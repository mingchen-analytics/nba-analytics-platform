"""Write validation reports to docs/validation/ (CLAUDE.md: every anomaly is reported).

- docs/validation/details/{season_type}_{season_end_year}.md : every check of one season
- docs/validation/season_report.md                          : one row per season
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb

from nba_platform.db import PROJECT_ROOT
from nba_platform.seasons import season_label
from nba_platform.validate.checks import CheckResult

VALIDATION_DIR = PROJECT_ROOT / "docs" / "validation"
DETAILS_DIR = VALIDATION_DIR / "details"

# Columns of the season report, in order: (check_id, short header)
REPORT_COLUMNS = [
    (0, "0 staging"), (9, "9 IDs"), (102, "102 keys"), (104, "104 dup"), (105, "105 time"), (106, "106 rows"),
    (1, "1 games"), (2, "2 score"), (3, "3 five"), (4, "4 subs"), (5, "5 box"), (6, "6 secs"),
    (107, "107 shot rows"), (10, "10 shots"), (11, "11 BigDataBall"), (101, "101 clock"), (109, "109 order ties"), (110, "110 xref noise"), (111, "111 known gaps"),
]


def write_season_detail(season_end_year: int, season_type: str, outcome: str,
                        results: list[CheckResult], notes: list[str] | None = None) -> Path:
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    path = DETAILS_DIR / f"{season_type}_{season_end_year}.md"
    lines = [
        f"# Validation — {season_label(season_end_year)} {season_type}",
        "",
        f"Outcome: **{outcome}**",
        "",
        "| check | level | status | checked | failed | name |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda r: (r.level != "hard", r.check_id)):
        lines.append(f"| {r.check_id} | {r.level} | {r.status} | {_n(r.n_checked)} | {_n(r.n_failed)} | {r.check_name} |")
    details = [r for r in results if r.status != "pass" or r.detail]
    if details:
        lines += ["", "## Details", ""]
        for r in sorted(details, key=lambda r: r.check_id):
            lines += [f"### {r.check_id} — {r.check_name} ({r.status})", "",
                      "```json", json.dumps(r.detail, default=str, ensure_ascii=False, indent=1)[:4000], "```", ""]
    for note in notes or []:
        lines += ["", note]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _n(v) -> str:
    return "" if v is None else f"{v:,}"


def write_season_report(con: duckdb.DuckDBPyConnection, outcomes: dict[tuple[int, str], str] | None = None) -> Path:
    """One row per (season, season_type) from the latest validation.results."""
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    rows = con.execute("""
        SELECT season_end_year, season_type, check_id, status, n_failed
        FROM validation.results
        QUALIFY row_number() OVER (PARTITION BY season_end_year, season_type, check_id ORDER BY run_at DESC) = 1
    """).fetchall()
    games = dict(((y, t), (n, e)) for y, t, n, e in con.execute("""
        SELECT g.season_end_year, g.season_type, count(DISTINCT g.game_id), count(e.game_id)
        FROM core.games g LEFT JOIN core.events e USING (game_id) GROUP BY ALL""").fetchall())
    by_season: dict[tuple[int, str], dict[int, tuple[str, int | None]]] = {}
    for y, t, cid, status, n_failed in rows:
        by_season.setdefault((y, t), {})[cid] = (status, n_failed)

    def cell(entry):
        if entry is None:
            return "—"
        status, n_failed = entry
        if status == "pass":
            return "✅"
        if status == "skip":
            return "skip"
        if status == "known":
            return "⚠ known"
        return f"❌ {n_failed:,}" if n_failed is not None else "❌"

    header = ["season", "type", "outcome", "games", "events"] + [h for _, h in REPORT_COLUMNS]
    lines = [
        "# Season validation report",
        "",
        "One row per season and season type. ✅ pass · ❌ n = failed count · ⚠ known = only known gaps (corrections/known_gaps.csv) · skip = not run (no source) · — = not run.",
        "Hard checks (0, 9, 102, 104, 105, 106): a failure means the season was **not loaded**.",
        "Hard shot checks (107, 108): a failure means that season's **shots** were not loaded.",
        "All other checks are warnings: the season is loaded and the anomaly is listed in",
        "`details/{season_type}_{season_end_year}.md`. No data was changed to make a check pass.",
        "Related: `duplicate_source_events.csv` (duplicated source rows behind most hard fails),",
        "`proposed_corrections.csv` (proposed, not applied), `format_diff_2004-05_vs_2025-26.md`.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    for (y, t) in sorted(by_season, key=lambda k: (k[1] != "regular", k[0])):
        checks = by_season[(y, t)]
        hard_fail = any(checks.get(cid, ("pass",))[0] == "fail" for cid in (0, 9, 102, 104, 105, 106))
        shots_fail = any(checks.get(cid, ("pass",))[0] == "fail" for cid in (107, 108))
        outcome = (outcomes or {}).get((y, t)) or (
            "hard fail — not loaded" if hard_fail else "loaded; shots not loaded" if shots_fail else "loaded")
        n_games, n_events = games.get((y, t), (0, 0))
        lines.append("| " + " | ".join(
            [season_label(y), t, outcome, f"{n_games:,}", f"{n_events:,}"]
            + [cell(checks.get(cid)) for cid, _ in REPORT_COLUMNS]) + " |")
    reasons = con.execute("""
        SELECT season_end_year, season_type, check_id, check_name, detail FROM validation.results
        WHERE level = 'hard' AND status = 'fail' ORDER BY season_type <> 'regular', season_end_year, check_id
    """).fetchall()
    if reasons:
        lines += ["", "## Hard-fail reasons", ""]
        for y, t_, cid, name, detail in reasons:
            # no source values in the committed summary: drop quoted examples
            msg = re.sub(r"\[.*\]|'[^']*'", "[…]", str(json.loads(detail).get("error", detail)))[:300]
            lines.append(f"- **{season_label(y)} {t_}** — check {cid} ({name}): `{msg}`")
    path = VALIDATION_DIR / "season_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
