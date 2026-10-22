"""Staging adapter for ramirobentes/nba_data play-by-play.

raw:  data/raw/ramirobentes/pbp_{regular|playoffs}_{season_end_year}.parquet
out:  games, events, lineups, player_names DataFrames in our common schema
      (see docs/decisions.md, "Phase 1 design").

Everything that cannot be mapped raises StagingError (CLAUDE.md rule 7). The only rows
not carried into events are ramirobentes' own synthetic msg_type 99 markers, and they
are counted and returned, never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from nba_platform.ingest.download import RAW_DIR, ramirobentes_filename
from nba_platform.seasons import check_season_type, season_label

SOURCE = "ramirobentes"

MSG_TYPE_TO_EVENT_TYPE = {
    1: "shot_made",
    2: "shot_missed",
    3: "free_throw",
    4: "rebound",
    5: "turnover",
    6: "foul",
    7: "violation",
    8: "substitution",
    9: "timeout",
    10: "jump_ball",
    11: "other",  # ejection
    12: "period_start",
    13: "period_end",
    18: "other",  # instant replay
    # cdn.nba.com-era codes (seen in 2025-26); see docs/validation/format_diff_2004-05_vs_2025-26.md
    22: "other",  # "<TEAM> Heave" marker
    92: "other",  # block as its own row (older seasons: blocker is on the missed shot)
    93: "other",  # "Game End"
    95: "other",  # steal as its own row (the turnover row also names the stealer)
    # 2017-18 → 2024-25 codes
    0: "other",   # "Game End"
    20: "other",  # "Stoppage: Out-of-Bounds / Injury / Blood Rule / ..."
}
# Team xref: an abbreviation maps to the TEAM_ID behind at least this share of its joined
# shots; the rest are reported (check 110) as join noise, never silently used.
TEAM_XREF_MIN_SHARE = 0.99
# Rows ramirobentes adds itself ("Last possession of quarter"); not NBA events.
SYNTHETIC_MSG_TYPE = 99
SYNTHETIC_EVENT_NUM = 9999

PLAYER_KEY_COLUMNS = ("player1_name", "player2_name", "player3_name")
PLAYER_KEY_RE = r"^(\d+) (\S.*)$"
CLOCK_RE = r"^(\d{1,2}):(\d{2}(?:\.\d+)?)$"


class StagingError(RuntimeError):
    """A raw row could not be mapped. The pipeline must stop."""


@dataclass
class StagedSeason:
    games: pd.DataFrame
    events: pd.DataFrame
    lineups: pd.DataFrame
    player_names: pd.DataFrame
    n_synthetic_rows: int
    n_corrections_applied: int
    order_ties: pd.DataFrame  # rows sharing a number_event (ordered by event_num)


def raw_path(season_end_year: int, season_type: str) -> Path:
    return RAW_DIR / SOURCE / ramirobentes_filename(season_end_year, season_type)


def read_raw(season_end_year: int, season_type: str) -> pd.DataFrame:
    return pd.read_parquet(raw_path(season_end_year, check_season_type(season_type)))


# --------------------------------------------------------------------------- parsing


def parse_player_keys(keys: pd.Series, column: str = "player") -> pd.DataFrame:
    """Split '1477 Bruce Bowen' into player_id (Int64) and name. NULL stays NULL.

    Each distinct string is parsed once and mapped back: a season has a few hundred distinct players but millions
    of lineup entries, and parsing every entry used several GB (a MemoryError on a busy machine, 2026-10-22).
    """
    distinct = pd.Series(keys.dropna().unique(), dtype=object)
    parts = distinct.str.extract(PLAYER_KEY_RE)
    bad_values = distinct[parts[0].isna()]
    if len(bad_values):
        bad = keys.isin(bad_values.tolist())
        raise StagingError(f"{column}: {int(bad.sum())} values are not 'ID Name': {keys[bad].unique()[:5].tolist()}")
    ids = pd.Series(pd.to_numeric(parts[0]).astype("Int64").to_numpy(), index=distinct.to_numpy())
    names = pd.Series(parts[1].str.strip().to_numpy(), index=distinct.to_numpy())
    return pd.DataFrame({"player_id": keys.map(ids).astype("Int64"), "name": keys.map(names)}, index=keys.index)


def parse_lineups(lineups: pd.Series, column: str = "lineup") -> tuple[pd.Series, pd.DataFrame]:
    """Comma-separated 'ID Name' strings -> (Series of player_id lists, exploded keys).

    A NULL lineup becomes an empty list so that validation check 3 reports it.
    """
    exploded = lineups.str.split(", ").explode()
    keys = parse_player_keys(exploded.dropna(), column)
    id_lists = keys["player_id"].astype("int64").groupby(level=0).agg(list)
    id_lists = id_lists.reindex(lineups.index)
    id_lists = id_lists.apply(lambda v: v if isinstance(v, list) else [])
    return id_lists, keys


def clock_to_secs_elapsed(period: pd.Series, clock: pd.Series) -> pd.Series:
    """Seconds since tip-off from period + 'MM:SS' clock (regulation 720 s, OT 300 s)."""
    parts = clock.str.extract(CLOCK_RE)
    bad = parts[0].isna()
    if bad.any():
        raise StagingError(f"clock: {int(bad.sum())} unparseable values: {clock[bad].unique()[:5].tolist()}")
    remaining = pd.to_numeric(parts[0]) * 60 + pd.to_numeric(parts[1])
    period = period.astype("int64")
    period_start = np.where(period <= 4, (period - 1) * 720, 2880 + (period - 5) * 300)
    period_len = np.where(period <= 4, 720, 300)
    return pd.Series(period_start + period_len - remaining, index=clock.index, dtype="float64")


def map_team_abbr(abbr: pd.Series, team_ids: dict[str, int], column: str) -> pd.Series:
    """Abbreviation -> team_id. NULL stays NULL; an unknown abbreviation raises."""
    unknown = abbr.notna() & ~abbr.isin(list(team_ids))
    if unknown.any():
        raise StagingError(f"{column}: unmapped team abbreviations {sorted(abbr[unknown].unique())}")
    return abbr.map(team_ids).astype("Int64")


# --------------------------------------------------------------------------- teams


def derive_team_xref(raw: pd.DataFrame, shotdetail: pd.DataFrame, season_end_year: int) -> pd.DataFrame:
    """Map each ramirobentes team abbreviation to an NBA team_id via shotdetail.

    Join: ramirobentes FGA rows (msg_type 1/2) to shotdetail on game_id + event_num.
    Each abbreviation maps to the TEAM_ID behind >= TEAM_XREF_MIN_SHARE of its joined
    shots (the rest is counted in ``n_conflicting``); the result must be one-to-one.
    """
    fga = raw.loc[raw["msg_type"].isin([1, 2]) & raw["team_abb"].notna(), ["game_id", "event_num", "team_abb"]]
    shots = shotdetail[["GAME_ID", "GAME_EVENT_ID", "TEAM_ID", "TEAM_NAME"]]
    joined = fga.merge(
        shots, left_on=["game_id", "event_num"], right_on=["GAME_ID", "GAME_EVENT_ID"], how="inner"
    )
    all_pairs = joined.groupby(["team_abb", "TEAM_ID", "TEAM_NAME"]).size().reset_index(name="n")
    totals = all_pairs.groupby("team_abb")["n"].transform("sum")
    all_pairs["share"] = all_pairs["n"] / totals
    weak = all_pairs.groupby("team_abb")["share"].max() < TEAM_XREF_MIN_SHARE
    if weak.any():
        raise StagingError(
            f"team xref: no TEAM_ID reaches {TEAM_XREF_MIN_SHARE:.0%} of joined shots for "
            f"{all_pairs[all_pairs['team_abb'].isin(weak[weak].index)].to_dict('records')}")
    pairs = all_pairs[all_pairs["share"] >= TEAM_XREF_MIN_SHARE].copy()
    pairs["n_conflicting"] = (totals[pairs.index] - pairs["n"]).astype("int64")

    multi_id = pairs.groupby("team_abb")["TEAM_ID"].nunique()
    multi_abbr = pairs.groupby("TEAM_ID")["team_abb"].nunique()
    if (multi_id > 1).any() or (multi_abbr > 1).any():
        raise StagingError(
            f"team xref not one-to-one: {pairs[pairs['team_abb'].isin(multi_id[multi_id > 1].index)].to_dict('records')}"
            f" / {pairs[pairs['TEAM_ID'].isin(multi_abbr[multi_abbr > 1].index)].to_dict('records')}"
        )
    multi_name = pairs.groupby("team_abb")["TEAM_NAME"].nunique()
    if (multi_name > 1).any():
        raise StagingError(f"team xref: more than one TEAM_NAME for {multi_name[multi_name > 1].index.tolist()}")

    seen = set(raw["team_abb"].dropna()) | set(raw["team_home"]) | set(raw["team_away"])
    missing = seen - set(pairs["team_abb"])
    if missing:
        raise StagingError(f"team xref: no shotdetail match for abbreviations {sorted(missing)}")

    return pd.DataFrame(
        {
            "source": SOURCE,
            "season_end_year": season_end_year,
            "source_team_key": pairs["team_abb"],
            "team_id": pairs["TEAM_ID"].astype("int64"),
            "team_name": pairs["TEAM_NAME"],
            "method": "auto",
            "n_joined_shots": pairs["n"].astype("int64"),
            "n_conflicting": pairs["n_conflicting"],
        }
    )


# --------------------------------------------------------------------------- corrections


def _same_value(current, expected: str) -> bool:
    if pd.isna(current):
        return expected == ""
    try:
        return float(current) == float(expected)
    except (TypeError, ValueError):
        return str(current) == expected


# corrections.csv row that removes one copy of an event the source repeats verbatim:
# field = "__row__", old_value = "exact_duplicate", new_value = "drop_one".
DROP_DUPLICATE_FIELD = "__row__"


# Columns ramirobentes derives itself (possession / free-throw attribution and helpers).
# Everything else is an NBA original field (event_num, msg/act type, period, clock,
# description, players, lineups, scores, shot_pts ...).
RB_DERIVED_COLUMNS = frozenset({
    "player_ft", "team_ft", "total_fta", "type_foul", "possession", "poss_home", "poss_away",
    "start_poss", "shot_pts_home", "shot_pts_away", "secs_played", "and1", "garbage_time",
    "margin_before", "total_starters_home", "total_starters_away", "reb_type", "off_team_abb",
})


def _drop_exact_duplicate(df: pd.DataFrame, c) -> pd.DataFrame:
    """Drop all but the first copy of a duplicated event.

    - `exact_duplicate`: copies must be identical in every raw column;
    - `derived_only_duplicate`: copies may differ only in RB_DERIVED_COLUMNS (the event
      was verified to appear once in the official PBP before this correction was written).
    Anything else fails.
    """
    if c.new_value != "drop_one" or c.old_value not in ("exact_duplicate", "derived_only_duplicate"):
        raise StagingError(f"correction {c}: __row__ supports exact_duplicate / derived_only_duplicate -> drop_one")
    mask = (df["game_id"] == c.game_id) & (df["event_num"] == float(c.source_event_num)) & (
        df["msg_type"] != SYNTHETIC_MSG_TYPE)
    rows = df[mask]
    if len(rows) < 2:
        raise StagingError(f"correction {c}: expected a duplicated event, matched {len(rows)} rows")
    compare = rows if c.old_value == "exact_duplicate" else rows.drop(columns=list(RB_DERIVED_COLUMNS & set(rows.columns)))
    if len(compare.astype(str).drop_duplicates()) != 1:
        raise StagingError(f"correction {c}: rows differ in columns that are not allowed to differ; not dropping")
    return df.drop(index=rows.index[1:])


def apply_corrections(raw: pd.DataFrame, corrections: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Apply corrections.csv rows whose game_id is in this file. Returns (copy, n_applied)."""
    todo = corrections[corrections["game_id"].isin(set(raw["game_id"]))]
    if todo.empty:
        return raw, 0
    out = raw.copy()
    for c in todo.itertuples(index=False):
        if c.field == DROP_DUPLICATE_FIELD:
            out = _drop_exact_duplicate(out, c)
            continue
        if c.field not in out.columns:
            raise StagingError(f"correction {c}: field {c.field!r} not in {SOURCE} columns")
        mask = (
            (out["game_id"] == c.game_id)
            & (out["event_num"] == float(c.source_event_num))
            & (out["msg_type"] != SYNTHETIC_MSG_TYPE)
        )
        if mask.sum() != 1:
            raise StagingError(f"correction {c}: matched {int(mask.sum())} rows, expected 1")
        current = out.loc[mask, c.field].iloc[0]
        if not _same_value(current, c.old_value):
            raise StagingError(f"correction {c}: current value {current!r} != old_value {c.old_value!r}")
        new = np.nan if c.new_value == "" else c.new_value
        if new is not np.nan and pd.api.types.is_numeric_dtype(out[c.field]):
            new = float(new)
        out.loc[mask, c.field] = new
    return out, len(todo)


def read_corrections(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# --------------------------------------------------------------------------- stage


def _one_value_per_game(df: pd.DataFrame, column: str) -> pd.Series:
    n = df.groupby("game_id")[column].nunique(dropna=False)
    if (n != 1).any():
        raise StagingError(f"{column}: more than one value in games {n[n != 1].index[:5].tolist()}")
    return df.groupby("game_id")[column].first()


def stage(
    raw: pd.DataFrame,
    team_xref: pd.DataFrame,
    season_end_year: int,
    season_type: str,
    corrections: pd.DataFrame | None = None,
) -> StagedSeason:
    check_season_type(season_type)
    if corrections is not None:
        raw, n_corr = apply_corrections(raw, corrections)
    else:
        n_corr = 0

    if set(raw["season"].unique()) != {season_end_year}:
        raise StagingError(f"season column {sorted(raw['season'].unique())} != {season_end_year}")
    if set(raw["season_type"].unique()) != {season_type}:
        raise StagingError(f"season_type column {sorted(raw['season_type'].unique())} != {season_type!r}")

    synthetic = raw["msg_type"] == SYNTHETIC_MSG_TYPE
    if (raw.loc[synthetic, "event_num"] != SYNTHETIC_EVENT_NUM).any():
        raise StagingError("msg_type 99 row with event_num != 9999: not a known synthetic marker")
    df = raw.loc[~synthetic].copy()

    unknown = ~df["msg_type"].isin(list(MSG_TYPE_TO_EVENT_TYPE))
    if unknown.any():
        raise StagingError(f"unmapped msg_type values {sorted(df.loc[unknown, 'msg_type'].unique())}")

    # Order: ramirobentes number_event; ties (different events sharing a number_event,
    # seen in older seasons) are broken by the NBA event_num and reported (check 109).
    df = df.sort_values(["game_id", "number_event", "event_num"], kind="stable").reset_index(drop=True)
    tied = df.duplicated(["game_id", "number_event"], keep=False)
    order_ties = df.loc[tied, ["game_id", "number_event", "event_num", "description"]]
    if df.duplicated(["game_id", "event_num"]).any():
        raise StagingError("duplicate (game_id, event_num): source_event_num is not unique")
    df["event_seq"] = df.groupby("game_id").cumcount() + 1

    team_ids = dict(zip(team_xref["source_team_key"], team_xref["team_id"]))
    players = {col: parse_player_keys(df[col], col) for col in PLAYER_KEY_COLUMNS}
    home_ids, home_keys = parse_lineups(df["lineup_home"], "lineup_home")
    away_ids, away_keys = parse_lineups(df["lineup_away"], "lineup_away")

    events = pd.DataFrame(
        {
            "game_id": df["game_id"],
            "event_seq": df["event_seq"].astype("int64"),
            "source_event_num": df["event_num"].astype("int64"),
            "period": df["period"].astype("int64"),
            "clock": df["clock"],
            "secs_elapsed_game": clock_to_secs_elapsed(df["period"], df["clock"]),
            "source_secs_game": df["secs_game"],
            "team_id": map_team_abbr(df["team_abb"], team_ids, "team_abb"),
            "event_type": df["msg_type"].astype("int64").map(MSG_TYPE_TO_EVENT_TYPE),
            "event_subtype": df["act_type"].astype("Int64"),
            "source_msg_type": df["msg_type"].astype("int64"),
            "player1_id": players["player1_name"]["player_id"],
            "player2_id": players["player2_name"]["player_id"],
            "player3_id": players["player3_name"]["player_id"],
            "points": np.where(df["msg_type"].isin([1, 3]), df["shot_pts"], 0).astype("int64"),
            "home_score": df["hs"].astype("int64"),
            "away_score": df["vs"].astype("int64"),
            "description": df["description"].str.strip(),
            "source": SOURCE,
        }
    )

    lineups = pd.DataFrame(
        {
            "game_id": df["game_id"],
            "event_seq": events["event_seq"],
            "home_player_ids": home_ids,
            "away_player_ids": away_ids,
            "source": SOURCE,
        }
    )

    last = events.groupby("game_id").tail(1).set_index("game_id")
    games = pd.DataFrame(
        {
            "season": season_label(season_end_year),
            "season_end_year": season_end_year,
            "season_type": season_type,
            "game_date": pd.to_datetime(_one_value_per_game(df, "game_date")).dt.date,
            "home_team_id": map_team_abbr(_one_value_per_game(df, "team_home"), team_ids, "team_home"),
            "away_team_id": map_team_abbr(_one_value_per_game(df, "team_away"), team_ids, "team_away"),
            "home_score": last["home_score"],
            "away_score": last["away_score"],
            "num_periods": events.groupby("game_id")["period"].max(),
            "source": SOURCE,
        }
    ).rename_axis("game_id").reset_index()

    all_keys = pd.concat(
        [players[c].dropna() for c in PLAYER_KEY_COLUMNS]
        + [parse_player_keys(df["player_ft"], "player_ft").dropna(), home_keys, away_keys]
    )
    player_names = (
        all_keys.groupby(["player_id", "name"]).size().reset_index(name="n_rows")
        .assign(source=SOURCE, season_end_year=season_end_year, season_type=season_type)
    )
    player_names["player_id"] = player_names["player_id"].astype("int64")
    player_names["source_player_key"] = player_names["player_id"].astype(str) + " " + player_names["name"]

    return StagedSeason(
        games=games,
        events=events,
        lineups=lineups,
        player_names=player_names,
        n_synthetic_rows=int(synthetic.sum()),
        n_corrections_applied=n_corr,
        order_ties=order_ties,
    )
