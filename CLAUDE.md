# CLAUDE.md — nba-analytics-platform

A personal NBA data platform: my own play-by-play database, my own possession/stint
logic, and my own metrics (on/off → RAPM), with a dashboard on top. Later it will
absorb my Playoff Matchup Adjustment Tracker and my broadcast-video player tracking
system.

Owner: Ming Chen (Wake Forest MSBA, sports analytics). This is a portfolio project —
I must be able to explain every design decision in an interview.

---

## Working agreements (read first)

1. **Core logic: Claude writes, I review and decide (changed 2026-10-21 at my request).**
   Claude writes the stint-building and possession-parsing code in `src/nba_platform/core/`;
   every basketball judgement in it is a rule I decided (CLAUDE.md, `config/rules.yaml`),
   and each design choice is logged in `docs/decisions.md` so I can explain it. Claude stops
   after each step for my review. Earlier version: "I write the core logic myself."
   Boilerplate (downloading, loading, schema DDL, Streamlit layout) Claude may write.
2. **Explain before you build.** For any non-trivial change, state the plan in a few
   lines first. After writing code, explain what it does in plain terms.
3. **Small vertical slices.** Get ONE season (2004-05) working end-to-end before scaling
   to all seasons.
4. **Never modify raw data.** Fixes go in `corrections` (see below), applied in staging.
5. **Never commit raw or third-party data to git.** `data/` is git-ignored. Only code,
   docs, and my own derived results may be published. Exception: `data/raw/manifest.csv`
   (URL, download time, SHA-256 of every raw file; our own metadata) is committed.
6. **Unknown → NULL.** Never invent IDs, timestamps, or values to fill gaps.
7. **Fail loudly.** A row that can't be mapped (unknown player, team, event type) stops the
   pipeline; it is never silently dropped.
8. Ask before changing the schema or any rule in this file. When a decision is made,
   update this file.
9. **Basketball definitions are separate from code.** Any rule that affects possessions,
   lineups, scoring attribution or metrics is written down (docs + `config/rules.yaml`)
   and has tests.
10. **Keep event-level detail.** Never assume a possession belongs to a single stint;
    keep the original event order.
11. **Never bend basketball logic to match a reference number.** When we differ from a
    reference (pbpstats, box scores), investigate and report the difference.
12. **Separate observed facts, source-provided values, and model assumptions.** Record
    the rules version so every metric can be reproduced.

---

## Data sources

| Source | Use | Seasons | Notes |
|---|---|---|---|
| **ramirobentes/nba_data** (GitHub Releases, Parquet) | **Primary** play-by-play, lineups | 1996-97 → current (updated daily) | NBA player IDs; lineups on every event. No license stated → keep local only. |
| **shufinskiy/nba_data** (`shotdetail_*`) | Shot coordinates for older seasons | 1996-97 → 2024-25 | NBA shot chart data. Also has `pbpstats_*` (possession reference, 2000-01+) and `matchups_*` (2017-18+). Repo is huge: download single files only. |
| **BigDataBall** (my purchased CSVs, local) | **Validation only** | 2004-05 → ~2019-20 | Names only, no IDs. Not the primary source. |
| **nba_api** | Fill gaps / box scores, if needed | any | Must run locally; stats.nba.com blocks cloud IPs. |
| Basketball Reference | **Do not scrape.** Manual spot checks only | — | Terms prohibit automated access and building tools from scraped data. |

### Source test results (2026-10-16)

- Game `0020400027` (SAS @ LAL, 2004-11-05): final 105–96 in all sources; ramirobentes vs
  BigDataBall lineups agreed on 100% of 430 aligned events; BigDataBall shot coordinates
  are identical to NBA shot chart `LOC_X/LOC_Y` (158/158).
- ramirobentes 2004-05, 2020-21, 2025-26: complete game counts (1230 / 1080 / 1230);
  0 lineup rows without exactly 5 players; `secs_played` sums to game length in ≥99.9% of
  games; team possession counts differ by ≤2 in ≥99.7% of games.
- ramirobentes 2004-05: 464 player IDs, one name per ID, no collisions.
- ramirobentes has **no shot coordinates** for 2004-05 (`locX` all NULL); present in
  2020-21+. shufinskiy `shotdetail_2004` covers 100% of 2004-05 shots and joins on
  `GAME_EVENT_ID = event_num`.

### Known source quirks

- **ramirobentes**
  - File season = **end year**: `pbp_regular_2005.parquet` is 2004-05.
  - URL pattern: `https://github.com/ramirobentes/nba_data/releases/download/pbp/pbp_regular_{YYYY}.parquet`
  - `player1_name` etc. are `"1477 Bruce Bowen"` (ID + name in one string) → split.
  - `lineup_home` / `lineup_away` are comma-separated `"ID Name"` strings → split.
  - Has its own possession columns (`possession`, `poss_home`, `poss_away`, `start_poss`)
    and `garbage_time`. Use them only as a **reference**; we compute our own.
  - Column set differs by era (some columns exist only 2016-17+ or 2025-26+).
- **shufinskiy**
  - File season = **start year**: `shotdetail_2004` is 2004-05.
  - `GAME_ID` loses leading zeros in CSV → `zfill(10)`.
  - Files are `.tar.xz` containing one CSV.
- **BigDataBall**
  - `game_id` stored as an Excel formula string `="0020400027"` → strip.
  - Players by name only; lineups in `a1–a5` (away), `h1–h5` (home).
  - Text fields have stray whitespace (`" timeout: regular"`, `"traveling "`).
  - Event labels changed in 2025-26 (`miss`→`shot`, `sub`→`substitution`).

---

## Tech stack

- Python (pandas, pyarrow) for ingestion and cleaning
- **DuckDB** (single file, default `%LOCALAPPDATA%\nba_platform\nba_platform.duckdb`,
  outside the project so folder-sync tools never touch it; optional override
  `NBA_PLATFORM_DB`) + Parquet for storage.
  **Only the ingestion pipeline writes to DuckDB**; every other tool (DBeaver, Streamlit,
  notebooks) opens it **read-only**.
- SQL for transformations (I browse/query with **DBeaver**, which has a DuckDB driver)
- scikit-learn + scipy.sparse for RAPM
- Streamlit for the dashboard (reads marts only, never computes heavy logic)
- pytest for tests. dbt is optional later, once core tables are stable.

---

## Architecture

```
raw/        original files, never modified (Parquet, CSV, tar.xz)
   ↓  Python: parse IDs, trim text, convert clock → seconds, apply corrections
staging/    cleaned, one consistent schema per source → Parquet
   ↓  load into DuckDB
core        games, teams, players, events, shots, stints, possessions
   ↓  SQL (+ Python for RAPM)
marts       player_game, player_onoff_season, lineup_stats, player_rapm, ...
   ↓
app/        Streamlit, reads marts only
```

### Directory layout

```
nba-analytics-platform/
├── CLAUDE.md
├── README.md
├── docs/
│   ├── possession_rules.md     # full rule spec with examples
│   ├── decisions.md            # dated log of design decisions
│   └── validation/             # validation reports (details/ is git-ignored)
├── data/                       # git-ignored (except raw/manifest.csv)
│   ├── raw/{ramirobentes,shufinskiy,bigdataball}/
│   ├── raw/manifest.csv        # url, downloaded_at, sha256 per raw file (committed)
│   └── staging/
├── src/nba_platform/
│   ├── ingest/                 # download + read raw sources
│   ├── staging/                # one adapter per source → common schema
│   ├── core/                   # stints.py, free_throws.py, rebounds.py, possessions.py
│   │                           # (Claude writes, owner reviews: working agreement 1)
│   ├── metrics/                # onoff.sql, rapm.py
│   └── validate/               # checks listed below
├── sql/                        # DDL and mart queries
├── corrections/                # corrections.csv
├── config/                     # rules.yaml: all tunable thresholds/definitions
├── app/                        # Streamlit
└── tests/
```

---

## Conventions

- `game_id`: TEXT, 10 characters with leading zeros (`'0020400027'`).
- `player_id`, `team_id`: INTEGER, NBA official IDs. Team-level events use `player_id` NULL.
- Season: `season` TEXT `'2004-05'` and `season_end_year` INTEGER `2005`.
- `season_type`: `'regular'` | `'playoffs'`.
- Time: `period` INTEGER; `secs_elapsed_game` (seconds since tip-off; OT periods are 300 s).
  Keep `clock` text only for display.
- Every staged/core row carries `source` (e.g. `'ramirobentes'`) and, where relevant,
  `source_event_num`.
- Event types use **our own vocabulary** (mapped from each source):
  `shot_made, shot_missed, free_throw, rebound, turnover, foul, substitution, timeout,
  jump_ball, violation, period_start, period_end, other`.
- snake_case everywhere.

---

## Core schema (v0 — to be refined on the 2004-05 slice)

- **games**: game_id, season, season_end_year, season_type, game_date, home_team_id,
  away_team_id, home_score, away_score, num_periods
- **teams**: team_id, abbreviation, name (abbreviations vary by era)
- **players**: player_id, name, name_variants
- **events**: game_id, event_seq, source_event_num, period, secs_elapsed_game, team_id,
  event_type, event_subtype, player1_id, player2_id, player3_id, points,
  home_score, away_score, stint_id, possession_id, description;
  for possession rules: `chance_id` (chance boundary), `foul_event_seq` (on free throws:
  the fouling event), `is_technical_ft`, `is_between_possessions_ft`.
  **The events table is the single source of points**: every scoring event records the
  scoring team (`team_id`) and the ten players on court (through `stint_id`), and carries
  `is_technical_ft`. Team totals are sums over events.
- **lineups on court**: stored via `stints` (not repeated on every event); every event
  maps to its on-court lineup through `events.stint_id`.
  **Definition: the lineup on a substitution event's row is the lineup *after* the
  substitution** (same as ramirobentes). (Owner decision 2026-10-18; replaces the reviewer's
  "before" definition — see decisions.md.)
  **Stint boundaries (owner 2026-10-21):** a substitution starts a new stint, but
  **consecutive substitutions at the same second (no other event between them) are merged**
  into one stint whose lineup is the one after the last of them; any other event in between
  (e.g. a free throw) keeps them apart. **Every period starts a new stint**; a stint ends at
  the next stint's start or at the end of its period (720 s, OT 300 s). Player IDs keep the
  source order. On the earlier substitution rows of a merged run, `events.stint_id` points to
  the merged lineup; the row's own lineup stays in `staging.event_lineups`.
- **stints**: game_id, stint_id, start_secs, end_secs, home_p1..p5, away_p1..p5
  (a stint = a stretch where the same ten players are on the floor)
- **possessions**: game_id, possession_id, offense_team_id, defense_team_id, start_secs,
  end_secs, start_type, end_type, **points** (the offense's points in this possession,
  technical free throws excluded), num_chances, rules_version; context for later
  definitions: period, secs_remaining_period_at_start, secs_remaining_game_at_start,
  start_margin_offense, offense_is_home; flags `is_end_of_period_heave`,
  `is_garbage_time`, `is_after_timeout`, `timeout_team_id` (team that called the timeout; NULL for an official timeout or none; owner 2026-10-21). **No single stint_id**: a possession can span
  several stints. No `scoring_team_id` and no `def_points`: points by the other team
  (e.g. a technical FT by the defense) live only in the events table.
- **Lineup efficiency** = sum of the lineup's points while on court ÷ sum of its
  possessions; technical free throws excluded by default (a switch includes them).
- **possession_stint_segments**: game_id, possession_id, segment_seq, stint_id,
  start_event_seq, end_event_seq, start_secs, end_secs (one possession → one or more
  stint segments)
- **shots**: game_id, source_event_num, player_id, team_id, shot_type, action_type,
  distance_ft, loc_x, loc_y, made
- **player_xref**: source, source_player_key, player_id, method (`auto` | `manual`)
- **corrections**: game_id, source_event_num, field, old_value, new_value, reason, added_on

---

## Possession rules (decided 2026-10-16 except where marked)

Principle: **store facts, decide with flags.**

**Event order (decided 2026-10-21):** possessions are built in the source's event order. Order
errors are not fixed by reordering rules in the code; a confirmed error becomes a row in
`corrections` (working agreements 4, 10, 11). Game-by-game mismatches with pbpstats are
investigated first.

**Event types without a possession meaning (decided 2026-10-21):** the 2025-26 duplicate steal
and block rows (msg 95 / 92), team "Heave" markers (msg 22), "Game End" (msg 93 / 0) and
"Stoppage" rows (msg 20) stay `other` and are ignored by the possession code. Edge cases are flagged, not deleted, so
metrics can choose. Align with pbpstats where reasonable so possession counts can be
validated game by game against shufinskiy `pbpstats_*`.

**Every tunable threshold and definition lives in `config/rules.yaml`, never hard-coded.**
Every possession row records the `rules_version` it was built with.

A possession **ends** on: made FG (if and-1, after the free throw), defensive rebound
(incl. team rebound), turnover (including source rows with action type 0, labelled "No Turnover", which carry a credited steal; 2026-10-21 **[待確認]**), **made** final free throw of a trip, end of period.
A **missed** final free throw does not end it by itself: the rebound decides (defensive
rebound → ends; offensive rebound → the possession continues).
An offensive rebound does **not** end a possession.

| Case | Rule | Status |
|---|---|---|
| End-of-period possessions | pbpstats approach: a possession that starts with ≤ `end_of_period_threshold_secs` (rules.yaml, default 2) left in the period **and scores 0 points** is excluded when computing efficiency. All possessions are **kept**; flag `is_end_of_period_heave`. Store seconds left in the period at the start so the threshold can change without rebuilding. The comparison uses the **exact** time left (owner 2026-10-21; the source has tenths from 2016-17, pbpstats uses whole seconds, so `pbpstats_compat` keeps about 500-560 more zero-point possessions per season from 2016-17 on purpose). | decided |
| Substitution during a possession (incl. between free throws) | **Not decided (kept open on purpose, 2026-10-21): compare A/B/C after `pbpstats_compat` is validated.** The data must keep all three options computable: **(A)** whole possession credited to the lineup on court when it ends; **(B)** FT points credited to the lineup on court at the time of the foul; **(C)** Cleaning the Glass chance split. So: every event maps to the lineup on court at that moment; every free throw records its fouling event; chance boundaries are recorded. | **open** |
| Offensive rebound | Does not end the possession. Each possession records its number of chances (`num_chances`). Chance boundaries (rules.yaml): **offensive rebounds only** in the first version (confirmed 2026-10-21); other boundaries only after checking Cleaning the Glass's published definition, in the `custom` profile. | decided |
| Flagrant foul (FTs + retained ball) | **One possession**: the FT trip and the retained ball are the same possession (owner 2026-10-21, both profiles; this is what pbpstats' reference data show; the earlier "two possessions (pbpstats)" was wrong). The last flagrant FT does not end the possession and is not a new chance. | decided (2026-10-21) |
| Other free throws with the ball retained | Same possession, like flagrant fouls (owner 2026-10-21, both profiles = pbpstats): **clear-path, transition-take, away-from-play and inbound-foul** free throws do not end the possession (pbpstats applies away-from-play and inbound with no clock condition). The kind comes from the free-throw code or the linked foul (`foul_event_seq`). | decided (2026-10-21) |
| Technical free throws | Do not start or end a possession. Count toward team points, but flag the event `is_technical_ft`; excluded by default from lineup efficiency and RAPM. | decided |
| Non-technical FT between possessions | A free throw awarded for a second foul in the same dead ball **after** the possession already ended (e.g. away-from-play or loose-ball foul after the last made FT; 1 case each in 2004-05 and 2024-25): treated like a technical FT: does not start or end a possession, counts toward team points, flag `is_between_possessions_ft`, excluded by default from lineup efficiency and RAPM. | decided (2026-10-21); option (a) in **both** profiles (owner 2026-10-21): a made last FT followed by another foul of the other team at the same second still ends the possession. pbpstats keeps the possession open there instead, so `pbpstats_compat` differs from pbpstats on purpose in these cases. |
| "Team rebound" after a non-final missed FT | Not a rebound; ignore (does not end the possession, is not a chance). The event row is kept. | decided (2026-10-21) |
| Jump ball / held ball | A jump ball does not end a possession by itself. Possession changes only if the other team gains control, decided by the team of the **next event that shows who has the ball**: a shot, a turnover, a non-technical free throw or a real rebound (fouls are skipped: their team is the fouling team; the player1/2/3 roles differ by era). The new possession's start type is `after_jump_ball`. Not a new chance. | decided (2026-10-21) |
| Possession start type | Fine-grained: `after_made_shot`, `after_defensive_rebound`, `after_steal` (live-ball turnover), `after_dead_ball_turnover`, `after_free_throw`, `period_start`, `after_jump_ball` (owner 2026-10-21). Plus flag `is_after_timeout`: a timeout event (by either team or official) in the dead ball between the previous possession's end and this possession's first event; the calling team is stored too. | decided (2026-10-21 for the timeout definition) |
| Garbage time | Flag `is_garbage_time` using the Cleaning the Glass definition (rules.yaml). Whether to exclude it is decided when building RAPM. A leverage-style definition may replace it later, so every possession stores: start score margin (offense's perspective), game seconds remaining, period, and whether the offense is the home team. | decided (as flag) |

Full spec with worked examples lives in `docs/possession_rules.md`.

### Development strategy: copy first, then deviate

`config/rules.yaml` holds two rule profiles:
- **`pbpstats_compat`** — a baseline that matches pbpstats as closely as possible. For the open
  substitution-during-a-possession question it uses pbpstats' hybrid: possessions are
  credited to the lineup on court when the possession ends, free-throw points to the
  lineup on court at the time of the foul.
- **`custom`** — my adjustments (e.g. technical free throws excluded by default); the
  substitution question stays **open** here.

Once the possession code exists, run `pbpstats_compat` first and compare with
`reference.pbpstats_possessions` game by game; the goal is equal per-team possession counts
in the vast majority of games. Every mismatch is investigated and explained — never fixed
by bending the logic to match the number (working agreement 11). Then deviate in `custom`,
one documented change at a time.

---

## Validation checklist (run per season, every load)

Two levels. **Every anomaly, at either level, is written to a report in
`docs/validation/`; data is never silently deleted.**

**Hard fail — stop; do not produce results for that season:**
- Core IDs cannot be identified (unknown player, team, game, event type). Includes
  check 9: every player name/ID maps through `player_xref`.
- Duplicate event unique keys (`game_id + event_seq`, `game_id + source_event_num`).
- The same player appears twice in one lineup.
- Game time out of range (`secs_elapsed_game` outside the period, or beyond game length).
- A join produces unexpected many-to-many row inflation.

**Warning — write to the error report for review; do not stop:**
- Small differences between play-by-play minutes and box score minutes (check 5).
- Possession counts that disagree between sources (checks 7–8).
- Missing shot coordinates (check 10).
- End-of-period special events.

Numbered checks (level shown where the review set it; others pending owner confirmation):
1. Game count matches the schedule (1230 normally; 1080 in 2020-21; lockout seasons fewer).
2. Sum of event points per team = final score.
3. Every event has exactly 5 distinct home and 5 distinct away players on court
   (a duplicate player in a lineup → hard fail).
4. Substitution consistency: entering player appears on court after the sub, leaving
   player does not.
5. Player minutes from play-by-play ≈ box score minutes. *(warning)*
6. Team player-seconds per game = 5 × game length (2880 s + 300 s per OT).
7. Team possession counts in a game differ by ≤ 2. *(warning)*
8. Our possession counts vs pbpstats reference: report differences per game. *(warning)*
9. Every player name/ID maps through `player_xref`; unmapped → fail. *(hard fail)*
10. Shot coordinates join rate to shot events (expect ~100%). *(warning)*
11. Cross-source check: for seasons where BigDataBall exists, compare lineups and scores.

---

## Roadmap

- [x] **Phase 0** — Repo setup, `.gitignore` for `data/`, download 2004-05 sources.
- [x] **Phase 1** — Staging adapter for ramirobentes; load `games`, `teams`, `players`,
      `events` for 2004-05 into DuckDB; validation checks 1–6.
- [x] **Phase 2** — Shots table from shufinskiy; check 10.
- [x] **Phase 3** — Possessions + checks 7–8 (done 2026-10-22 for all 60 season files, profile
      `pbpstats_compat`; `custom` profile and the A/B/C substitution credit still open).
- [ ] **Phase 4** — Stints (done, all seasons) + on/off in SQL (next); first Streamlit page (player on/off, with
      possession counts shown next to every rate).
- [x] **Phase 5** — Scale to all seasons; cross-source check vs BigDataBall.
- [ ] **Phase 6** — RAPM (Ridge; separate O/D; multi-season windows; home court;
      low-minute player bucket). **No preset λ range**: choose λ by cross-validation
      grouped by **game**. The data design supports both possession-level and
      stint-level observations.
- [ ] **Phase 7** — Integrate Matchup Tracker (shufinskiy `matchups_*`, 2017-18+).
- [ ] **Phase 8** — Integrate video tracking (join on game_id + period + game clock).

"Integrate" in Phases 7–8 means **exchanging data through shared `game_id`,
`player_id`, `team_id`**, not merging repos. Video needs its own synchronization layer
(video time ↔ game clock); for now only the interface is reserved.

---

## Glossary

- **Possession**: one team's continuous control of the ball until it ends (rules above).
- **Stint**: a stretch of play with the same ten players on the floor; a new stint starts
  at every substitution (consecutive substitutions at the same second merged) and at every period start.
- **On/Off**: team net rating per 100 possessions with a player on the floor minus with
  him off the floor (same team, same season).
- **RAPM**: ridge regression on possessions/stints that estimates each player's impact per
  100 possessions while controlling for the other nine players on the floor.

## References

- pbpstats raw PBP issues: https://github.com/dblackrun/pbpstats/wiki/Fixing-issues-with-raw-play-by-play
- pbpstats possession definitions: https://darrylblackport.com/posts/2019-04-03-why-pbpstats-possession-counts-lower/
- Building RAPM: https://jeremiasengelmann.substack.com/p/nba-adjusted-plus-minus-how-to-build
- Player ID mapping approach: https://github.com/llimllib/nba_data/issues/62
