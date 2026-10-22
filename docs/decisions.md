# Decisions log

Dated log of design decisions. Entries marked **[待確認]** were made conservatively
during unattended runs and need the owner's confirmation.

## 2026-10-16 — Project renamed to nba-analytics-platform

- Project name: `nba-analytics-platform` (was `courtbase`).
- Python package: `nba_platform`, at `src/nba_platform/` (src layout, `pyproject.toml`).
- DuckDB file: `data/nba_platform.duckdb`.
- Owner decision (confirmed).

## 2026-10-16 — Python 3.13 for the virtual environment

- `.venv` built with `py -3.13`; 3.14 is also installed but 3.13 has the most mature
  wheels for pyarrow / duckdb. Owner approved in the Phase 0 plan.

## 2026-10-16 — Phase 0 smoke test

- `pytest` exits with code 5 when no tests are collected, so Phase 0 adds
  `tests/test_smoke.py` (imports `nba_platform`) so "pytest passes" is meaningful.

## 2026-10-16 — Roadmap checkboxes in CLAUDE.md are not ticked during the overnight run [待確認]

- Ticking them would modify CLAUDE.md beyond the rename. Progress is tracked in
  `docs/progress_log.md` instead.

## 2026-10-16 — Phase 1 design (ramirobentes staging → DuckDB)

Observed facts (2004-05 regular, `pbp_regular_2005.parquet`) that drive the design:
- ramirobentes has **no team IDs**, only abbreviations (`team_abb`, `team_home`, `team_away`).
- Joining ramirobentes FGA rows (msg_type 1/2) to shufinskiy `shotdetail_2004` on
  `game_id + event_num = GAME_EVENT_ID`: 197,626 / 197,626 joined, 0 shooter or
  made/missed mismatches, each abbreviation maps to exactly one `TEAM_ID`.
- `msg_type = 99` rows ("Last possession of quarter", 1,297 rows) are **synthetic rows
  added by ramirobentes** (`event_num = 9999`, `number_event = x.5`); not NBA events.
- On a substitution row, `lineup_home/away` already shows the **post-sub** lineup.
- `number_event` is ramirobentes' ordering (non-contiguous because of the .5 rows).

Decisions:
1. **team_id comes from shufinskiy shotdetail** via the join above, stored in
   `core.team_xref (source, season_end_year, source_team_key, team_id, team_name, method='auto')`.
   Every abbreviation must map to exactly one team_id per season, else the pipeline fails.
   `core.teams` is rebuilt from team_xref using the most recent season's abbreviation/name.
   *(team_xref is a new table, the team analogue of player_xref.)* **[待確認]**
2. **Synthetic msg_type 99 rows are excluded from `core.events`** (counted and reported,
   not silent). They stay in the raw file. A msg_type 99 row whose event_num ≠ 9999 fails. **[待確認]**
3. `event_seq` = our own 1..n per game, ordered by ramirobentes `number_event`, after
   excluding synthetic rows. `source_event_num` = NBA `event_num`.
4. `events` gets three columns beyond the v0 schema: `clock` (display only, as CLAUDE.md
   conventions allow), `source_msg_type` (raw NBA msg type, so `other` stays traceable),
   and `source`. `event_subtype` = NBA action-type code (INTEGER, e.g. FT 11 = "1 of 2").
   `stint_id` / `possession_id` are NULL until Phase 3–4. **[待確認]**
5. Event type mapping (msg_type → ours): 1 shot_made, 2 shot_missed, 3 free_throw,
   4 rebound, 5 turnover, 6 foul, 7 violation, 8 substitution, 9 timeout, 10 jump_ball,
   11 other (ejection), 12 period_start, 13 period_end, 18 other (instant replay).
   Any other msg_type fails the pipeline.
6. `secs_elapsed_game` is computed by us from `period + clock` (OT = 300 s) and compared
   to the source `secs_game` as an extra validation check (101).
7. `points` = `shot_pts` on shot_made / free_throw rows, 0 otherwise.
   `games.home_score/away_score` = `hs/vs` on the game's last event.
   Note: check 2 then compares two columns of the same source (shot_pts vs running score).
8. **Lineups**: stored as `staging.event_lineups (game_id, event_seq, home_player_ids[], away_player_ids[])`
   exactly as the source gives them (not 5 columns, so a bad row with ≠5 players is
   visible to check 3 instead of being forced into shape). This is source parsing only,
   **not** stint building. **[待確認]**
9. Players: `player_id` parsed from `"ID Name"` strings (player1/2/3, player_ft, lineups).
   `core.players` is rebuilt from `staging.player_names` (every (player_id, name) seen):
   `name` = name in the most recent season, `name_variants` = all distinct names.
   `player_xref.source_player_key` = the raw `"ID Name"` string, `method='auto'`.
   Coach / team-level actors → `player_id` NULL.
10. Code layout additions: `src/nba_platform/db.py` (connection + DDL from `sql/schema.sql`),
    `src/nba_platform/pipeline.py` (stage → load → validate CLI). DuckDB schemas:
    `core`, `staging`, `validation`. **[待確認]**
11. Corrections (`corrections/corrections.csv`) are applied to the raw DataFrame in the
    ramirobentes adapter, matched on `game_id + source_event_num + field` (raw column name);
    `old_value` must equal the current value or the pipeline fails.
12. Check 1 expected regular-season game counts are **reference numbers from general
    knowledge, not from data**: 1189 (29 teams, 1996-97 → 2003-04), 1230 (30 teams),
    1998-99 725, 2011-12 990, 2012-13 1229, 2019-20 1059, 2020-21 1080. **[待確認]**
13. Check 5 (player minutes vs box score) is **skipped**: no box score source loaded yet.

## 2026-10-16 — Possession rules decided by owner

Owner decisions (confirmed). CLAUDE.md "Possession rules" and "Core schema" updated;
all tunable values in `config/rules.yaml`.

1. **End-of-period possessions** — decided. pbpstats approach: a possession starting with
   ≤ `end_of_period_threshold_secs` (default 2, in rules.yaml) left in the period and
   scoring 0 points is excluded from efficiency. All possessions are kept, flagged
   `is_end_of_period_heave`.
2. **Substitution during a possession (incl. between FTs)** — **open**. Data must keep
   three options computable: (A) credit to the lineup on court when the possession ends;
   (B) FT points to the lineup on court at the time of the foul; (C) Cleaning the Glass
   chance split. Therefore: events map to the on-court lineup (`stint_id`), free throws
   record their fouling event (`foul_event_seq`), chance boundaries are recorded (`chance_id`).
3. **Offensive rebound** — decided. Does not end the possession; record `num_chances`
   per possession.
4. **Flagrant foul** — decided. FT trip and the retained possession are two possessions
   (pbpstats).
5. **Technical FTs** — decided. Do not start/end a possession; count in team points; event
   flag `is_technical_ft`; excluded by default from lineup efficiency and RAPM.
6. **Garbage time** — decided as a flag. `is_garbage_time` uses the Cleaning the Glass
   definition; exclusion decided at RAPM time. Each possession stores start margin
   (offense perspective), game seconds remaining, period, offense_is_home, so a
   leverage-style definition can replace it later.
7. **Possession start type** — decided. `after_made_shot`, `after_defensive_rebound`,
   `after_steal` (live-ball TO), `after_dead_ball_turnover`, `after_free_throw`,
   `period_start`; plus flag `is_after_timeout`.
8. `possessions` gets a `rules_version` column. All thresholds/definitions in
   `config/rules.yaml`, not in code.

Unchanged (still proposed): team rebound after a non-final missed FT; jump ball / held ball.

Follow-ups noted by Claude:
- The exact Cleaning the Glass definitions (garbage-time thresholds, starters condition,
  whether garbage time stays on once triggered; chance boundaries beyond offensive
  rebounds) were written into rules.yaml from memory and must be verified against CTG's
  published glossary. **[待確認]**
- `config/` directory added to the CLAUDE.md layout.

## 2026-10-16 — Reviewer corrections adopted by owner

Owner decisions (confirmed), from an external review of CLAUDE.md. CLAUDE.md updated.

**Schema**
1. A possession can span several stints: `possessions` no longer has a single `stint_id`;
   new table `possession_stint_segments (game_id, possession_id, segment_seq, stint_id,
   start_event_seq, end_event_seq, start_secs, end_secs)`. `events.stint_id` stays.
2. `possessions` distinguishes `offense_team_id` from `scoring_team_id` (a technical FT
   may be shot by the defense).
3. Definition: the lineup on a substitution event's row is the lineup **before** the sub.
4. Possession end: only a **made** final FT ends the possession; after a missed final
   FT the rebound decides (offensive rebound → possession continues).

**Validation levels**
- Hard fail (stop, no results): unidentifiable core IDs, duplicate event unique keys,
  duplicate player within a lineup, game time out of range, unexpected many-to-many join
  inflation.
- Warning (report, continue): small PBP vs box-score minute differences, possession
  counts disagreeing across sources, missing shot coordinates, end-of-period special events.
- All anomalies go to reports in `docs/validation/`; data is never silently deleted.

**Other**
1. RAPM: no preset λ range; λ by cross-validation grouped by game; data supports both
   possession-level and stint-level observations.
2. Phases 7–8 "integration" = exchanging data through shared game_id / player_id /
   team_id, not merging repos. Video needs its own sync layer; only the interface is
   reserved now.
3. DuckDB is written only by the ingestion pipeline; DBeaver / Streamlit open it read-only.
4. Every raw download is recorded in `data/raw/manifest.csv` (url, downloaded_at, sha256);
   the manifest is committed (exception to rule 5).
5. Working agreements 9–12 added (definitions separate from code; keep event-level
   detail; don't bend logic to match references; separate facts / source values /
   assumptions, record rules version).
6. overnight_plan.md: checkpoint on game 0020400027 before the full 2004-05 run; compare
   2025-26 vs 2004-05 column formats before scaling to all seasons.

Follow-ups noted by Claude:
- **Source vs. definition (sub-row lineup):** in ramirobentes the `lineup_home/away`
  on a substitution row is already the **post-sub** lineup (observed on 2004-05, e.g.
  game 0020400027 event_seq 32). Under the new definition, the sub row belongs to the
  pre-sub lineup, so stint building must take the lineup of the previous event for sub
  rows. Staging keeps the source lineups unchanged (fact), and this difference is
  documented rather than silently "fixed". **[待確認]**
- **scoring_team_id on a possession:** one possession can contain points by both teams
  (e.g. offense scores, defense makes a technical FT). A single `scoring_team_id` column
  cannot express that; options are a points-per-team child table or separate
  offense/defense point columns. Not decided. **[待確認]**
- **Numbered checks 1, 2, 3 (count ≠ 5 without duplicates), 4, 6, 11** were not
  classified by the review. Until the owner decides, they are treated as **warnings**
  (reported, not stopping), consistent with the overnight plan's "list failing seasons
  in the report, don't force them to pass". **[待確認]**
- `.gitignore` must be changed so `data/raw/manifest.csv` is tracked while the rest of
  `data/` stays ignored; download.py must write the manifest. To be done when work resumes.

## 2026-10-17 — Phase 1 implementation details (overnight run)

1. **Validation levels implemented.** Hard checks run *inside* the load transaction;
   any failure rolls the season back (nothing loaded) and is reported:
   0 staging mapping (StagingError), 9 IDs resolve, 102 unique event keys,
   104 no duplicate player in a lineup, 105 game time in range, 106 loaded rows = staged
   rows (no join inflation). Everything else is a warning (loaded + reported):
   1, 2, 3 (count ≠ 5), 4, 6, 10, 101. Check 5 = skip. **[待確認]** for 1, 2, 3, 4, 6.
2. Reports: `docs/validation/season_report.md` (one row per season) and
   `docs/validation/details/{season_type}_{year}.md` (every check, with examples).
3. Playoffs have no schedule source, so check 1 for playoffs verifies **series
   structure** from game IDs (`004YY00RSG`): each series ends with one team at 4 wins
   (3 in best-of-5 first rounds through 2001-02) and no game after the clincher. **[待確認]**
4. `data/raw/manifest.csv`: the three 2004-05 files predate the manifest, so their
   `downloaded_at` was backfilled from the file modification time and the `note` column
   says so (observed fact, not an invented timestamp).
5. `.gitignore` now uses `/data/*`, `!/data/raw/`, `/data/raw/*`, `!/data/raw/manifest.csv`
   (verified with `git check-ignore`).
6. Single-game checkpoint: `python -m nba_platform.pipeline --season-end-year 2005
   --game-id 0020400027 --db :memory:` (staging written to `data/staging/_checkpoint/`,
   check 1 skipped because a single game has no schedule).
7. The overnight run continued after the owner's "更新完就停下來" message because the
   owner's `/goal` (complete steps 0–5) was still active; the interpretation was "do not
   start extra work because of that message". **[待確認]**

## 2026-10-17 — Step 3 (all seasons) decisions

1. **DuckDB moved out of the synced folder for the overnight run.** The project folder
   (under Desktop) is managed by a cloud-sync client (files carry a Cloud Files reparse
   point with a `sync_id`). The sync client rewrote `data/nba_platform.duckdb` behind
   DuckDB's back: the file shrank to 29 MB with a LastWriteTime older than the last
   write, and DuckDB could no longer open it ("could not read … location 69218304").
   `db.py` now honours `NBA_PLATFORM_DB`; the overnight build lives at
   `%LOCALAPPDATA%\nba_platform\nba_platform.duckdb` (never synced). Default path unchanged.
   The corrupted file was left in place, untouched, for the owner to inspect. **[待確認]**
   Note for the owner: the sync client is also uploading `data/` (raw third-party files)
   to cloud storage. Not git, but worth knowing given rule 5.
2. 2025-26 introduces msg_type 22 (Heave), 92 (Block row), 93 (Game End), 95 (Steal row).
   All mapped to `other`; `source_msg_type` keeps the code. **[待確認]**
3. player1/2/3 roles differ by era (jump ball: 2004-05 player1 = jumper, 2025-26 player1
   = tip receiver; blocker on a miss: player3 → player2). Copied as given; documented in
   `docs/validation/format_diff_2004-05_vs_2025-26.md`. **[待確認]**
4. ramirobentes `locX/locY` (2020-21+) are 0–100 court-percentage coordinates, not
   shotdetail tenths of feet. Because shufinskiy shotdetail exists for **every** season
   1996-97 → 2025-26 (regular + playoffs), `core.shots` uses shufinskiy only; the
   ramirobentes fallback in the plan was never needed and coordinates are not mixed.
5. Play-in games (`005…`) are not in either source's playoff files; not loaded.

## 2026-10-17 — Step 4 (Phase 3 prep) notes

1. `validate/phase3_prep.py` reads raw files only and uses **reference** possessions
   (ramirobentes' own `possession` / `start_poss` columns, pbpstats possessions). It is
   not possession logic and lives outside `core/`.
2. pbpstats rows are one per event; a pbpstats possession = distinct
   (GAMEID, OPPONENT, PERIOD, STARTTIME, ENDTIME, STARTTYPE, STARTSCOREDIFFERENTIAL, EVENTS).
   OPPONENT = the defense.
3. Finding: at ≥ 3 s left the two references agree second by second; at 0–2 s
   ramirobentes has ~1,455 more 0-point possessions, ≈ the season-total gap (+1,429).
   Inference (not verified): pbpstats already drops end-of-period 0-point possessions,
   so pbpstats should be compared with our counts **after** that exclusion. **[待確認]**
4. `docs/possession_rules.md` keeps CLAUDE.md's statuses (decided / open / proposed)
   instead of "all proposed", because the owner decided most rules after the plan was
   written. **[待確認]**
5. `pyyaml==6.0.3` added to requirements (rules.yaml loader `nba_platform/rules.py`).

## 2026-10-17 — Step 3 fixes after the first all-seasons run

The first run (old code) hard-failed many seasons. Each cause was investigated before
changing anything:

1. **Ties in ramirobentes `number_event`** (1996-97, 1997-98, 1999-00, …, 2025-26
   playoffs): different events (different NBA `event_num`) share one `number_event`
   (e.g. 1996-97 had 4 such pairs). This is not a duplicate of *our* unique keys
   (`event_seq`, `source_event_num`), so it is no longer a hard fail: ties are ordered by
   `event_num` (the NBA's own event number) and every tied row is reported in warning
   check **109**. **[待確認]**
2. **msg_type 0 ("Game End") and 20 ("Stoppage: Out-of-Bounds / Injury / Blood Rule /
   Equipment / Court Cleanup / Other")** appear 2017-18 → 2024-25. No team, no player, no
   points. Mapped to `other`. **[待確認]**
3. **Team xref join noise** (2017-18: 7 of 7,178 NOP shots joined to Toronto's TEAM_ID):
   an abbreviation now maps to the TEAM_ID behind ≥ 99 % of its joined shots
   (`TEAM_XREF_MIN_SHARE`); the minority is reported in warning check **110**. Below
   99 % it is still a hard fail. **[待確認]**
4. **2014-15 regular season stays a hard fail**: game `0021401022` (2OT) has 48 lineup
   values whose player key has no ID (`NA <name>`; proposed ID 202711). Not fixed automatically (rule 6: never
   invent IDs). `docs/validation/proposed_corrections.csv` lists 48 proposed rows
   (ID 202711, the only ID in that file whose accent-insensitive name matches); they take
   effect only if the owner copies them into `corrections/corrections.csv`. **[待確認]**
5. **Playoff series check rewritten**: older playoff game IDs are sequential
   (`004YY000GG`), so a series is now the unordered team pair; round 1 = the 8 series
   that start first; 15 series expected.
6. `validation.results` now keeps only the latest run per season (a re-run replaces all
   of that season's rows), so a fixed season does not keep a stale failure.
7. 2025-26 `0022500029`: one made FT (`shot_pts = 1`, "(1 PTS)") does not change the
   running score, so event points (115) ≠ final home score (114). Source contradiction;
   reported (check 2), not changed.
8. **2000-01 regular season stays a hard fail** (second run): game `0020000409` has the
   NBA event `event_num` 435 (msg 6 foul, act 14 flagrant type 1, 02:04) **twice**. The two rows
   differ only in ramirobentes-derived FT attribution columns (`total_fta` 2 vs 1,
   `player_ft` two different players, `shot_pts_home` 2 vs 0). This duplicates our
   unique key (`game_id, source_event_num`) → hard fail by the review's rule. Not
   de-duplicated automatically (which row is right is a judgement call; corrections.csv
   cannot delete rows). Owner to decide: e.g. add a `drop_row` correction type. **[待確認]**
9. **Systematic: duplicated foul rows in ramirobentes** (scan of all 60 files,
   `docs/validation/duplicate_source_events.csv`): 8 NBA events in 7 regular-season files
   (2000-01, 2002-03, 2003-04, 2011-12, 2012-13 ×2, 2017-18, 2019-20) appear twice. Every
   pair differs **only** in ramirobentes-derived FT-attribution columns (`player_ft`,
   `poss_home/away`, `shot_pts_home/away`, `total_fta`), none of which we load. In every
   column of `core.events` the two rows are identical. They still duplicate our unique key,
   so these seasons stay **hard fails**; the hard check was not loosened overnight.
   Suggested owner decision: allow dropping a duplicate *only if identical on every loaded
   column*, reported per row. **[待確認]**

## 2026-10-17 — Step 5 note

1. Validation reports and the possession-rules draft quote small excerpts of source rows
   (event descriptions, lineup strings, game IDs) as evidence. Committed locally only (no
   remote, no push). Owner to confirm this is acceptable under rule 5 before publishing,
   or ask for excerpts to be replaced by IDs only. **[待確認]**

## 2026-10-17 — Plan 2026-10-17, step 1: database location and privacy (owner decisions)

1. **Database default path is now `%LOCALAPPDATA%\nba_platform\nba_platform.duckdb`**
   (owner decision; resolves the [待確認] in "Step 3 (all seasons) decisions" item 1).
   `NBA_PLATFORM_DB` remains an optional override; pipeline and pytest work without it.
   CLAUDE.md tech stack and layout updated. Fallback when `LOCALAPPDATA` is unset:
   `~/.local/share/nba_platform/`.
2. The corrupted in-project `data/nba_platform.duckdb` was deleted (derived file).
3. The sync client is Synology Drive (owner confirmed, paused). README now tells users of
   sync tools to exclude `data/`, `.venv/`, `*.duckdb`.
4. `docs/validation/details/` is git-ignored (removed from the index; the files stay
   local). Committed summaries carry IDs, codes and numbers only: possession-rule
   sequences show `player1_id` instead of descriptions, `duplicate_source_events.csv`
   and `proposed_corrections.csv` were regenerated without source text, season-report
   failure reasons drop quoted values, and source descriptions were removed from
   decisions / progress log / reports. Earlier commits still contain the old text; git
   history was **not** rewritten. **[待確認]**
5. The "stop after the update" interpretation (Step 1 implementation details, item 7) is
   **resolved: the interpretation was correct** (owner, 2026-10-17).

## 2026-10-17 — Plan 2026-10-17, step 2: conditional corrections (owner rules)

1. **Duplicated source events — owner rule: drop one copy only if identical in every raw
   column (event_num included); reason `source exact duplicate`.** Implemented as a
   corrections.csv row `field = __row__, old_value = exact_duplicate, new_value = drop_one`;
   the adapter re-checks that the copies are identical in every column and fails
   otherwise. Result: **0 of 8** duplicated events qualify (all differ in
   ramirobentes-derived FT columns), so **no row was dropped**; all 8 are listed in
   `docs/validation/conditional_corrections.md`. The 7 affected seasons stay hard fails.
   (Resolves "Step 3 fixes" items 8–9 by the owner's rule.)
2. **2014-15 missing player IDs — owner rule: apply only if all 48 rows agree with the
   BigDataBall file of that game.** BigDataBall `play_id` = NBA `event_num` (period and
   clock also checked). Result: **48 / 48 consistent** (same five home players at each
   event, including the proposed player 202711) → 48 rows appended to
   `corrections/corrections.csv`, reason "missing player ID; proposed ID confirmed by
   BigDataBall lineup at the same event". (Resolves "Step 3 fixes" item 4.)
3. BigDataBall 2014-15 (1,312 files, placed by the owner) recorded in
   `data/raw/manifest.csv` with origin "local purchase: BigDataBall (not downloadable)",
   `downloaded_at` = file mtime, SHA-256.
4. **Garbage time — confirmed (owner, CTG official): retroactive.** A possession is
   garbage time only if the condition holds from it through the end of the game; a
   stretch where the margin falls back below the threshold does not count.
   `config/rules.yaml`: `stays_on_once_triggered: null` → `retroactive_until_game_end: true`;
   `rules_version` → `2026-10-17.1`. The numeric thresholds and the starters condition
   remain **[待確認]** (still from memory). 2004-05 share: 1.75 % of possessions.
5. The "stop after the update" item is resolved (see step 1 entry, item 5).

## 2026-10-17 — Plan 2026-10-17, steps 4–5 notes

1. Check 5 tolerances live in `config/rules.yaml` (`validation:` section): rounding
   tolerance 1 min, "large" above 5 min. Check 5 stays warning level.
2. 2004-05 → 2006-07 box-score minutes appear "balanced" to the team total (only 4.6 % of
   2004-05 team-games miss 5 × game length, vs ~55 % normally): inference, not verified.
3. BigDataBall `play_id` is the NBA event number but **not monotonic** in the files;
   the final score is taken from the last row of the file. With that, 0 / 1,311 final
   scores differ.
4. BigDataBall → NBA player_xref rules (both recorded as `method = auto`): `name`
   (accent/case/punctuation-insensitive name of exactly one player in that team's aligned
   lineups) and `lineup` (single leftover name ↔ single leftover ID in every aligned
   lineup, ≥ 10 times). 480 by name, 8 by lineup, 4 unmatched and listed with their
   candidate IDs — not guessed. **[待確認]** whether the `lineup` rule is acceptable as
   `auto`, and whether to add the 4 as `manual`.
5. `rebuild_reference_tables` now deletes/rebuilds only the `player_xref` rows of sources
   that feed `staging.player_names`, so BigDataBall rows survive reloads.
6. Check 11 recorded in `validation.results` (warning) for the seasons BigDataBall covers.

## 2026-10-17 — Plan 2026-10-17, step 6: shot quality flags

1. New column `core.shots.quality_flags` (TEXT, comma-separated, NULL = none), added with
   `ALTER TABLE … ADD COLUMN IF NOT EXISTS`; shot inserts now use `BY NAME`. Owner
   authorized the flag in the plan; no shot is deleted or changed.
2. `xy_zero_placeholder`: shot exactly at (0, 0) in a season where > 5 % of shots are at
   (0, 0) (threshold in rules.yaml). 1996-97 → 2009-10 have 22–36 % of shots at (0, 0) with
   distance 0; from 2010-11 on 0 %. Inference: (0, 0) is a placeholder for close shots.
3. `early_season_location_suspect`: every shot of 1996-97 → 1999-00 (Sports Reference
   warning; seasons listed in rules.yaml). Evidence: 9–10 action types (vs 25–29 later),
   1996-97 layup share 29 % (vs 21–23 %).
4. Flags are set by `python -m nba_platform.validate.shot_quality` and must be re-run after
   any `pipeline --all` (a reload inserts shots with NULL flags). **[待確認]** whether
   to call it from the pipeline automatically.

## 2026-10-17 — Plan 2026-10-17, step 7: pbpstats reference

1. New schema `reference` with `reference.pbpstats_possessions` (one row per pbpstats
   possession, no event text). Loaded by `python -m nba_platform.reference.pbpstats`;
   never used to build our possessions. New package `src/nba_platform/reference/`.
2. pbpstats files exist for 2000-01 → 2024-25 only (50 files, regular + playoffs).
3. **Finding:** ramirobentes' 2024-25 playoffs file lacks game `0042400231` (present in
   pbpstats and in the nba_api box scores). The series-structure check could not see it
   (the series winner still had 4 wins). **Check 1 now also compares our game IDs with the
   nba_api box-score game list** when cached; that season now fails check 1 (warning).
   All other 52 loaded seasons match the box-score game list exactly.

## 2026-10-18 — Plan 2026-10-18, step 1: duplicated events verified against the official PBP

1. Owner rule: drop one copy of a duplicated event only if (a) the copies differ only in
   ramirobentes-derived columns and (b) the official PBP (shufinskiy `nbastats_*`) has
   that event number exactly once in the game. Reason: "source duplicate verified against
   official PBP".
2. The ramirobentes-derived columns are listed in code (`RB_DERIVED_COLUMNS`): player_ft,
   team_ft, total_fta, type_foul, possession, poss_home, poss_away, start_poss,
   shot_pts_home, shot_pts_away, secs_played, and1, garbage_time, margin_before,
   total_starters_home/away, reb_type, off_team_abb. `shot_pts` is treated as an NBA field
   (conservative: it feeds our points). **[待確認]** that this list is complete/acceptable.
3. New correction kind: `field = __row__, old_value = derived_only_duplicate, new_value =
   drop_one`; the adapter re-checks that the copies differ only in derived columns and
   keeps the first copy (by ramirobentes order).
4. Result: **8 / 8** events meet both conditions (each official count = 1) → 8 corrections.
   Report: `docs/validation/duplicate_verification.md`.

## 2026-10-18 — Plan 2026-10-18, step 2: known gaps and source contradictions

1. `corrections/known_gaps.csv` (committed, like corrections) lists documented gaps; the
   pipeline re-applies it after every season load → `core.known_gaps` (new table) and two
   new `core.games` columns: `pbp_missing` (BOOLEAN) and `known_issue` (TEXT). Schema
   change authorized by the plan.
2. `0042400231` (2024-25 playoffs, MIN 88 – GSW 99, 2025-05-06): game row built from the
   nba_api box score (teams = MATCHUP "vs." / "@", score = sum of player points),
   `source = nba_api_box`, `num_periods` NULL (unknown), `pbp_missing = TRUE`, no events.
3. `0022500029` (2025-26): `known_issue = source_score_conflict`.
4. New status `known` (rendered "⚠ known"): check 1 is `known` when the season is complete
   only thanks to a known pbp_missing game; check 2 is `known` when every mismatch is a
   known contradiction. Checks 2, 5 and 6 skip `pbp_missing` games (they have no events).
   New info check 111 lists the gaps applied per season.

## 2026-10-18 — Plan 2026-10-18, step 3: minutes differences

1. **Known source phenomenon (inference, not verified):** box-score minutes of 2004-05 →
   2006-07 (regular) and 2003-04 → 2005-06 (playoffs) look "balanced" to the team total
   (e.g. only 4.6 % of 2004-05 team-games miss 5 × game length vs ~55 % normally), which
   pushes single players ±1–2 min. Check 5 stays a warning; not investigated further.
2. Player-games with |diff| > 5 min were investigated (report only,
   `docs/validation/minutes_large_diff.md`). Classification rules in
   `validate/minutes_large_diff.py`; every class is an inference.
   - 2005-06 (110): all 110 `box_likely_wrong` — the team box totals of those games are
     short by a median of 90 min, and BigDataBall's lineups give minutes within 1 min of
     our PBP in **110 / 110** (within 1 min of the box score in 0).
   - 2006-07 (243, no BigDataBall): 237 `box_likely_wrong` (team box totals short),
     2 swapped with a teammate, 4 undetermined.
   - 1996-97 (16): 7 swapped with a teammate, 6 box likely wrong, 3 ramirobentes lineup
     likely wrong (a period-start stretch without a logged substitution matches the gap).
3. BigDataBall 2005-06 (1,561 files) recorded in the manifest. 247 files are browser
   duplicates named "… (n).csv"; all 247 are byte-identical (same SHA-256) to the original
   and are ignored by the adapter's file-name rule.

## 2026-10-18 — Plan 2026-10-18, step 4: (0, 0) means the rim

1. Owner: in NBA shot-chart coordinates (0, 0) is the rim; a shot there is an at-the-rim
   attempt with an imprecise spot, not missing data. Data agrees: 96–100 % of (0, 0) shots
   are layups / dunks / tip-ins in every season, and none has a distance > 0.
2. Flag `xy_zero_placeholder` renamed **`rim_location_imprecise`** (same rule: (0, 0) in a
   season with > 5 % of shots there). New flag **`rim_location_suspect`**: (0, 0) and a jump
   shot, a 3-pointer or distance > 0 (any season) — 2,860 loaded shots.
3. Flags moved from the `core.shots.quality_flags` column (dropped) to the new table
   **`core.shot_quality_flags`** (game_id, source_event_num, flag) so reloads keep them —
   this also covers the storage part of plan step 7.

## 2026-10-18 — Plan 2026-10-18, step 5: CTG garbage time — checked against the official definition

1. **Garbage-time definition: checked by the owner against Cleaning the Glass's official
   text (2026-10-18) — confirmed.** 4th quarter only; margin ≥ 25 with 12–9 min left, ≥ 20
   with 9–6, ≥ 10 with ≤ 6; at most 2 of the game's starters on the floor combined;
   retroactive (only the stretch that lasts to the end of the game counts). Replaces the
   earlier [待確認] on thresholds and starters.
2. Program vs definition: period, thresholds and the retroactive rule already matched.
   The starters condition used ramirobentes' `total_starters_*` (undocumented); it now uses
   **our own count** of the game's starters (lineup on the game's first event) on the floor
   at the possession start. It equals the source column on 100.00 % of 2004-05 possessions,
   so the 2004-05 share is unchanged (1.75 %). `rules_version` → `2026-10-18.1`.
3. Boundary convention (not stated in the definition): exactly 9:00 / 6:00 left fall in the
   lower-threshold band (≥ 20 / ≥ 10). **[待確認]**

## 2026-10-18 — Plan 2026-10-18, step 6: definitions (owner decisions)

1. **(a) Substitution-row lineup = the lineup _after_ the substitution** (same as
   ramirobentes); **every substitution starts a new stint.** This **overturns the reviewer's
   definition** ("lineup before the substitution", 2026-10-16). Owner's reasons: a
   substitution row carries no statistics of its own; matching ramirobentes removes a
   conversion layer; "each substitution starts a new stint" is the most common definition.
   Resolves the [待確認] "Source vs. definition (sub-row lineup)".
2. **(b) Scoring storage.** The events table is the single source of points: each scoring
   event records the scoring team and the ten players on court and carries
   `is_technical_ft`. `possessions` drops `scoring_team_id` and keeps one `points` column =
   the offense's points in the possession, technical FTs excluded. No `def_points`; team
   totals are sums over events. Lineup efficiency = lineup points on court ÷ lineup
   possessions; technical FTs excluded by default, a switch includes them. Resolves the
   [待確認] on `scoring_team_id`.
3. **(c) Design check** (`docs/validation/scoring_attribution.md`, 2004-05 and 2024-25):
   scoring events by the team not on offense (ramirobentes reference possessions) are
   technical FTs **and** non-technical FTs, so by the plan's rule the design is **not**
   declared valid and is **not** changed. **[待確認]** Breakdown: 8,146 and-1 free throws
   (the reference ends the possession on the made FG, so the and-1 FT falls in the next
   possession — under CLAUDE.md's rule they belong to the shooter's possession; inference:
   a reference artifact), 3 FTs at a period boundary, 2 "other" (listed by game / event).
4. **(d)** `docs/possession_rules.md` (generated by `validate/phase3_prep.py`) gains notes on
   duplicate steal/block rows (2025-26), era-dependent player roles, the post-sub lineup
   definition, the pbpstats ≤ 2 s / 0-point removal (now stated as the owner's finding,
   no longer an inference) and pbpstats' hybrid substitution handling (reference, not a
   decision; case 2 stays open).
5. **(e) Development strategy "copy first, then deviate"** written into CLAUDE.md and
   possession_rules.md. `config/rules.yaml` now has `profiles: pbpstats_compat` (case 2 =
   pbpstats hybrid: possessions to the lineup at possession end, FT points to the lineup
   at the foul) and `custom` (technical FTs excluded; case 2 open). `load_rules(profile=…)`
   merges a profile over the shared values. pbpstats' treatment of technical FTs in lineup
   stats is unverified → `null` in `pbpstats_compat`. **[待確認]**

## 2026-10-18 — Plan 2026-10-18, step 7: automation

1. `pipeline --all` ends with `post_load`: shot-quality flags (`validate/shot_quality.run`)
   and the BigDataBall cross-check (`validate/bdb_crosscheck.run`), on the pipeline's own
   connection. A failing step is printed and recorded (`validation.results`, season 0,
   type `post_load`) without hiding the load results; the next good run clears it.
2. Shot-quality flags live in `core.shot_quality_flags` (done in step 4), so reloads keep them.
3. Pre-commit hook `scripts/git-hooks/pre-commit` (versioned) runs the full pytest suite and
   blocks the commit on any non-zero exit (failures **and** collection errors). Installed
   with `git config core.hooksPath scripts/git-hooks`; verified by a probe commit with a
   failing test, which was blocked.

## 2026-10-18 — Plan 2026-10-18, step 9: BigDataBall lineup arbitration (report only)

1. `validate/bdb_arbitration.py`, called by the BigDataBall cross-check: a disagreement run =
   consecutive aligned events of one team (our event order) where the two lineups differ.
   Evidence per run: (1) box-score minutes of the players on court in only one source, per
   source; (2) official PBP substitutions (shufinskiy `nbastats_*`) inside the run window.
   Runs are counted in our event order per team, so the totals differ from the earlier
   file-order count (e.g. 2014-15: 216 runs, earlier 591). Verdicts are inferences.
2. BigDataBall now has 7 seasons (the owner added 2004-05, 2007-08, 2010-11, 2012-13,
   2013-14); all recorded in the manifest and cross-checked.
3. Result: in every season most decidable runs favour **ramirobentes** (e.g. 2014-15:
   215 of 216; 2007-08: 183 of 205); BigDataBall is right in 6 runs (2005-06). Nothing changed.

## 2026-10-18 — Overnight batch preparation

1. **Bug fixed — `core.team_xref` lost regular-season teams.** Loading a playoffs file
   deleted the whole season's xref (`source + season_end_year`) and re-inserted only the 16
   playoff teams. `core.teams` was unaffected (built from every season), but joins through
   `team_xref` missed teams. Fix: delete only the abbreviations being re-inserted. The main
   database was repaired by re-inserting both staging `team_xref.parquet` files per season
   (480 → 892 rows; every season now has 29–30 teams) and rebuilding the reference tables.
2. `scripts/overnight_batch.py`: one process, tasks A–H in order, isolated, resumable
   (state file), NBA.com serial 4–5 s + jitter, 30 s timeout, stop after 5 consecutive
   failures, raw JSON cached in `data/raw/nba_api/{category}/{season}/`. Reproducibility (A)
   rebuilds into a **separate** database (`%LOCALAPPDATA%\nba_platform\rebuild_check.duckdb`)
   so the main database and its reference tables are never dropped. **[待確認]**
3. NBA.com TeamGameLogs (Advanced) returns all game types in one request; rows are labelled
   by game-ID prefix (002 regular, 004 playoffs, 001 preseason, 005 play-in, 003 All-Star,
   006 Cup final). Possessions are compared via `core.games` team IDs.
4. Single-game boxes (H): tracking from 2013-14, hustle from 2015-16; newest season first;
   empty shells are counted, not treated as errors; per-period data is not downloaded.
5. `logs/` is git-ignored (local run logs and summaries).

## 2026-10-18 — Possession-count reference (owner decision)

1. **The main reference for the possession code is pbpstats (2000-01 → 2024-25).**
   ramirobentes' possession columns are inconsistent across eras and are reference only.
2. Evidence (supported inference): the 2016-17 break comes from ramirobentes' processing
   pipeline (its README: new pipeline from 2016-17; 2020-21 playoffs used the old one).
   2020-21 playoffs vs pbpstats 94.1 % exact / vs NBA official 58.8 % — the pre-2016 pattern;
   2020-21 regular season 78.2 % / 91.3 % — the post-2016 pattern.

## 2026-10-18 — Overnight batch v2 (owner decisions)

1. NBA.com requests 7–8 s apart (random jitter). After 5 consecutive failures: cooldown
   45 min, then 90 min (at most 3 cooldowns per night; a cooldown that would pass the
   deadline stops instead), then stop all NBA.com requests. Cooldowns are logged.
2. Priority: finish task F (remaining shot context, all play types), then single-game
   tracking + hustle boxes for every available season's playoffs (newest first), then
   2025-26 and 2024-25 regular season. No other regular seasons. Deadline 08:00.
3. Summary: at most 10 lines per task; per-season tables live in the validation reports
   (`docs/validation/possession_benchmark.md`, `bigdataball_crosscheck.md`), linked.
4. Finished tasks of the 2026-10-18 run are reused (A–E); G re-runs (cheap; a trial run
   leaves its table partial).

## 2026-10-19 — NBA.com planned rests (owner decision)

1. The 5 missing play-type requests (2019-20 regular) were fetched: task F is complete
   (1,936 / 1,936; play_type 109,118 rows).
2. Besides the cooldown rule, the client now rests 30 min after every 600 requests sent
   (logged; a rest that would pass the deadline stops the NBA.com requests instead).
   Rest length 30 min chosen conservatively. **[待確認]**

## 2026-10-19 — Matchups playoffs

1. `reference.matchups` now holds regular season **and playoffs** (`matchups_po_2017` …
   `matchups_po_2024`, `season_type = 'playoffs'`): 1,886,689 rows, 10,076 games, 100 % of
   game IDs found in `core.games`.
2. shufinskiy also has `matchups_2025` / `matchups_po_2025` (2025-26). Not downloaded — same
   range as the original plan (2017 → 2024). **[待確認]**

## 2026-10-20 — Keys, relationships and the dashboard plan

1. **No new PRIMARY / FOREIGN KEY constraints on the big tables** (`core.events`,
   `core.shots`, `staging.event_lineups`) and no foreign keys anywhere: the pipeline reloads a
   season by delete-then-insert, DuckDB foreign keys have no cascade, and the indexes are
   costly at 17.5 M rows. Uniqueness and references stay hard-fail validation checks
   (9, 102, 104, 106, 107). The logical model is documented in `docs/data_model.md`; new
   small `marts.*` tables get real PRIMARY KEYs. Existing schema unchanged. **[待確認]**
2. **Dashboard in three layers** (basics → on/off and tracking-based metrics → RAPM/EPM-style),
   draft in `docs/dashboard_spec.md`. Layer 1 first because it needs no possession data. The
   official box score is what the site shows; our own play-by-play box score is used only to
   validate the events table (`docs/validation/box_vs_pbp.md`). Until our possessions exist,
   team pace and ratings come from NBA's official `POSS`, labelled *official*.
3. Publishing the site (data terms of ramirobentes / NBA.com) is not decided; everything stays
   local. **[待確認]**

## 2026-10-21 — Shooting marts and dashboard thresholds

1. Zones are NBA's own `shot_zone_basic` labels; a shot without one is `Unknown`, not guessed
   (none exist today). Flagged shots stay in the counts; `flagged_share` is shown.
2. League percentiles only among players with at least 100 attempts in the season and type
   (and 20 in the zone for accuracy). Both numbers live in the new `dashboard:` section of
   `config/rules.yaml` (display thresholds, not basketball rules; `rules_version` unchanged).
   Chosen conservatively. **[待確認]**
3. Team defense shot mix counts the shots taken against the team (opponent = the other team of
   the game).

## 2026-10-21 — Tracking mart

1. `marts.player_tracking_season` shows a curated set of about 50 NBA.com columns in five groups
   (Movement, Touches & passing, Drives & shooting, Rebounding & rim defense, Hustle); a column
   shared by several measures comes from its home measure. Selection and grouping chosen
   conservatively. **[待確認]**
2. Regular-season tracking rows list a traded player once, under his last team, with full-season
   totals; the mart keeps that as delivered (no splitting by team). Per-game values divide by the
   tracking table's own games (`gp`, `hustle_gp`), not the box score's, because tracking misses
   some games (`docs/validation/tracking_vs_box.md`: tracking is never higher than the box score;
   lower for 5-44 % of regular-season player-seasons depending on the stat and season).

## 2026-10-21 — Possession rules decided by the owner (before writing the possession code)

`rules_version` → `2026-10-21.1`. CLAUDE.md, `config/rules.yaml` and `docs/possession_rules.md` updated.

1. **Team rebound after a non-final missed FT**: not a rebound; ignored (proposed → decided).
2. **Jump ball / held ball**: does not end a possession; possession changes only if the other
   team gains control, decided by the team of the next event that has a team (Dean Oliver's
   definition, also pbpstats). Not a new chance. (proposed → decided)
3. **Chance boundaries**: offensive rebounds only in the first version (confirmed).
4. **Event order**: the source order is used; no reordering rules in code; confirmed order
   errors become `corrections` rows.
5. **Non-technical FT between possessions** (`docs/pending_decisions.md` item 1; 0020400278
   event 200, 0022400105 event 501): option (a), treated like a technical FT, new event flag
   `is_between_possessions_ft` (schema: `ALTER TABLE core.events ADD COLUMN`).
6. **2025-26 msg 95 / 92 / 22 / 93 / 0 / 20**: stay `other`, ignored by the possession code
   (the earlier [待確認] in `format_diff_2004-05_vs_2025-26.md` is resolved).
7. **`is_after_timeout`**: any timeout in the dead ball between the previous possession's end
   and this possession's first event; the calling team is stored too.
8. **CTG garbage-time boundaries** at exactly 9:00 / 6:00: lower-threshold band (confirmed).
9. **Substitution credit in `custom`**: kept open on purpose; compare A/B/C after
   `pbpstats_compat` is validated.
10. **Technical FTs in `pbpstats_compat`**: stays `null` until pbpstats' own treatment is
    checked in its source / documentation (owner asked for that check first).
11. Working mode: Claude writes an implementation guide (order, interfaces, tests); the owner
    writes the possession logic; Claude reviews.

## 2026-10-21 — pbpstats' treatment of technical free throws (checked in its source)

Read from `dblackrun/pbpstats` (master), `pbpstats/resources/enhanced_pbp/free_throw.py`,
`stats_nba/free_throw.py`, `stats_nba/enhanced_pbp_item.py`:

1. **Lineup stats:** a made FT's points (`shot_value`) are added to the shooting lineup's
   plus-minus and subtracted from the other lineup (plus `OPPONENT_POINTS`), with no exception
   for technical FTs. The lineup is the one on the floor at the time of the foul
   (`event_for_efficiency_stats`: the `Foul` at the same clock, searched backward then forward,
   else the FT itself). → `pbpstats_compat.technical_ft`: `exclude_from_lineup_efficiency:
   false`, `exclude_from_rapm: false`, `credited_to: lineup_at_foul`. (`custom` keeps excluding.)
2. **Possessions:** a FT ends a possession only if it is made, `is_end_ft`, and not one of
   the exceptions (away-from-play, inbound foul, transition take foul, or a foul by the other
   team at the same clock). `is_end_ft` is built from "1 of 1 / 2 of 2 / 3 of 3", which a
   technical FT ("Free Throw Technical") does not contain, so a technical FT does not end a
   possession; `get_offense_team_id` also skips technical FTs. This is **inferred** from those
   lines, not stated in one place; same as our rule.
3. Worth knowing for the comparison with pbpstats: an **away-from-play** made FT and a made
   last FT **followed by a foul of the other team at the same clock** do not end a possession
   in pbpstats. Our two between-possession FTs (decision of 2026-10-21, item 5 above) are this
   pattern; the per-game comparison will show whether the counts differ.

## 2026-10-21 — Who writes the core code; stint definition

1. **Working agreement 1 changed at the owner's request:** Claude writes `core/` (stints and
   possessions); the owner decides every rule and reviews each step. Every basketball
   judgement stays a written rule (CLAUDE.md / `rules.yaml`) with tests.
2. **Stints** (`rules_version` → `2026-10-21.2`): consecutive substitutions at the same second
   with no other event between them form one stint (lineup after the last of them); an event
   between them (e.g. a free throw) keeps them apart, so every free throw keeps its own
   on-court lineup and credit options A/B/C stay computable. Every period starts a new stint;
   a stint ends at the next stint's start or at its period's end. Player IDs keep the source
   order (sorting can be done when lineup stats are built). Replaces "every substitution
   starts a new stint" (2026-10-18).
3. Order of work: stints, then possessions; one game (`0020400027`), then 2004-05; only the
   `pbpstats_compat` profile first; Claude stops after each step for review.

## 2026-10-21 — Stints built (step 1), checked on 2004-05

`src/nba_platform/core/stints.py` (`build_stints`, `player_seconds`, `period_bounds`), tests
`tests/test_stints.py`. Read-only dry run on 2004-05 regular season (not written to the database
yet): 1,230 / 1,230 games, 38,723 stints (31.5 per game; 33,711 start at a substitution run,
5,012 at a period start, **0** lineup changes without a substitution row), 1,523 zero-length
stints (substitutions between free throws at one second, kept on purpose). Every team-game's
5 × seconds equals the game length. Player seconds equal the earlier event-based accounting
(checks 5 and 6) in 24,951 of 24,955 player-games; the 4 others are one game, `0020400152`,
whose 4th-period start row is at 11:39: the event-based accounting gave those 21 s to the
lineup that ended the 3rd period, the stint rule gives them to the lineup that started the
4th. Source gap, reported, not corrected.

## 2026-10-21 — Stints written for 2004-05; free-throw trips and fouls (step 2)

1. `nba_platform.build_core --step stints` wrote `core.stints` (new table, PRIMARY KEY
   `(game_id, stint_id)`, `rules_version` per row) and `core.events.stint_id` for 2004-05
   regular season: 38,723 stints, 559,067 events, every event linked, every team-game's time
   equal to the game length. A reload of a season's events clears `stint_id`; build_core must
   run again (to be wired into the pipeline).
2. `src/nba_platform/core/free_throws.py` (`link_free_throws`, tests `tests/test_free_throws.py`):
   - Free-throw kinds from the NBA action-type code, the same in every season (checked on all
     60 season files): 10-15 regular, 16/21/22 technical, 18-20/27-29 flagrant, 17/25/26 clear
     path (17 = unnumbered, 2000-01 → 2006-07), 81 transition take (2025-26). An unknown code
     stops the build.
   - Foul codes that cause each kind: technical 11, 12, 13, 16, 17, 18, 19, 25, 30, 32, 33
     (33 = bench technical, 2023-24 →); flagrant 14, 15; clear path 9; transition take 31; code
     0 = rescinded foul, never linked; everything else regular.
   - Trips are tracked per (kind, team), so a technical FT in the middle of a regular trip does
     not cut it. A trip links to the nearest fitting foul of the other team (or a foul without a
     team) at the same second, before the trip first, else after; a foul feeds one trip; no
     fit → NULL.
   - Dry run (read-only): 2004-05 regular 100 % of 35,612 trips linked, playoffs 100 %; 1996-97
     regular 99.98 % (6 unlinked), playoffs 99.95 %; 2015-16 and 2025-26 ≥ 99.93 % before the two
     fixes below (rerun pending). Incomplete trips (e.g. 39 in 2004-05) are all "1 of 2" stopped
     by a lane violation (turnover or jump ball): real play, not a source error; the possession
     logic must end those possessions on the turnover / jump ball.
   - Fixes found by the dry run: fouls without a team (1996-97 team technicals) now fit; an
     interleaved technical FT no longer splits a regular trip.
3. Found for step 4 (possession ending), **owner decision needed for `custom`**: free throws
   after which the fouled team keeps the ball. pbpstats: flagrant and clear-path FTs end the
   possession (the retained ball is a new possession, as we decided for flagrant fouls);
   transition-take, away-from-play and inbound-foul FTs do **not** end it (one possession).
   `pbpstats_compat` will follow pbpstats.

## 2026-10-21 — Free throws with the ball retained (owner)

Both profiles follow pbpstats: clear-path FTs like flagrant FTs (last FT ends the possession,
the retained ball starts a new one); transition-take, away-from-play and inbound-foul FTs do
not end the possession. `rules.yaml` `free_throws_with_ball_retained`; `rules_version` →
`2026-10-21.3`.

## 2026-10-21 — Rebounds (step 3) and what pbpstats does with ball-retained free throws

1. `src/nba_platform/core/rebounds.py` (`classify_rebounds`, tests `tests/test_rebounds.py`):
   a rebound belongs to the latest miss in the period; it is real only after a missed field
   goal or a missed last, non-technical free throw (the owner's rule for non-final FTs, and the
   technical-FT rule "never start or end a possession" applied to rebounds; same as pbpstats'
   "end FT" condition); offensive = same team as the miss.
2. Dry run 2004-05 regular season: 124,824 rebound rows; real 116,914; ignored 7,559 after
   non-final FTs and 350 after technical FTs; 1 with no miss before it. Player OREB / DREB
   from this classification match the official box score in **99.980 % / 99.988 %** of
   player-games (29,541 vs 29,544 OREB; 73,429 vs 73,426 DREB).
3. pbpstats source checked again (`stats_nba/enhanced_pbp_item.py`, `free_throw.py`): a made
   last FT does not end the possession when it is an **away-from-play** FT (1 of 1 or 2 of 2,
   foul is away-from-play), an **inbound-foul** FT or a **transition-take** FT (1 of 1), with
   **no clock condition**, i.e. also outside the last two minutes, when the ball is not
   actually retained (in 2004-05, 15 missed last away-from-play FTs were followed by a player
   rebound, i.e. live ball). `pbpstats_compat` copies this. Whether `custom` should apply the
   "same possession" rule only when the ball is really retained is asked of the owner.

## 2026-10-21 — Possessions (steps 4-7) built; first comparison with pbpstats (2004-05)

`src/nba_platform/core/possessions.py` (`build_possessions`, `garbage_time`, `segments`);
tests `tests/test_possession_rules.py` (the owner's skeleton, expected values filled from the
written rules: 31 tests). Read-only dry run, 2004-05 regular season, `pbpstats_compat`:

- 1,230 / 1,230 games, 229,403 possessions, every team-game's points conserved (possession
  points + technical FTs = final score), 1,814 events outside possessions = the technical FTs.
- vs pbpstats per team-game (excluding `is_end_of_period_heave`): **94.02 % identical**,
  99.92 % within 1 (ramirobentes' own counts: 98.9 %).
- Fix found by the comparison: an and-1 is recognised by the defense's shooting / flagrant foul
  at the same second, not only by a following free throw, so a lane violation that cancels the
  free throw ends the possession on that turnover (+0.65 points of agreement).
- Remaining extra possessions: 109 of the differences are **flagrant and clear-path trips**,
  which pbpstats counts as **one** possession (free throws + the retained ball), not two. The
  CLAUDE.md rule says "two possessions (pbpstats)"; the pbpstats reference data show one.
  What-if with one possession: **98.37 %** identical. Owner decision asked.
- Provisional, for owner review: start type `after_jump_ball` (not in the six decided types);
  the jump-ball "next event with a team" skips fouls (their team is the fouling team).
- The two "between possessions" free throws are not flagged in this run: pbpstats' rule "a
  made last FT followed by the other team's foul at the same second does not end the possession"
  keeps the possession open, so they fall inside it (option (c) in practice). Owner decision asked.

## 2026-10-21 — DuckDB stack overflow in the tracking mart (Windows)

`marts.tracking.build` crashed the test process with "Windows fatal exception: stack overflow"
in 5 of 6 runs (in the wide INSERT with about 50 aggregates); with `SET threads = 1` it never
did. The build now runs with one thread and restores the previous setting (tested). The
table is small (about 10 k rows), so the cost is negligible. Code unchanged otherwise.

## 2026-10-21 — Owner decisions after the first pbpstats comparison; 2004-05 at 98.37 %

`rules_version` → `2026-10-21.4`; CLAUDE.md, `rules.yaml`, `docs/possession_rules.md` updated.

1. **Flagrant and clear-path free throws: one possession** (the trip and the retained ball), in
   both profiles. This is what pbpstats' reference data show; CLAUDE.md's earlier "two
   possessions (pbpstats)" was wrong. All five "ball retained" kinds (flagrant, clear path,
   transition take, away from play, inbound) now keep the possession.
2. **Between-possessions free throws: option (a) in both profiles.** A made last FT ends the
   possession even when the other team fouls again at the same second; the extra FTs are outside
   every possession (`is_between_possessions_ft`). pbpstats keeps the possession open there, so
   `pbpstats_compat` differs from pbpstats on purpose in these cases (3 in 2004-05).
3. **`after_jump_ball`** is a seventh start type; the jump-ball control rule ("next event that
   shows who has the ball" = shot, turnover, non-technical FT, real rebound; fouls skipped) is
   confirmed.

2004-05 regular season, read-only rerun: 229,292 possessions, points conserved in every
team-game, 1,817 events outside possessions (1,814 technical FTs + 3 between-possessions FTs).
vs pbpstats per team-game: **98.37 % identical**, 99.96 % within 1 (ramirobentes: 98.9 %).
36 games still differ (pbpstats has 38 possessions we do not; we have 13 it does not); to be
investigated game by game, not fixed by bending the rules.

## 2026-10-21 — "No Turnover" rows are turnovers; remaining differences with pbpstats (2004-05)

`rules_version` → `2026-10-21.5`. Source turnover rows with action type 0 (text "No Turnover",
606 rows in 2004-05) carry a credited steal, so they are turnovers and end the possession;
pbpstats' reference data count them. Before, the code skipped them (Claude's reading of the
pbpstats source, which the data contradicted). Effect on 2004-05: **98.37 % → 98.54 %** identical
per team-game, **100 %** within 1. Claude's reading of the data, to be confirmed by the owner
**[待確認]** (`rules.yaml` `turnovers`, CLAUDE.md possession-end list).

Remaining 36 team-game differences (28 where pbpstats has one more possession, 8 where we do): about
half involve the last seconds of a period (a rebound or turnover at 0:00-0:01 and the possession
that follows it: pbpstats' rule for possessions with 2 seconds or less left differs in detail
from our `is_end_of_period_heave` flag), the rest are single odd sequences. Not changed: to be
investigated game by game (working agreement 11).

## 2026-10-21 — Possessions written for 2004-05 regular season; checks 111, 7, 8

`build_core --step possessions` wrote `core.possessions` (229,296), `core.possession_stint_segments`
(257,662) and the event columns; new table column `rules_profile` (next to `rules_version`) records
the profile **[待確認]**. Checks (`validate/possession_checks.py`, report
`docs/validation/possession_check_2005_regular.md`):
- 111 (hard) passes: every team-game's possession points + free throws outside possessions = final score.
- 7 (warning): 4 of 1,230 games differ by 3 between the two teams (99.67 % within 2); pbpstats'
  own counts differ by 3 in three of them, so these are features of the games.
- 8 (warning): 36 of 2,460 team-games differ from pbpstats (98.54 % identical, 100 % within 1).
- Bug found by running on real data: a duplicated `period_start` row (game 0020400756) made an
  empty possession without an offense team; a repeated start row now joins the open possession.

## 2026-10-21 — Possessions for all 50 seasons with a pbpstats reference (profile pbpstats_compat)

`build_core --all --step possessions` wrote `core.possessions`, segments and the event columns for
2000-01 → 2024-25 (regular season + playoffs); summary `docs/validation/possession_summary.md`,
one report per season `possession_check_{year}_{type}.md`. 2025-26 regular season is also built
(no pbpstats reference exists for it: check 8 is skipped); 2025-26 playoffs are not built yet.

- Check 111 (hard) passes in every season. Two bugs found by the run and fixed: technical free
  throws listed **after** the period-end row were attached to the ending possession (their point
  was lost), and a technical foul listed **before** the period-start row opened an empty
  possession (2025-26). Check 111 now reports games registered as `source_score_conflict` in
  `core.known_gaps` instead of failing; check 8 is skipped when a season has no pbpstats data.
- Check 8, share of team-games identical to pbpstats: **97.2-99.3 % in every season 2000-01 →
  2015-16** (99.9-100 % within 1), but **70-82 % from 2016-17** (94-98 % within 1; both regular
  season and playoffs).
- The break: in every season about 800 final possessions of a period contain no action at all
  (only the period-end row: the ball is held until the buzzer). Before 2016-17 pbpstats counts
  them like we do; from 2016-17 we have about 1,000-1,280 of them per season and pbpstats does not
  count about 515 of them (2018-19: we have 626 possessions pbpstats does not, 515 of them ending
  at the period end; pbpstats has 61 we do not). Possessions total 247,097 vs 246,532 (+0.23 %).
  Not changed: counting a possession in which the offense simply runs out the clock is the
  basketball-correct definition; the owner decides whether `pbpstats_compat` should drop them
  from 2016-17 on **[待確認]**, and whether to investigate which of them pbpstats keeps.
- Check 7 (<= 2 difference between the teams): 0-21 games per season fail, 99.3 % or more of games
  pass in every season.

## 2026-10-21 — Why agreement with pbpstats drops from 2016-17 (investigation, Opus)

The earlier explanation ("pbpstats does not count about 515 empty final possessions") was wrong:
the raw pbpstats file and `reference.pbpstats_possessions` both contain those possessions. Matching
by end time + defense had mislabelled them. Side-by-side comparison of whole games found three causes:

1. **Clock precision (main cause).** Through 2015-16 every possession starts on a whole second; from
   2016-17 the source clock has tenths (21,309 fractional starts in 2016-17). Our end-of-period flag
   compares the exact time (`secs_remaining_period_at_start <= 2`), so a 0-point possession that
   starts with 2.4 s left is counted. pbpstats treats it as 2 s (whole seconds), so it is excluded.
   About 500-560 such possessions per regular season from 2016-17. Using whole seconds
   (`floor(secs_remaining) <= 2`) restores agreement: 2016-17 80.3 % → 98.2 %, 2018-19 77.9 % →
   97.9 %, 2022-23 77.9 % → 97.3 %, 2024-25 79.7 % → 98.6 %; no change before 2016-17. This is a
   rule semantic: **owner decision asked** (keep `secs_remaining_period_at_start` exact; only the
   flag's comparison would change; `rules.yaml` would gain `end_of_period.clock_precision`).
2. **Transition-take free throws, 2022-23 → 2024-25 (fixed).** They carry the plain "1 of 1" code
   (10); only the take foul (code 31) shows the kind. A regular free throw may now link to a take
   foul, and the trip becomes `transition_take` (same possession, as decided). Before, the free
   throw had no `foul_event_seq` and the possession was split. 2025-26 has its own code (81).
3. **Games missing in the pbpstats reference** (a few in 2019-20 and 2023-24) were counted as count
   differences; check 8 now compares only games both sides have and lists the missing ones.

Tried and reverted: not opening a possession for a team that commits a "turnover" without the ball
(defensive lane violation at an and-1). It lowered 2004-05 from 98.54 % to 98.37 % and did not
help later seasons, so the earlier handling stays. The database still holds four seasons built
with that variant (2004-05, 2018-19, 2022-23, 2024-25 regular); they are rebuilt with the next
full run.

## 2026-10-21 — End-of-period flag keeps the exact time (owner)

The owner kept the exact time left for `is_end_of_period_heave` (`rules.yaml`
`end_of_period.clock_precision: exact`, `rules_version` 2026-10-21.6). From 2016-17,
`pbpstats_compat` therefore differs from pbpstats by about 500-560 zero-point possessions per
regular season that start with 2-3 s left (pbpstats counts them as 2 s): a deliberate, documented
difference, so check 8 stays near 78 % identical from 2016-17 while 97-99 % within 1. The full
rebuild of all seasons (with the transition-take fix) is postponed until the owner asks.

## 2026-10-22 — Full rebuild: stints, possessions, marts and reports for every season

`python -m nba_platform.rebuild` (about 2 h 40 min, 9 steps, all ok, rules_version 2026-10-21.6,
profile `pbpstats_compat`):
- **core tables for all 60 season files** (1996-97 → 2025-26, regular + playoffs): 1,161,854
  stints, 7,275,201 possessions, 8,128,672 segments; every event outside a possession is a
  technical or between-possessions free throw. Check 111 (hard) passes in all 60.
- Check 8 vs pbpstats: 97.2-99.3 % identical through 2015-16 and 70-83 % from 2016-17 (the
  deliberate exact-seconds difference; 94-99 % within 1). The transition-take fix lifted 2022-23
  → 2024-25 by about 5 points (72.5 → 77.8 %, 75.4 → 79.2 %, 76.3 → 79.7 %). 1996-97 → 1999-00
  and 2025-26 have no pbpstats reference.
- Open: 2017-18 regular season is the outlier (70.4 % identical, 21 games with a difference of
  more than 2 between the teams, 159 `implied` possessions); not investigated yet.
- The pipeline now rebuilds the core tables after a season load (`post_load` and single-season
  runs), because a reload clears `stint_id` / `possession_id`.

## 2026-10-22 — 2017-18 outlier (partial investigation; the rest postponed by the owner)

2017-18 regular season: 70.4 % of team-games identical to pbpstats, 21 games where the two
teams' possession counts differ by more than 2, 159 `implied` possessions (neighbouring seasons:
32 / 41; 2015-16: 77). Findings:
- It is concentrated early in the season: `implied` possessions per 100 games: 52, 34, 19, 19, then 2-8.
- Mechanism: the source inserts **late-added events** by time into the sequence (their
  `source_event_num` is far above that of their neighbours, e.g. game 0021700075, event 58 has
  number 97 between 85 and 86), so the order of two or three events around a miss, rebound and
  turnover is wrong. Our rule is "source order, confirmed errors go to `corrections`" (decided
  2026-10-21); pbpstats repairs these orders automatically.
- Evidence: 53 % of the `implied` possessions of 2017-18 start within three events of a
  late-added event, against 23 % of ordinary possessions. 23 % of all 2017-18 possessions are near
  a late-added event (2015-16: 5 %, 2016-17: 10 %, 2018-19: 18 %), i.e. this season has far more of them.
- About half of the `implied` possessions are not explained by this yet (not analysed).

Not done, left for the next session (owner): classify the remaining ~75 `implied` possessions; decide
whether a reordering rule for late-added events (by event number) belongs in the `custom` profile
(it would change the "source order" principle) or stays a documented source defect.

## 2026-10-22 — Published to GitHub (private)

Repository: `mingchen-analytics/nba-analytics-platform`, **private**. Decisions (owner):
1. **History:** a new single initial commit. The 75 earlier commits (which contain 60 per-season
   detail files quoting source play-by-play text, and the early commits' author email) stay on the
   local branch `main-old-history` and in a `git bundle` outside the repository; they are never
   pushed. Only `main` is pushed.
2. **Manifest:** purchased BigDataBall files are listed in the git-ignored
   `data/raw/manifest_local.csv`; the committed `data/raw/manifest.csv` holds publicly downloadable
   sources only (code in `ingest/download.py` merges both when reading).
3. **License:** MIT, for the code and documentation only; the README says no third-party data is covered.
4. **Author e-mail:** GitHub noreply address (repository-local git config).
5. The short real 2004-05 sequences in `tests/fixtures/possessions/` (IDs, clocks, scores; no text)
   are kept; the README says so.
Making the repository public, and deploying the dashboard publicly, are separate decisions
(data terms of ramirobentes / NBA.com) **[待確認]**.

## 2026-10-22 — Implausible NBA.com tracking values in 2025-26 (found on the dashboard)

Looking at the Tracking page (first manual review of the dashboard) showed average speeds of 11-15 mph
(Cooper Flagg 12.1, Shaedon Sharpe 15.4). Investigation (read-only):
- League medians are normal (2025-26: 2.67 miles / 36 min, 4.47 mph); the defect is in specific
  player-seasons: **44 players above 5.5 mph in the 2025-26 regular season, up to 22.6 mph**, with
  distances about 2.7 times normal. 9 each on MIL, DAL, NYK, POR (66-76 % of those teams' tracked
  minutes), a few on WAS, ATL, PHX (probably traded players, because regular-season tracking lists a
  traded player once under his last team). No other season has a value above 5.08 mph (2013-14 → 2024-25).
- Our validation had only compared the box statistics repeated in the tracking tables, not the tracking
  measurements themselves; `docs/validation/tracking_quality.md` now does (per-season medians and flags).
- Handling (flag, never delete): `marts.player_tracking_season.movement_suspect` = average speed above
  5.5 mph with at least 100 minutes (`rules.yaml` `dashboard`); the Tracking page warns and hides flagged
  rows by default (Movement category). Other players on the affected teams may be affected below the
  threshold; not corrected.
- Another break found by the same report: possession time per minute and touches per 36 minutes change
  level from 2024-25 (median possession time / minute 0.055 → 0.110 → 0.074; touches / 36 min 56 → 52), i.e. NBA.com's
  tracking measurement changed; these measures are not comparable across 2023-24 → 2024-25. Documented
  in the report, not changed.
- **[待確認]** the 5.5 mph threshold and the 100-minute minimum (chosen from the clean seasons' maximum of 5.08).

## 2026-10-22 — Repository made public

`mingchen-analytics/nba-analytics-platform` is **public** (owner decision, for the portfolio and
résumé). Final scan before the change: published history is one author (GitHub noreply address), 5
commits, no detail files, no purchased-file listing, no secrets or local paths, no data files except
the public manifest. Wiki and projects disabled; topics: nba, basketball-analytics, sports-analytics,
data-engineering, duckdb, streamlit, python, play-by-play. Deploying the dashboard publicly stays a
separate, undecided question (data terms) **[待確認]**.

## 2026-10-22 — On/off and lineup marts (built overnight on a branch; waiting for owner approval)

New tables `marts.player_onoff_season` and `marts.lineup_stats` (`marts/onoff.py`), built from our own
stints, possessions and events. A schema addition: **not merged until the owner approves** (working agreement 8).
- **Crediting = the `pbpstats_compat` hybrid** (CLAUDE.md), recorded in `credit_method = 'pbpstats_hybrid'`:
  a possession goes to the stint on the floor when it ends, field-goal points go with the possession,
  free-throw points go to the stint on the floor at the foul. The open A/B/C question is **not decided** by this;
  the columns allow A, B and C to be stored side by side later. **[待確認]**
- A counted free throw without a linked foul (56 in all seasons) is credited to its own stint, and counted in
  `docs/validation/onoff_checks.md`. **[待確認]**
- Technical free throws and free throws between possessions are counted nowhere. Heave and garbage possessions are
  **counted, not excluded**; their counts are columns (`*_heave_poss`, `*_garbage_poss`), so whether to exclude
  them stays a decision for the page or for RAPM.
- Checks (hard, the build is rolled back): every possession has an end stint; the offense team is home or away;
  credited points = possession points (7,723,936); stint possessions = core.possessions; per team-season the players'
  possessions, points and seconds are exactly 5 times the lineups'. All pass for all 60 season files.
- Sanity (not a check): league points per 100 possessions rise from 104.0 (1996-97) to 113.3 (2024-25); LeBron James 2012-13 MIA
  on/off +15.2, Stephen Curry 2015-16 GSW +22.0; player on-court minutes differ from official box minutes by 2.4 minutes
  on average over 10,945 player-seasons with 500+ minutes (the large single gaps come from incomplete box scores,
  see `docs/validation/box_vs_pbp.md`).
- No page yet: the owner wants to see the layout of the existing pages first.

## 2026-10-22 — 2017-18 outlier, second part (read-only analysis, overnight; no rule changed)

All 159 `implied` possession starts of the 2017-18 regular season (a possession that stayed open when the other
team acted; 80+ games), each placed in exactly one category, first match wins. Numbers and IDs only.

| # | category | n | note |
|---|---|---|---|
| 1 | an event the source inserted out of number order lies within 4 rows of the trigger | 92 (58 %) | 80 games, mostly the first 300 games of the season |
| 2 | missed field goal by the first team, no rebound row before the other team acts | 14 | |
| 3 | missed free throw, no rebound row | 1 | |
| 4 | rebound rows exist but none ends the possession | 35 | 17 have only rebound rows of the first team (an event of that team is missing or misplaced); 18 have a rebound row of the other team that the code cannot tie to a miss or that follows a non-final free throw |
| 5 | made free throw by the first team, the end of the trip is not shown | 15 | last free-throw code seen: "1 of 1" 7, "2 of 2" 6, other 2 |
| 6 | made shot or turnover by the first team, possession still open | 2 | |

Check against the official NBA.com play-by-play (shufinskiy `nbastats_2017`, message types only): in categories 2 and 3
(15 cases) the official file has a rebound row directly after the same miss in **14** (the other case has no miss at that
clock), i.e. the rebound exists in the official file but is not where the primary source's rows need it. Examples:
`0021700002` event 334, `0021700012` event 222, `0021700252` event 484.
- Categories 2-6 (67 cases, 42 %) are missing, missing-from-place or inconsistent events in the primary source; the
  evidence supports **corrections rows** (working agreement 4) rather than a reordering rule, but a correction needs a
  confirmed error per case. Category 1 (92) is the late-added-event mechanism of the first part (entry above).
- Not done: category 4's 18 cases with a rebound row of the other team are only partly traced (the rebound row is
  matched to no miss, or follows a non-final free throw); no correction rows written; whether to add a reordering rule in
  `custom` stays the owner's decision. **[待確認]**

## 2026-10-22 — On/off tables approved; pair table; option A against the hybrid

- **Owner approved** the new tables `marts.player_onoff_season`, `marts.lineup_stats`, and the new
  `marts.pair_stats` (two teammates on the floor; each stint gives 10 pairs per team; hard check: per team-season the
  pairs' possessions, points and seconds are exactly 10 times the lineups'). Also approved: the team efficiency table
  (next entry). Credit method stays `pbpstats_hybrid`; the A/B/C question remains open.
- **Option A (`end_lineup`) computed for comparison only** (`docs/validation/onoff_credit_methods.md`). Possession counts
  are identical; only free-throw points move. Substitutions are usually made in the dead ball after a foul and before the
  free throws: 28.0 % of made free throws come after a substitution that followed their foul, and for 40.9 % the lineup at the foul
  differs from the lineup at the end of the possession. Result: **548,053 points (7.1 % of possession points) move**;
  a player's net on-off changes by 1.19 points per 100 possessions on average (players with 1,000+ offensive possessions on), and
  by more than 1 point for about 40 % of them. The choice matters; it remains the owner's (pending_decisions item 4).

## 2026-10-22 — Team efficiency table (approved)

`marts.team_efficiency_season`: offense / defense points per 100 of our possessions per team and season, in three versions
(all possessions; without end-of-period heaves; also without garbage time), so a page can switch. Technical and
between-possession free throws are outside possessions and stored separately. Check against NBA.com's season box score:
team points equal for 1,365 of 1,372 team-seasons; the 7 others are small source-score differences (1996-97 → 2012-13, 1-7
points) and the 2024-25 playoff game `0042400231` that has a box score but no play-by-play (GSW -99, MIN -88). Sanity: GSW 2015-16
net +10.9, BOS 2023-24 net +11.5 (without heaves). Four factors are not built yet (they need shot, rebound and turnover counts;
the official box score has them, but mixing it with our possessions has to be labelled).
