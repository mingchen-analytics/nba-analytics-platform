# Dashboard spec (draft v0, 2026-10-20; layer-1 pages built 2026-10-21: Games, Players, Teams, Shooting, Tracking)

Draft for the owner to edit. It maps every planned page to the data it needs and says whether
it can be built now or has to wait for the possession code or for RAPM.

## Goal

A multi-page site in the spirit of Cleaning the Glass, Databallr and Dunks & Threes (layout
and navigation ideas only; no content copied; check each site's current pages before
borrowing a layout), in three layers:

| Layer | Audience | Content |
|---|---|---|
| 1. Basics | casual visitors | box scores, leaderboards, shooting, team pages |
| 2. Advanced | informed fans | on/off, lineups, per-100-possession numbers, tracking-based custom metrics |
| 3. Integrated | analysts | RAPM (offense / defense), then an EPM-style one-number metric |

The database comes first: every page reads a `marts.*` table, never raw events (CLAUDE.md:
"Streamlit reads marts only"). Nothing on a page is computed in the app.

## Principles

1. **Sample size next to every rate** (possessions, attempts, minutes).
2. **Percentile colouring against the league** for the same season and season type (CTG style).
3. **Rule switches are visible**: technical free throws, garbage time, substitution-during-a-possession
   option A/B/C (CLAUDE.md "Possession rules"). Every metric names its `rules_version` and
   profile. This is what makes the site different from the sites above.
4. **Provenance label** on every number: *official* (NBA.com value), *ours* (counted from our
   play-by-play), or *model* (RAPM / EPM). Observed facts, source values and model
   assumptions are never mixed in one column (CLAUDE.md working agreement 12).
5. **Season and season type selectors** on every page; 1996-97 → 2025-26 where the data exists
   and a clear "not available before 2013-14" note where it does not (tracking).

## Site map

### Layer 1: can be built now

| Page | Questions it answers | Content | Source tables |
|---|---|---|---|
| Home | what is in here, what changed | latest games, coverage per season, links | `core.games`, validation summary |
| Games | what happened in a game | official box score for both teams, score-by-quarter, score-margin chart, play-by-play list | `reference.nba_player_box`, `core.games`, `core.events` |
| Players: leaderboards | who leads in X | totals, per game, per 36, true shooting %, filters (season, team, minimum minutes) | `marts.player_season` |
| Player page | one player's season / career | game log, season splits, shooting by zone, percentile bars | `marts.player_game`, `marts.player_season`, `core.shots` |
| Teams | team profile | record, scoring, pace and ratings from NBA's official possessions (labelled *official*), roster minutes | `marts.team_season`, `reference.nba_team_possessions` |
| Shooting | where do shots come from and go in | zone frequency and accuracy with league percentile, shot chart | `core.shots`, `core.shot_quality_flags` |
| Tracking (season) | who runs, touches, passes | NBA.com season tracking and hustle tables, shown as *official* | `reference.nba_tracking`, `reference.nba_hustle` |
| Data health | can I trust this | existing dashboard (checks, benchmarks, coverage) | `validation.results`, `reference.*` |

Notes for layer 1:
- The official box score is what is shown. Our own play-by-play version (`marts.player_game_pbp`)
  is compared against it in `docs/validation/box_vs_pbp.md` to show that the event table is
  trustworthy; it is not a second box score on the site.
- Shot frequency / accuracy uses `core.shots` (all seasons). Shot-quality flags are shown,
  never used to delete shots.
- Team pace and ratings use the NBA official `POSS` until our own possessions exist; this is
  labelled *official* and replaced (not silently) afterwards.

### Layer 2: needs the owner's possession and stint code

| Page | Questions | Content | Needs |
|---|---|---|---|
| Team efficiency | how good is the offense / defense | points per 100 possessions, four factors, with garbage-time and technical-FT switches | `core.possessions`, rules profiles |
| On/off | how does the team do with a player on vs off | on, off, difference per 100 possessions, possession counts next to every rate | `core.stints`, `core.possessions`, events with `stint_id` |
| Lineups | which lineups work | five-man and two-man tables with minimum possessions | `core.stints`, `core.possessions` |
| Rule explorer | how much do the rules matter | the same player / lineup under `pbpstats_compat` vs `custom`, and substitution option A/B/C | the three credit methods (CLAUDE.md, open question) |
| Tracking per game | how do the tracking numbers move | distance, touches, passes per game; contested shots, deflections, loose balls | `reference.nba_box_tracking`, `reference.nba_box_hustle` (2013-14 → 2025-26 playoffs, 2024-25 → 2025-26 regular season so far) |
| Own metrics from tracking | numbers that exist nowhere else | to be designed (for example touches and passes per 100 possessions; contested shots per 100 opponent possessions) | tracking boxes + our possessions |
| Matchups | playoff series adjustments | the owner's Playoff Matchup Adjustment Tracker, joined on `game_id`, `player_id`, `team_id` | `reference.matchups` (2017-18 → 2024-25) |

### Layer 3: needs layer 2 first

| Page | Content | Needs |
|---|---|---|
| RAPM | offensive and defensive RAPM, multi-season windows, home court, low-minute bucket; lambda from grouped cross-validation (by game) | possession-level observations, stints |
| One-number metric | an EPM-style metric: a box-score prior (from layer 1 data) combined with RAPM | RAPM + player-season box data |

## What layer 2 needs from the possession code

A checklist the possession and stint tables must satisfy so these pages need no rework
(it follows CLAUDE.md; nothing new is decided here):

- Possession fields: offense / defense team, start and end seconds, start and end type,
  points, `num_chances`, period, seconds remaining at start, start margin, `offense_is_home`,
  `is_end_of_period_heave`, `is_garbage_time`, `is_after_timeout`, `rules_version`.
- Technical free throws flagged, excluded by default from efficiency and RAPM.
- Every event mapped to its on-court lineup (`stint_id`); each substitution starts a stint.
- Free throws record the fouling event (`foul_event_seq`), so credit options A/B/C can all be computed.
- Both rule profiles (`pbpstats_compat`, `custom`) can be built side by side, so the Rule explorer is possible.

## Marts to build (layer 1, in this order)

| Table | Grain | Primary key | Built from |
|---|---|---|---|
| `marts.player_game_pbp` | player, game | `(game_id, player_id)` | `core.events`, `staging.event_lineups` (validation only) |
| `marts.player_game` | player, game | `(game_id, player_id)` | official box + our seconds on court |
| `marts.player_season` | player, season, type, team | `(season_end_year, season_type, player_id, team_id)` | `marts.player_game` |
| `marts.team_game`, `marts.team_season` | team, game / season | `(game_id, team_id)` / `(season_end_year, season_type, team_id)` | box + official possessions |
| `marts.shot_zones` | player, season, zone | `(season_end_year, season_type, player_id, zone)` | `core.shots` |

All of them are rebuilt from scratch by the pipeline (the only writer); Streamlit opens the
database read-only.

## Open questions for the owner

1. Which layer-1 page first? Suggested: Games, then Player page.
2. Single multi-page Streamlit app, or a different front end later? (Streamlit is in CLAUDE.md.)
3. Public site or local only? Publishing needs a decision on data terms first: ramirobentes
   has no stated licence and NBA.com has terms of use. Until decided, everything stays local
   and only derived summaries may leave the machine. **[待確認]**
4. Which tracking-based custom metrics do you want first? (Needs your possession code.)
