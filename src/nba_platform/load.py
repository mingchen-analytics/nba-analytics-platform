"""Write staged DataFrames to data/staging/ (Parquet) and load them into DuckDB.

Loading is idempotent per (source, season_end_year, season_type): that season's rows are
deleted and re-inserted in one transaction. Reference tables (teams, players,
player_xref) are rebuilt from their xref/name tables after every load.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import duckdb
import pandas as pd

from nba_platform.db import PROJECT_ROOT
from nba_platform.staging.ramirobentes import StagedSeason

STAGING_DIR = PROJECT_ROOT / "data" / "staging"


def staging_dir(source: str, season_end_year: int, season_type: str) -> Path:
    return STAGING_DIR / source / f"{season_type}_{season_end_year}"


def write_staging(frames: dict[str, pd.DataFrame], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, df in frames.items():
        path = out_dir / f"{name}.parquet"
        df.to_parquet(path, index=False)
        paths[name] = path
    return paths


def _p(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def load_pbp_season(
    con: duckdb.DuckDBPyConnection,
    staged: StagedSeason,
    team_xref: pd.DataFrame,
    source: str,
    season_end_year: int,
    season_type: str,
    before_commit: Callable[[duckdb.DuckDBPyConnection], None] | None = None,
    out_dir: Path | None = None,
) -> dict[str, Path]:
    """Stage to Parquet, then replace this season's games/events/lineups in DuckDB.

    ``before_commit`` runs inside the transaction (hard validation checks); if it raises,
    the whole season load is rolled back and the exception propagates.
    """
    paths = write_staging(
        {
            "games": staged.games,
            "events": staged.events,
            "lineups": staged.lineups,
            "player_names": staged.player_names,
            "team_xref": team_xref,
        },
        out_dir or staging_dir(source, season_end_year, season_type),
    )
    p = {k: _p(v) for k, v in paths.items()}
    season_games = (
        "SELECT game_id FROM core.games WHERE season_end_year = $y AND season_type = $t "
        f"UNION SELECT game_id FROM read_parquet('{p['games']}')"
    )
    params = {"y": season_end_year, "t": season_type}

    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"DELETE FROM core.events WHERE game_id IN ({season_games})", params)
        con.execute(f"DELETE FROM staging.event_lineups WHERE game_id IN ({season_games})", params)
        con.execute(f"DELETE FROM core.games WHERE game_id IN ({season_games})", params)
        con.execute(
            "DELETE FROM staging.player_names WHERE source = $s AND season_end_year = $y AND season_type = $t",
            {"s": source, **params},
        )
        # team_xref is keyed by season, not season type: replace only the abbreviations this
        # file maps, so loading the playoffs never drops regular-season teams (bug fixed 2026-10-18)
        con.execute(
            f"""DELETE FROM core.team_xref WHERE source = $s AND season_end_year = $y
                AND source_team_key IN (SELECT source_team_key FROM read_parquet('{p['team_xref']}'))""",
            {"s": source, "y": season_end_year},
        )

        con.execute(f"""
            INSERT INTO core.games BY NAME
            SELECT game_id, season, season_end_year, season_type, game_date,
                   home_team_id, away_team_id, home_score, away_score, num_periods, source
            FROM read_parquet('{p['games']}')""")
        con.execute(f"""
            INSERT INTO core.events BY NAME
            SELECT game_id, event_seq, source_event_num, period, clock, secs_elapsed_game,
                   team_id, event_type, event_subtype, source_msg_type,
                   player1_id, player2_id, player3_id, points, home_score, away_score,
                   description, source
            FROM read_parquet('{p['events']}')""")
        con.execute(f"""
            INSERT INTO staging.event_lineups
            SELECT game_id, event_seq,
                   CAST(home_player_ids AS INTEGER[]), CAST(away_player_ids AS INTEGER[]), source
            FROM read_parquet('{p['lineups']}')""")
        con.execute(f"""
            INSERT INTO staging.player_names
            SELECT source, season_end_year, season_type, player_id, name, source_player_key, n_rows
            FROM read_parquet('{p['player_names']}')""")
        con.execute(f"""
            INSERT INTO core.team_xref
            SELECT source, season_end_year, source_team_key, team_id, team_name, method
            FROM read_parquet('{p['team_xref']}')""")
        rebuild_reference_tables(con)
        if before_commit is not None:
            before_commit(con)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return paths


def rebuild_reference_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("DELETE FROM core.teams")
    con.execute("""
        INSERT INTO core.teams
        SELECT team_id,
               arg_max(source_team_key, season_end_year),
               arg_max(team_name, season_end_year)
        FROM core.team_xref GROUP BY team_id""")

    con.execute("DELETE FROM core.players")
    con.execute("""
        INSERT INTO core.players
        WITH by_season AS (
            SELECT player_id, name, season_end_year, sum(n_rows) AS n
            FROM staging.player_names GROUP BY ALL
        )
        SELECT player_id,
               arg_max(name, CAST(season_end_year AS BIGINT) * 1000000000 + n),
               list(DISTINCT name ORDER BY name)
        FROM by_season GROUP BY player_id""")

    # Only the sources rebuilt from staging.player_names; other sources' xref rows
    # (e.g. bigdataball, built by validate/bdb_crosscheck.py) are kept.
    con.execute("DELETE FROM core.player_xref WHERE source IN (SELECT DISTINCT source FROM staging.player_names)")
    con.execute("""
        INSERT INTO core.player_xref
        SELECT DISTINCT source, source_player_key, player_id, 'auto'
        FROM staging.player_names""")


def load_shots_season(
    con: duckdb.DuckDBPyConnection,
    shots: pd.DataFrame,
    source: str,
    season_end_year: int,
    season_type: str,
    before_commit: Callable[[duckdb.DuckDBPyConnection], None] | None = None,
    out_dir: Path | None = None,
) -> Path:
    """Stage shots to Parquet, then replace this season's shots in DuckDB."""
    path = write_staging({"shots": shots}, out_dir or staging_dir(source, season_end_year, season_type))["shots"]
    p = _p(path)
    season_games = (
        "SELECT game_id FROM core.games WHERE season_end_year = $y AND season_type = $t "
        f"UNION SELECT DISTINCT game_id FROM read_parquet('{p}')"
    )
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"DELETE FROM core.shots WHERE game_id IN ({season_games})",
                    {"y": season_end_year, "t": season_type})
        con.execute(f"""
            INSERT INTO core.shots BY NAME
            SELECT game_id, source_event_num, player_id, team_id, shot_type, action_type,
                   shot_zone_basic, shot_zone_area, shot_zone_range, distance_ft, loc_x, loc_y, made, source
            FROM read_parquet('{p}')""")
        if before_commit is not None:
            before_commit(con)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return path
