"""Known gaps and source contradictions (corrections/known_gaps.csv).

Re-applied after every season load so they survive reloads:
- `pbp_missing`: the game is absent from the play-by-play source. Its `core.games` row is
  built from the nba_api box score (teams, score, date; `num_periods` unknown → NULL) and
  carries `pbp_missing = TRUE`. It has no events.
- any other issue (e.g. `source_score_conflict`): the existing game row gets `known_issue`.
Validation reports known gaps with status `known` (a warning), not as failures.
"""

from __future__ import annotations

import json

import pandas as pd

from nba_platform.db import PROJECT_ROOT
from nba_platform.ingest.nba_api_gamelog import cache_path
from nba_platform.seasons import season_label

KNOWN_GAPS_CSV = PROJECT_ROOT / "corrections" / "known_gaps.csv"


def read_known_gaps() -> pd.DataFrame:
    return pd.read_csv(KNOWN_GAPS_CSV, dtype={"game_id": str}, keep_default_na=False)


def box_game_row(game_id: str, season_end_year: int, season_type: str) -> dict | None:
    """Teams, score and date of one game from the cached LeagueGameLog (player rows)."""
    path = cache_path(season_end_year, season_type)
    if not path.exists():
        return None
    rs = json.loads(path.read_text(encoding="utf-8"))["resultSets"][0]
    df = pd.DataFrame(rs["rowSet"], columns=rs["headers"])
    g = df[df["GAME_ID"].astype(str).str.zfill(10) == game_id]
    if g.empty:
        return None
    teams = g.groupby("TEAM_ID").agg(pts=("PTS", "sum"), matchup=("MATCHUP", "first"), date=("GAME_DATE", "first"))
    home = teams[teams["matchup"].str.contains(" vs. ")]
    away = teams[teams["matchup"].str.contains(" @ ")]
    if len(home) != 1 or len(away) != 1:
        return None
    return {"game_id": game_id, "season": season_label(season_end_year), "season_end_year": season_end_year,
            "season_type": season_type, "game_date": pd.to_datetime(home["date"].iloc[0]).date(),
            "home_team_id": int(home.index[0]), "away_team_id": int(away.index[0]),
            "home_score": int(home["pts"].iloc[0]), "away_score": int(away["pts"].iloc[0]),
            "num_periods": None, "source": "nba_api_box", "pbp_missing": True, "known_issue": "pbp_missing"}


def apply(con, season_end_year: int, season_type: str) -> list[str]:
    """Insert / flag this season's known gaps. Returns problems (never raises)."""
    gaps = read_known_gaps()
    gaps = gaps[(gaps["season_end_year"].astype(int) == season_end_year) & (gaps["season_type"] == season_type)]
    con.execute("DELETE FROM core.known_gaps WHERE season_end_year = ? AND season_type = ?",
                [season_end_year, season_type])
    problems = []
    for g in gaps.itertuples(index=False):
        if g.issue == "pbp_missing":
            if con.execute("SELECT count(*) FROM core.events WHERE game_id = ?", [g.game_id]).fetchone()[0]:
                problems.append(f"{g.game_id}: listed as pbp_missing but has events; not changed")
                continue
            row = box_game_row(g.game_id, season_end_year, season_type)
            if row is None:
                problems.append(f"{g.game_id}: no box score in the nba_api cache; game row not added")
                continue
            con.execute("DELETE FROM core.games WHERE game_id = ?", [g.game_id])
            con.execute("INSERT INTO core.games BY NAME SELECT * FROM (SELECT " +
                        ", ".join(f"${k} AS {k}" for k in row) + ")", row)
        else:
            n = con.execute("SELECT count(*) FROM core.games WHERE game_id = ?", [g.game_id]).fetchone()[0]
            if not n:
                problems.append(f"{g.game_id}: game not loaded; flag not set")
                continue
            con.execute("UPDATE core.games SET known_issue = ? WHERE game_id = ?", [g.issue, g.game_id])
        con.execute("INSERT INTO core.known_gaps VALUES (?, ?, ?, ?, ?, ?)",
                    [g.game_id, season_end_year, season_type, g.issue, g.reason, g.added_on])
    return problems


def season_gaps(con, season_end_year: int, season_type: str) -> dict[str, str]:
    """{game_id: issue} for one season (empty if the table has no rows)."""
    return dict(con.execute("SELECT game_id, issue FROM core.known_gaps WHERE season_end_year = ? AND season_type = ?",
                            [season_end_year, season_type]).fetchall())
