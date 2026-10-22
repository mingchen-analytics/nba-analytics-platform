# nba-analytics-platform

A personal NBA data platform built from raw play-by-play: my own event database, my own
possession and lineup ("stint") logic, and my own metrics (on/off → RAPM), with a dashboard
on top. Portfolio project by Ming Chen (Wake Forest MSBA, sports analytics).

**Status (2026-10-19):** data foundation done — play-by-play for every season 1996-97 →
2025-26 (regular season + playoffs) loaded, validated and reproducible from scratch;
stints and possessions are built for every season (checked against pbpstats); on/off and the
second dashboard layer are next.

## Why

Public NBA metrics hide many judgment calls: when a possession ends, who gets credit when
a substitution happens between free throws, what counts as garbage time. This project
makes every one of those decisions explicit, configurable (`config/rules.yaml`) and tested,
so each number can be explained and reproduced.

## Architecture

```
raw files (never modified, SHA-256 in data/raw/manifest.csv)
   │  Python adapters: parse IDs, clock → seconds, map event types, apply corrections
   ▼
staging (Parquet, one schema per source)
   │  load per season in one transaction; hard checks before commit
   ▼
DuckDB  core:       games · events · shots · teams · players · *_xref
        staging:    event_lineups (10 players on court per event)
        reference:  pbpstats possessions, NBA.com official possessions / tracking /
                    hustle / shot context / play types, matchups (comparison only)
        validation: one row per check per season
   │  next: stints + possessions (owner-written) → on/off → RAPM
   ▼
Streamlit (read-only): data-health dashboard today, metrics later
```

Code: `src/nba_platform/` — `ingest/` (downloads), `staging/` (one adapter per source),
`validate/` (checks and reports), `reference/`, `core/` (possessions and stints — mine,
stints, free throws, rebounds, possessions), `pipeline.py` (stage → load → validate). Details: `docs/data_dictionary.md`,
design log: `docs/decisions.md`.

## Data sources and terms

| Source | Used for | Notes |
|---|---|---|
| [ramirobentes/nba_data](https://github.com/ramirobentes/nba_data) | play-by-play + on-court lineups, 1996-97 → 2025-26 | no license stated → files kept local only |
| [shufinskiy/nba_data](https://github.com/shufinskiy/nba_data) | NBA shot-chart locations (all seasons); pbpstats possessions, official PBP and matchups (reference) | single files downloaded, not redistributed |
| nba_api (stats.nba.com) | box-score minutes, game lists, official possessions, tracking / hustle / play-type reference data | cached locally, throttled requests; NBA terms apply |
| BigDataBall (purchased) | cross-source validation only (7 seasons, 2004-05 → 2014-15) | never redistributed |

**No raw or third-party data is in this repository.** Only code, documentation and my own
derived summaries (IDs and numbers) are committed. Basketball Reference is not scraped.

**License.** The code and documentation are released under the [MIT License](LICENSE). The license covers
only my own work; it grants no rights to any third-party data (ramirobentes, shufinskiy, NBA.com,
BigDataBall, ...), which stays under its owners' terms and must be obtained from them.
`tests/fixtures/possessions/` holds short windows of real 2004-05 sequences (IDs, clocks and scores
only, no text) used to test the possession rules. `data/raw/manifest.csv` lists the publicly
downloadable files (URL, time, SHA-256); the listing of purchased files stays on my machine.

## Validation summary

Every season runs two levels of checks; every anomaly is reported
(`docs/validation/season_report.md`), and data is never changed to make a check pass.

- **Hard checks** (season is not loaded if one fails): every ID resolves, unique event
  keys, no player twice in a lineup, game time in range, no row inflation in joins.
- **Warnings** (reported, season loaded): game counts vs schedule, event points = final
  score, 5 + 5 players on court, substitution consistency, player-seconds = 5 × game
  length, minutes vs box score, shot-location join, cross-source lineups.

Results today:

- **60 of 60** season files loaded: 37,986 games, 17.5 M events, 6.3 M shots. Source
  problems were fixed only under strict, documented conditions (e.g. a duplicated event is
  dropped only if the official PBP has it once — `docs/validation/duplicate_verification.md`);
  known gaps are recorded, not patched (`corrections/known_gaps.csv`).
- **Reproducible:** a rebuild from zero reproduces all 11 core tables exactly
  (row counts and content hashes).
- **Possession counts vs pbpstats:** 91.5 % of team-games identical over 2000-01 → 2024-25
  (98.8 % through 2015-16). A break at 2016-17 was traced to the source's processing pipeline,
  so pbpstats — not the source's own possession columns — is the benchmark for my possession
  code (`docs/validation/possession_benchmark.md`).
- Shot locations join to ≥ 99.88 % of field-goal attempts in every season; early-era location
  problems are flagged, not deleted (`docs/validation/shot_quality.md`).
- Play-by-play minutes match box scores within rounding for > 99.8 % of player-games in most
  seasons; large gaps were traced to incomplete box scores (`docs/validation/minutes_large_diff.md`).
- Against BigDataBall (7 seasons): final scores agree in all but 2 of 8,883 games, 96–99.6 %
  of team lineups identical, and where they disagree, box-score minutes and official
  substitutions side with the primary source in 641 of 647 decidable cases
  (`docs/validation/bigdataball_crosscheck.md`).

## How to run

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pip install -e .

# download one season (raw files + manifest with url, time, sha256)
.venv/Scripts/python -m nba_platform.ingest.download --season-end-year 2005
.venv/Scripts/python -m nba_platform.ingest.download --season-end-year 2005 --season-type playoffs

# single-game checkpoint (in-memory DB), one season, or everything
.venv/Scripts/python -m nba_platform.pipeline --season-end-year 2005 --game-id 0020400027 --db :memory:
.venv/Scripts/python -m nba_platform.pipeline --season-end-year 2005
.venv/Scripts/python -m nba_platform.pipeline --all              # also rebuilds shot-quality flags and the BigDataBall cross-check

# extra validation sources
.venv/Scripts/python -m nba_platform.ingest.nba_api_gamelog      # box scores (run locally)
.venv/Scripts/python -m nba_platform.validate.run_check --check 5
.venv/Scripts/python -m nba_platform.validate.bdb_crosscheck
.venv/Scripts/python -m nba_platform.reference.pbpstats
.venv/Scripts/python -m nba_platform.reference.player_box        # official player box scores
.venv/Scripts/python -m nba_platform.marts.player_game_pbp      # our own box score (validation)
.venv/Scripts/python -m nba_platform.validate.box_vs_pbp        # docs/validation/box_vs_pbp.md
.venv/Scripts/python -m nba_platform.marts.box_marts            # player / team box marts for the dashboard
.venv/Scripts/python -m nba_platform.marts.shot_zones           # shooting zones + league percentiles
.venv/Scripts/python -m nba_platform.marts.tracking             # season tracking + hustle per player
.venv/Scripts/python -m nba_platform.validate.tracking_vs_box   # docs/validation/tracking_vs_box.md

# tests (integration tests open the database read-only; skipped if it does not exist)
.venv/Scripts/python -m pytest -q

# dashboard (internal, read-only, no player metrics): "Data health" page + "Reference data"
# page (possession benchmarks, NBA.com reference coverage) in the sidebar
.venv/Scripts/streamlit run app/data_health.py
```

### Pre-commit hook (tests must pass before every commit)

The repository ships a hook that runs the whole test suite and blocks the commit if anything
fails (failures or collection errors). Install it once per clone:

```bash
git config core.hooksPath scripts/git-hooks
```

### Database location

The DuckDB file lives **outside the project** at
`%LOCALAPPDATA%\nba_platform\nba_platform.duckdb` (Linux/macOS: `~/.local/share/nba_platform/`).
Set `NBA_PLATFORM_DB` only to override it. Only the pipeline writes to the database; open it
**read-only** in DBeaver or Streamlit.

### Folder-sync tools (Synology Drive, OneDrive, Dropbox, …)

If the project folder is synced, **exclude `data/`, `.venv/` and `*.duckdb`**. Sync clients
rewrite files behind DuckDB's back (a synced database was corrupted on 2026-10-17) and would
upload raw third-party data, which must stay local.

## Roadmap

- [x] Raw → staging → DuckDB for every season, with two-level validation; pytest pre-commit hook
- [x] Shots with quality flags; box-score, pbpstats and BigDataBall cross-checks
- [x] Reproducibility check (rebuild from zero, content hashes); possession benchmarks vs
      pbpstats and NBA official counts
- [x] NBA.com season-level reference data (official possessions, tracking, hustle, shot
      context, play types); single-game boxes in progress
- [x] Dashboard: data health + reference data pages
- [x] Possessions and stints (all 60 season files, `pbpstats_compat`; tests on real sequences in
      `tests/test_possession_rules.py`)
- [ ] On/off → RAPM (ridge, λ by game-grouped cross-validation)
- [ ] Playoff Matchup Adjustment Tracker and video tracking, linked by shared IDs
