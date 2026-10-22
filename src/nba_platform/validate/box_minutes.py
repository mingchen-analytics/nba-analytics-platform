"""Box-score minutes from cached nba_api LeagueGameLog responses (validation check 5)."""

from __future__ import annotations

import json

import pandas as pd

from nba_platform.ingest.nba_api_gamelog import cache_path


def load_box_minutes(season_end_year: int, season_type: str) -> pd.DataFrame | None:
    """(game_id, player_id, team_id, box_min) or None when the cache file is missing."""
    path = cache_path(season_end_year, season_type)
    if not path.exists():
        return None
    rs = json.loads(path.read_text(encoding="utf-8"))["resultSets"][0]
    df = pd.DataFrame(rs["rowSet"], columns=rs["headers"])
    return pd.DataFrame({
        "game_id": df["GAME_ID"].astype(str).str.zfill(10),
        "player_id": df["PLAYER_ID"].astype("int64"),
        "team_id": df["TEAM_ID"].astype("int64"),
        "box_min": pd.to_numeric(df["MIN"]).astype("float64"),
    })


def team_minutes_balance(con, season_end_year: int, season_type: str, box: pd.DataFrame) -> float:
    """Share of team-games whose box minutes do not sum to 5 x game length (rounding signature)."""
    con.register("box_tm", box)
    try:
        return float(con.execute("""
            SELECT avg((s <> 5 * (48 + 5 * (g.num_periods - 4)))::INT)
            FROM (SELECT game_id, team_id, sum(box_min) AS s FROM box_tm GROUP BY ALL) b
            JOIN core.games g USING (game_id)""").fetchone()[0] or 0.0)
    finally:
        con.unregister("box_tm")


def write_report(con, path) -> None:
    """docs/validation/minutes_vs_box.md from validation.results check 5 (numbers only)."""
    from nba_platform.seasons import season_label

    rows = con.execute("""SELECT season_end_year, season_type, status, n_checked, n_failed, detail
                          FROM validation.results WHERE check_id = 5
                          ORDER BY season_type <> 'regular', season_end_year""").fetchall()
    lines = ["# Validation check 5: play-by-play minutes vs box score", "",
             "Box score: nba_api `LeagueGameLog` (player level, whole minutes), cached in `data/raw/nba_api/`.",
             "PBP minutes: time to the next event credited to the ten players shown on each event.",
             "Warning level only. |diff| up to 1 minute is rounding (box minutes are integers).",
             "`team-games ≠ 5×length` = share of team-games whose box minutes do not add up to the game",
             "length; ~55 % is the normal signature of rounding each player independently.", "",
             "| season | type | player-games | ≤0.5 | ≤1 | ≤2 | ≤5 | >5 | mean abs diff (min) | PBP only | box only | team-games ≠ 5×length | games with a >5 min diff |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for y, t, status, n, nf, detail in rows:
        d = json.loads(detail)
        if status == "skip":
            lines.append(f"| {season_label(y)} | {t} | skip | | | | | | | | | | |")
            continue
        dist = list(d["abs_diff_distribution"].values())
        box = load_box_minutes(y, t)
        bal = team_minutes_balance(con, y, t, box) if box is not None else float("nan")
        big = ", ".join(f"{g['game_id']} ({g['max_diff_min']})" for g in d["largest_diff_games"][:3]) or "—"
        lines.append(f"| {season_label(y)} | {t} | {d['player_games_compared']:,} | " + " | ".join(f"{v:,}" for v in dist)
                     + f" | {d['mean_abs_diff_min']} | {d['pbp_only_player_games']} | {d['box_only_player_games']} | {bal:.1%} | {big} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
