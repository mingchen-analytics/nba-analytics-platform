# Data dictionary

Database: DuckDB, default `%LOCALAPPDATA%\nba_platform\nba_platform.duckdb` (override with
`NBA_PLATFORM_DB`). DDL: `sql/schema.sql`. Only the pipeline writes; everything else opens it
read-only. Schemas: `core` (our tables), `staging` (source data kept as given), `reference`
(other people's numbers, for comparison only), `validation` (check results).

Conventions (CLAUDE.md): `game_id` TEXT, 10 characters with leading zeros; `player_id`,
`team_id` INTEGER NBA IDs; seasons as `season` TEXT `'2004-05'` + `season_end_year` INTEGER
`2005`; `season_type` `'regular'` | `'playoffs'`; time as `period` + `secs_elapsed_game`
(seconds since tip-off, OT periods 300 s). Unknown → NULL.

---

## core.games

One row = one game. **Primary key:** `game_id`.

| column | type | meaning |
|---|---|---|
| game_id | TEXT | NBA game ID (`002…` regular season, `004…` playoffs) |
| season | TEXT | e.g. `2004-05` |
| season_end_year | INTEGER | e.g. `2005` |
| season_type | TEXT | `regular` / `playoffs` |
| game_date | DATE | local game date |
| home_team_id, away_team_id | INTEGER | NBA team IDs |
| home_score, away_score | INTEGER | final score (running score on the game's last event) |
| num_periods | INTEGER | 4 + overtimes |
| source | TEXT | `ramirobentes`, or `nba_api_box` for a game missing from the play-by-play |
| pbp_missing | BOOLEAN | TRUE = no play-by-play (row built from the box score; `num_periods` NULL, no events) |
| known_issue | TEXT | issue from `core.known_gaps` (e.g. `pbp_missing`, `source_score_conflict`), else NULL |

## core.known_gaps

One row = one documented gap or source contradiction, from `corrections/known_gaps.csv`
(committed, re-applied on every load). **Primary key:** (`game_id`, `issue`). Validation
reports these with status `known` (a warning), not as failures.

| column | type | meaning |
|---|---|---|
| game_id | TEXT | game |
| season_end_year, season_type | | season |
| issue | TEXT | `pbp_missing` / `source_score_conflict` |
| reason | TEXT | what was observed |
| added_on | TEXT | date |

## core.events

One row = one NBA play-by-play event, in game order. **Unique keys:** (`game_id`, `event_seq`)
and (`game_id`, `source_event_num`) — both enforced by hard check 102.

| column | type | meaning |
|---|---|---|
| game_id | TEXT | game |
| event_seq | INTEGER | our order within the game, 1…n (ramirobentes `number_event`, ties by NBA event number) |
| source_event_num | INTEGER | NBA event number (joins to shot data) |
| period | INTEGER | 1–4, 5+ = overtime |
| clock | TEXT | game clock as shown (display only) |
| secs_elapsed_game | DOUBLE | seconds since tip-off (computed from period + clock) |
| team_id | INTEGER | team of the event; NULL for game-level rows (period start, official timeout, double technical) |
| event_type | TEXT | our vocabulary: `shot_made, shot_missed, free_throw, rebound, turnover, foul, substitution, timeout, jump_ball, violation, period_start, period_end, other` |
| event_subtype | INTEGER | NBA action code (e.g. FT 11 = "1 of 2", foul 14 = flagrant type 1) |
| source_msg_type | INTEGER | NBA message type as given (keeps `other` traceable) |
| player1_id, player2_id, player3_id | INTEGER | players involved; **roles depend on event type and era** (e.g. jump-ball order, blocker on a miss) |
| points | INTEGER | points scored on this event (made FG or made FT), else 0 |
| home_score, away_score | INTEGER | running score after the event |
| stint_id, possession_id, chance_id, foul_event_seq, is_technical_ft | | **reserved**, filled by the owner's stint / possession code (NULL now) |
| description | TEXT | source text (local only, never in committed reports) |
| source | TEXT | `ramirobentes` |

Rows not carried over: ramirobentes' synthetic msg 99 rows ("last possession of quarter"),
counted per season (check 103).

## core.shots

One row = one field-goal attempt with location. **Unique key:** (`game_id`, `source_event_num`)
(hard check 107); joins to `core.events` on the same columns.

| column | type | meaning |
|---|---|---|
| game_id, source_event_num | TEXT, INTEGER | the FGA event |
| player_id, team_id | INTEGER | shooter and team (agree with the event in > 99.99 %) |
| shot_type | TEXT | `2PT Field Goal` / `3PT Field Goal` |
| action_type | TEXT | NBA shot description category (e.g. `Driving Layup Shot`) |
| shot_zone_basic, shot_zone_area, shot_zone_range | TEXT | NBA shot-chart zones |
| distance_ft | DOUBLE | shot distance, feet |
| loc_x, loc_y | DOUBLE | court coordinates, tenths of a foot, rim at (0, 0) (see `core.shot_quality_flags`) |
| made | BOOLEAN | made / missed |
| source | TEXT | `shufinskiy` (NBA shot chart data) |

## core.shot_quality_flags

One row = one quality flag on one shot. Kept outside `core.shots`, so reloading shots never
removes flags (rebuilt by `validate/shot_quality.py`, which `pipeline --all` runs). **Primary
key:** (`game_id`, `source_event_num`, `flag`); joins to `core.shots` on the first two.

| column | type | meaning |
|---|---|---|
| game_id, source_event_num | TEXT, INTEGER | the shot |
| flag | TEXT | `rim_location_imprecise` — at (0, 0) = the rim in NBA coordinates, exact spot not recorded (seasons where > 5 % of shots sit there: 1996-97 → 2009-10); `rim_location_suspect` — at (0, 0) but a jump shot, 3-pointer or distance > 0; `early_season_location_suspect` — 1996-97 → 1999-00 |

## core.teams

One row = one NBA franchise ID. **Primary key:** `team_id`. Abbreviation and name are those of
the most recent season loaded (a franchise keeps its ID through relocations).

| column | type | meaning |
|---|---|---|
| team_id | INTEGER | NBA team ID |
| abbreviation | TEXT | latest abbreviation |
| name | TEXT | latest name |

## core.team_xref

One row = how one source abbreviation maps to a team ID in one season.
**Primary key:** (`source`, `season_end_year`, `source_team_key`).

| column | type | meaning |
|---|---|---|
| source | TEXT | `ramirobentes` |
| season_end_year | INTEGER | season |
| source_team_key | TEXT | abbreviation in that source and season (e.g. `NOH`) |
| team_id | INTEGER | NBA team ID (from shot-chart joins, ≥ 99 % agreement required) |
| team_name | TEXT | name in that season |
| method | TEXT | `auto` / `manual` |

## core.players

One row = one NBA player ID. **Primary key:** `player_id`.

| column | type | meaning |
|---|---|---|
| player_id | INTEGER | NBA player ID |
| name | TEXT | name in the most recent season |
| name_variants | TEXT[] | every spelling seen |

## core.player_xref

One row = one source's player key mapped to an NBA player ID.
**Primary key:** (`source`, `source_player_key`).

| column | type | meaning |
|---|---|---|
| source | TEXT | `ramirobentes` (`"ID Name"` strings) or `bigdataball` (names) |
| source_player_key | TEXT | the key as the source writes it |
| player_id | INTEGER | NBA player ID |
| method | TEXT | `auto` / `manual` (BigDataBall rules: `docs/validation/bigdataball_crosscheck.md`) |

## staging.event_lineups

One row = the ten players on court for one event, exactly as the source gives them (not
stints). **Key:** (`game_id`, `event_seq`), one row per `core.events` row (hard check 106).

| column | type | meaning |
|---|---|---|
| game_id, event_seq | TEXT, INTEGER | the event |
| home_player_ids, away_player_ids | INTEGER[] | on-court players; on a substitution row the source shows the **post**-sub lineup (CLAUDE.md defines the sub row as pre-sub — to be aligned in stint building) |
| source | TEXT | `ramirobentes` |

## staging.player_names

One row = one (player ID, spelling) seen in one source file. Feeds `core.players` and
`core.player_xref`.

| column | type | meaning |
|---|---|---|
| source, season_end_year, season_type | | file |
| player_id | INTEGER | NBA player ID |
| name | TEXT | spelling |
| source_player_key | TEXT | `"ID Name"` |
| n_rows | BIGINT | how often it appears |

## reference.pbpstats_possessions

One row = one possession **as pbpstats counts it** (shufinskiy `pbpstats_*`, 2000-01 →
2024-25). Reference only — never used to build our possessions. **Key:** (`game_id`,
`possession_seq`).

| column | type | meaning |
|---|---|---|
| season_end_year, season_type | | season |
| game_id | TEXT | game |
| possession_seq | INTEGER | order in the game (period, then start time) |
| defense_team_abbr | TEXT | pbpstats `OPPONENT` |
| period | INTEGER | period |
| start_time, end_time | TEXT | clock left in the period |
| start_type | TEXT | pbpstats start type (e.g. `Off Steal`) |
| start_score_diff | INTEGER | score margin at the start, offense perspective |
| n_event_rows | INTEGER | event rows in the source |
| fg2a, fg2m, fg3a, fg3m, offensive_rebounds, turnovers, shooting_fouls_drawn, nonshooting_fouls_fts | INTEGER | pbpstats counts |
| source | TEXT | `shufinskiy_pbpstats` |

## validation.results

One row = one check of one season, from the latest run. Rendered in
`docs/validation/season_report.md` and the dashboard (`app/data_health.py`).

| column | type | meaning |
|---|---|---|
| run_at | TIMESTAMP | when it ran |
| season_end_year, season_type | | season |
| check_id | INTEGER | CLAUDE.md checks 1–11, plus 0 (staging), 101–110 (ours) |
| check_name | TEXT | description |
| level | TEXT | `hard` (failure = season not loaded) / `warning` (reported) |
| status | TEXT | `pass` / `fail` / `skip` |
| n_checked, n_failed | BIGINT | counts |
| detail | TEXT | JSON with numbers and examples (may quote source rows; local only) |

---

## reference.nba_player_box

Official player box score, one row per player and game, from the cached NBA.com
LeagueGameLog (`reference/player_box.py`). 786,768 rows, 37,986 games, every game in
`core.games`. Shown on the site as the box score; `marts.player_game_pbp` is compared with it.

| column | type | meaning |
|---|---|---|
| game_id, player_id, team_id | | project keys (`game_id` 10 characters) |
| season_end_year, season_type | | season |
| min | DOUBLE | minutes as NBA.com publishes them (whole minutes) |
| fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, reb, ast, stl, blk, tov, pf, pts, plus_minus | DOUBLE | counting stats as published, NULL when the source has none |

## marts.player_game_pbp

The same box score **counted from `core.events`** (`marts/player_game_pbp.py`), for validation
only: 786,751 rows (games without play-by-play are not included). Rules: shots, free throws,
rebounds, assists, turnovers, blocks, personal fouls by event type and player role. Roles
differ by era: steal = player2 up to 2015-16 and in 2025-26, player3 in 2016-17 → 2024-25;
block = player3 (player2 in 2025-26); technical-type fouls (incl. subtype 32, flopping,
2023-24 →) are not personal fouls. Also `secs_played` (seconds on court, same accounting as
checks 5 and 6) and `plus_minus` (points while on court, the lineup shown on each event).
Compared with the official box in `docs/validation/box_vs_pbp.md`.

## marts.player_game, marts.player_season, marts.team_game, marts.team_season

Layer-1 dashboard tables (`marts/box_marts.py`), rebuilt from scratch, **real PRIMARY KEYs**.
Box stats are NBA.com values; `pbp_secs_played` is counted from our play-by-play;
`*_official*` columns come from NBA.com's official possessions (`POSS`), not ours.
Row counts and the points-vs-score consistency check: `docs/validation/box_marts.md`.

| table | rows | key | notes |
|---|---|---|---|
| `marts.player_game` | 786,768 | `(game_id, player_id)` | box stats, `min`, `pbp_secs_played`, `is_home`, `won`, `opponent_team_id`, `game_date` |
| `marts.player_season` | 22,572 | `(season_end_year, season_type, player_id, team_id)` | a traded player has one row per team; `games` = games in the box score; totals, `fg_pct`, `fg3_pct`, `ft_pct`, `efg_pct`, `ts_pct` (NULL without attempts), `mpg`/`ppg`/`rpg`/`apg`/`spg`/`bpg`/`tpg`, `pts_per36`/`reb_per36`/`ast_per36` |
| `marts.team_game` | 75,972 | `(game_id, team_id)` | sums of the player box, `opponent_pts`, `won`, `poss_official`, `pace_official` (NULL where NBA.com has none) |
| `marts.team_season` | 1,372 | `(season_end_year, season_type, team_id)` | totals, wins / losses, `poss_official`, `games_with_poss_official`, `ortg_official_poss`, `drtg_official_poss`, `pace_official_poss` (points ×100 / official possessions; to be replaced by our own possessions) |

## marts.shot_zones_league, marts.shot_zones_team, marts.shot_zones_player

Shooting by court zone (`marts/shot_zones.py`), rebuilt from `core.shots` (6,328,071 shots, each
counted once; the build stops if a shot is lost or duplicated). Zone = NBA `shot_zone_basic`
(`Unknown` if the source has none, never guessed). Shots with data-quality flags are counted;
`flagged_share` says how many. **Real PRIMARY KEYs.**

| table | rows | key | notes |
|---|---|---|---|
| `marts.shot_zones_league` | 420 | `(season_end_year, season_type, zone)` | `fga`, `fgm`, `fg_pct`, `freq` (share of all shots) |
| `marts.shot_zones_team` | 18,950 | `(season_end_year, season_type, team_id, side, zone)` | `side` = `offense` (own shots) / `defense` (shots allowed); `league_fg_pct`, `league_freq` for comparison |
| `marts.shot_zones_player` | 106,941 | `(season_end_year, season_type, player_id, zone)` | a traded player is combined; `fg_pct_percentile`, `freq_percentile` (0-100) only among players with at least `dashboard.shot_percentile_min_season_fga` (100) attempts in the season, and for accuracy at least `shot_percentile_min_zone_fga` (20) in the zone (`config/rules.yaml`); otherwise NULL |

## marts.player_tracking_season

NBA.com season tracking and hustle numbers, one row per player, season and team (`marts/tracking.py`),
**PRIMARY KEY** `(season_end_year, season_type, player_id, team_id)`, 9,759 rows (7,941 with hustle).
Every number is NBA.com's (**official**). `reference.nba_tracking` has one row per measure; this table
takes each shown column from its home measure (for example `DRIVE_FG_PCT` from `Drives`).
In the regular season NBA.com lists a traded player once, under his last team, with full-season totals.
Tracking misses some games, so `gp` can be lower than the box score (`docs/validation/tracking_vs_box.md`).

| group | columns (lower case) |
|---|---|
| keys and base | `gp`, `min` (from the Possessions measure), `hustle_gp` (hustle games; NULL before 2015-16), `movement_suspect` (average speed above `dashboard.tracking_max_plausible_avg_speed_mph` with at least `tracking_suspect_min_minutes` minutes: an implausible NBA.com value, kept and flagged; 44 player-seasons, all 2025-26 regular season) |
| Movement | `dist_miles`, `dist_miles_off`, `dist_miles_def`, `avg_speed`, `avg_speed_off`, `avg_speed_def` |
| Touches & passing | `touches`, `front_ct_touches`, `time_of_poss`, `avg_sec_per_touch`, `avg_drib_per_touch`, `pts_per_touch`, `passes_made`, `passes_received`, `potential_ast`, `ast_pts_created`, `secondary_ast`, `ft_ast`, `ast_to_pass_pct`, `paint_touches`, `paint_touch_fga`, `post_touches`, `post_touch_fga`, `elbow_touches` |
| Drives & shooting | `drives`, `drive_fga`, `drive_fg_pct`, `drive_pts`, `drive_ast`, `drive_tov`, `drive_pf`, `catch_shoot_*` (fga, fg3a, fg_pct, efg_pct, pts), `pull_up_*` (fga, fg3a, fg_pct, efg_pct, pts) |
| Rebounding & rim defense | `oreb_chances`, `oreb_chance_pct`, `dreb_chances`, `dreb_chance_pct`, `reb_chances`, `reb_chance_pct`, `reb_contest_pct`, `avg_reb_dist`, `def_rim_fga`, `def_rim_fgm`, `def_rim_fg_pct` |
| Hustle | `contested_shots` (+ `_2pt`, `_3pt`), `deflections`, `charges_drawn`, `screen_assists`, `screen_ast_pts`, `loose_balls_recovered`, `box_outs` |

`count` columns can be shown per game (divided by `gp`, or `hustle_gp` for hustle) or per 36 minutes;
`rate` columns (percentages, averages, per-touch values) are never scaled.

## marts.player_onoff_season, marts.lineup_stats, marts.pair_stats

On/off and lineup results counted from our own stints and possessions (`marts/onoff.py`; no NBA.com numbers).
New tables approved by the owner on 2026-10-22 (CLAUDE.md working agreement 8).
Each row carries `credit_method`, `rules_version` and `rules_profile`.

**Crediting (`pbpstats_hybrid`, decided by the owner 2026-10-22 for a substitution during a possession):** a
possession, with its heave and garbage flags, goes to the stint on the floor when it ends (the last of its
stint segments), for the offense and the defense lineup; the points of a field goal go with the possession; the
points of a free throw go to the stint on the floor at the foul (`foul_event_seq`); a counted free throw without a
linked foul goes to its own stint (56 in all seasons, listed in the report). Technical free throws and free
throws between possessions are counted nowhere. Heave and garbage possessions are counted, not excluded; their
counts are columns so a page can exclude them.

| table | key | columns |
|---|---|---|
| `marts.player_onoff_season` | `(season_end_year, season_type, team_id, player_id)` **PRIMARY KEY**; a traded player has one row per team | `games`, `on_secs`, `off_secs`; for `on_` and `off_` each: `o_poss`, `o_pts`, `o_heave_poss`, `o_garbage_poss` (offense) and `d_poss`, `d_pts`, `d_heave_poss`, `d_garbage_poss` (defense); `on_ortg`, `on_drtg`, `on_net`, `off_ortg`, `off_drtg`, `off_net` (per 100 possessions; NULL when there is no possession), `net_on_minus_off` |
| `marts.lineup_stats` | `(season_end_year, season_type, team_id, lineup_key)` **PRIMARY KEY**; `lineup_key` = the five player IDs sorted and joined with `-` | `p1..p5` (sorted), `games`, `stints`, `secs`, `o_poss`, `o_pts`, `o_heave_poss`, `o_garbage_poss`, `d_poss`, `d_pts`, `d_heave_poss`, `d_garbage_poss`, `ortg`, `drtg`, `net` |
| `marts.pair_stats` | `(season_end_year, season_type, team_id, player_a, player_b)` **PRIMARY KEY**, `player_a < player_b` | two teammates on the floor together (each stint gives 10 pairs per team): `games`, `stints`, `secs`, the same eight counts as `lineup_stats`, `ortg`, `drtg`, `net` |

`off_` = the team's total minus `on_` (same team and season). The build is rolled back unless every possession has an end
stint, credited points equal possession points, and per team-season the players' possessions, points and seconds are exactly
5 times the lineups' and the pairs' exactly 10 times (`docs/validation/onoff_checks.md`). Snapshot build (all 60 season files): 22,571 player rows, 420,946 lineups, 151,672 pairs.
`python -m nba_platform.marts.onoff --compare` also writes `docs/validation/onoff_credit_methods.md`: on/off under option A (`end_lineup`) against the hybrid.

## marts.team_efficiency_season

Points per 100 possessions per team and season from our own possessions (`marts/team_efficiency.py`), **PRIMARY KEY**
`(season_end_year, season_type, team_id)`, 1,372 rows; approved 2026-10-22. Three versions of every rating: all possessions
(`ortg`, `drtg`, `net`), `_ex_heave` (without end-of-period heaves) and `_ex_heave_garbage` (also without garbage time),
each with its `o_poss`, `o_pts`, `d_poss`, `d_pts`. `poss_per_game` = (offense + defense possessions) / 2 / games.
`pts_outside_possessions` = technical and between-possession free throws, so `o_pts + pts_outside_possessions` is the team's
total; it equals NBA.com's season box score for 1,365 of 1,372 team-seasons (`docs/validation/team_efficiency.md`; the two
largest gaps are the 2024-25 playoff game without play-by-play). Rows carry `rules_version`, `rules_profile`.
Four factors, offense `o_` and defense `d_` (the opponents' offense), from our own events and possessions: counts `fga`, `fgm`,
`fg3m`, `ftm` (made free throws inside possessions), `tov` (possessions ending in a turnover), `orb` (`num_chances - 1`, team
rebounds included), `drb_against` (possessions ending in a defensive rebound); rates `efg`, `tov_pct`, `orb_pct`, `ft_rate`. FGA equal
NBA.com's for 1,331 of 1,372 team-seasons; eFG% for BOS 2023-24 and GSW 2015-16 equal the official values.

## marts.player_game_tracking

NBA.com single-game tracking and hustle boxes, one row per player and game (`marts/tracking_games.py`), **PRIMARY KEY**
`(game_id, player_id)`; every number is NBA.com's (**official**). Coverage follows the downloads: every playoff season from
2013-14 and the regular seasons fetched so far (`reference.nba_box_tracking`, `reference.nba_box_hustle`). Rows of players who
did not play (0 seconds, "DNP") are left out and counted (`dnp_rows`). `has_tracking`, `has_hustle` say which box the row has;
`movement_suspect` flags a whole **game** when a player with at least `dashboard.tracking_game_min_secs` seconds averages more than
`dashboard.tracking_game_max_plausible_speed_mph` (3 games, all 2025-26 regular season). Columns: `secs_played`, `distance` (miles),
`speed` (mph), `touches`, `passes`, `assists`, `secondary_assists`, `free_throw_assists`, `rebound_chances_*`, `contested_` /
`uncontested_field_goals_made` / `_attempted`, `defended_at_rim_field_goals_*`, `contested_shots` (+ `2pt`, `3pt`), `deflections`,
`charges_drawn`, `screen_assists`, `screen_assist_points`, `loose_balls_recovered_total`, `box_outs`.

## marts.player_rapm (approved 2026-10-22; fitted per window)

Ridge RAPM per player and window (`metrics/rapm.py`), **PRIMARY KEY** `(window_id, player_id)`; `window_id` is for example
`2024-25 regular` or `2022-23 + 2023-24 + 2024-25 regular`. One observation per possession (points of the offense); features: five
offense columns, five defense columns, home court; penalty by cross-validation grouped by game. Columns: `off_poss`, `def_poss`
(possessions on the floor), `o_rapm`, `d_rapm` (positive = good), `rapm` = sum, all in points per 100 possessions relative to
an average player; `alpha`, `n_obs`, `home_points_per100`, and the choices that produced the row: `credit_method`
(`end_lineup`), `exclude_end_of_period_heave`, `exclude_garbage_time`, `min_possessions_for_own_column`, `rules_version`,
`rules_profile`. Players below the possession minimum share a replacement column and have no row. `o_se`, `d_se`, `rapm_se`: bootstrap standard errors (50 resamples of whole games, same penalty; NULL when none was run).

## marts.matchup_pairs

NBA.com matchup data, one row per defender and guarded player in a game (`marts/matchups.py`), 2017-18 → 2024-25, **PRIMARY KEY**
`(game_id, defender_id, offender_id)`; every number is NBA.com's (**official**), typed from `reference.matchups` (all text there, game
ids without their leading zeros: `21700001` becomes `0021700001`). `team_id` is the defender's team. `matchup_secs` the time he was matched
with the offender, `partial_possessions`, `pct_defender_time` / `pct_offense_time` / `pct_both_on` (as given), `switches_on`; counts while
matched: `player_pts` (the offender's), `team_pts`, `assists`, `potential_assists`, `turnovers`, `blocks`, `fgm`, `fga`, `fg3m`, `fg3a`,
`help_blocks`, `help_fgm`, `help_fga`, `ftm`, `fta`, `shooting_fouls`. Blank values are NULL. Hard checks: games in `core.games`, players and
teams known, the defender's team played the game, no duplicate keys, every value blank or a number. 1,886,689 rows, 10,076 games; 112 regular-season games
have no matchup data (92 of them in 2019-20), listed in `docs/validation/matchups_coverage.md`; 87 rows name a player who is not in that game's box score.

## core.possessions, core.possession_stint_segments (Claude-written, owner-reviewed)

Built per season by `python -m nba_platform.build_core --season-end-year Y --season-type T --step possessions [--profile pbpstats_compat|custom]`
(profile recorded per row in `rules_profile`, with `rules_version`). Loaded for **every season** (60 season files, 1996-97 → 2025-26):
7,275,201 possessions, 8,128,672 segments, 1,161,854 stints (`core.stints`, same pass); `rules_version`
`2026-10-21.6`. Columns follow CLAUDE.md "Core schema" (possessions); extra: `rules_profile`,
`timeout_team_id`. `core.events` gets `possession_id`, `chance_id` (chance number within the possession),
`is_between_possessions_ft`, `foul_event_seq` and `is_technical_ft` (free throws) for the same season. An event outside
every possession (`possession_id` NULL) is a technical free throw or a between-possessions free throw. Start types:
`after_made_shot`, `after_defensive_rebound`, `after_steal`, `after_dead_ball_turnover`, `after_free_throw`,
`after_jump_ball`, `period_start`, `implied` (the source never showed how the previous possession ended; counted in the
diagnostics, 57 in 2004-05); end types: `made_fg`, `defensive_rebound`, `turnover`, `made_ft`, `jump_ball`, `period_end`,
`implied`. Checks: 112 (hard), 7 and 8 (warnings), report `docs/validation/possession_check_{year}_{type}.md`.

---

## Not built yet (owner)

(nothing left of the core tables: `core.stints`, `core.possessions` and the segments exist for every season)
