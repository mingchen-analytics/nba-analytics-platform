# NBA.com (nba_api) endpoint inventory

Probed 2026-10-18 00:59 with nba_api, 34 requests (≥ 4 s apart, serial).
Filter support is read from each endpoint's parameters (nba_api); responses cached in
`data/raw/nba_api/probe/`. Sizes are for one request of the most recent season.

| data class | endpoint | key parameters | filters | earliest season | probe result / notes |
|---|---|---|---|---|---|
| player tracking: SpeedDistance | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=SpeedDistance, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 582 rows, 70 KB |
| player tracking: Possessions | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=Possessions, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 582 rows, 79 KB |
| player tracking: Passing | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=Passing, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 582 rows, 66 KB |
| player tracking: Drives | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=Drives, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 582 rows, 87 KB |
| player tracking: CatchShoot | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=CatchShoot, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 582 rows, 62 KB |
| player tracking: PullUpShot | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=PullUpShot, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 582 rows, 60 KB |
| player tracking: Rebounding | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=Rebounding, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 578 rows, 116 KB |
| player tracking: Defense | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=Defense, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 582 rows, 54 KB |
| player tracking: ElbowTouch | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=ElbowTouch, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 582 rows, 84 KB |
| player tracking: PostTouch | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=PostTouch, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 582 rows, 83 KB |
| player tracking: PaintTouch | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=PaintTouch, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 582 rows, 87 KB |
| player tracking: Efficiency | LeagueDashPtStats | season, season_type_all_star, pt_measure_type=Efficiency, player_or_team=Player/Team | DateFrom/To: yes; Period: no | 2013-14 | ok, 582 rows, 80 KB |
| hustle (season) | LeagueHustleStatsPlayer / LeagueHustleStatsTeam | season, season_type_all_star | DateFrom/To: yes; Period: no | 2015-16 | player ok, 581 rows, 90 KB; team ok, 30 rows, 5 KB |
| hustle (single game) | BoxScoreHustleV2 | game_id | DateFrom/To: no; Period: no | see note | 2025-26 game ok, 12 KB; 2015-16 game ok, 2 KB |
| tracking box score (single game) | BoxScorePlayerTrackV3 | game_id | DateFrom/To: no; Period: no | see note | 2025-26 game ok, 22 KB; 2013-14 game ok, 21 KB |
| shot context: closest defender distance | LeagueDashPlayerPtShot (team: LeagueDashTeamPtShot) | season, close_def_dist_range_nullable (one range per request) | DateFrom/To: yes; Period: yes | 2013-14? (probe: shotctx_close_def_2013-14 → ok, 464 rows, 58 KB; shotctx_close_def_2013-14 → ok, 464 rows, 58 KB) | ok, 553 rows, 70 KB |
| shot context: touch time | LeagueDashPlayerPtShot (team: LeagueDashTeamPtShot) | season, touch_time_range_nullable (one range per request) | DateFrom/To: yes; Period: yes | 2013-14? (probe: shotctx_close_def_2013-14 → ok, 464 rows, 58 KB; shotctx_close_def_2013-14 → ok, 464 rows, 58 KB) | ok, 579 rows, 76 KB |
| shot context: dribbles | LeagueDashPlayerPtShot (team: LeagueDashTeamPtShot) | season, dribble_range_nullable (one range per request) | DateFrom/To: yes; Period: yes | 2013-14? (probe: shotctx_close_def_2013-14 → ok, 464 rows, 58 KB; shotctx_close_def_2013-14 → ok, 464 rows, 58 KB) | ok, 578 rows, 76 KB |
| shot context: shot clock | LeagueDashPlayerPtShot (team: LeagueDashTeamPtShot) | season, shot_clock_range_nullable (one range per request) | DateFrom/To: yes; Period: yes | 2013-14? (probe: shotctx_close_def_2013-14 → ok, 464 rows, 58 KB; shotctx_close_def_2013-14 → ok, 464 rows, 58 KB) | ok, 504 rows, 62 KB |
| play type (Synergy) | SynergyPlayTypes | season, play_type_nullable (one of ~11), type_grouping_nullable=offensive/defensive, player_or_team_abbreviation=P/T | DateFrom/To: no; Period: no | 2015-16? (probe: playtype_Isolation_offensive_P_2015-16 → ok, 287 rows, 54 KB; playtype_Isolation_offensive_P_2014-15 → ok, 314 rows, 59 KB) | offense P ok, 284 rows, 54 KB; defense P ok, 394 rows, 75 KB; offense T ok, 30 rows, 6 KB |
| official possessions per team-game | TeamGameLogs (measure_type=Advanced) | season_nullable, season_type_nullable, measure_type_player_game_logs_nullable=Advanced — **whole season in one request** | DateFrom/To: yes; Period: yes | 1996-97 | ok, 2,794 rows, 949 KB; 1996-97 ok, 2,525 rows, 857 KB; possession columns: POSS |

Notes:
- "earliest season" for season-level endpoints comes from probing two early seasons; a value with `?`
  means the probe was not conclusive.
- Single-game box scores: availability is per game; the probe tested one modern and one early game.
- Per-period data is available on several endpoints (Period filter) but is not downloaded (owner).
- **TeamGameLogs (Advanced)** has a `POSS` column (also `PACE`, `E_PACE`). Without
  `season_type_nullable` one request returns **every game type** of the season — for 2025-26:
  2,460 regular-season rows (`002…`), 170 playoffs (`004…`), 142 preseason (`001…`), 12
  play-in (`005…`), 8 All-Star (`003…`), 2 NBA Cup final (`006…`). Filter by game-ID prefix (or
  pass the season type); 1996-97 also returns data, so official possessions exist for every season.
- **BoxScoreHustleV2** for a 2015-16 game returns an empty shell (team IDs 0, no players): single-game
  hustle data starts later than the season-level hustle tables (2015-16). Treat empty shells as
  "not available", not as an error.
- **BoxScorePlayerTrackV3** returned a full box score for a 2013-14 game (tracking era starts 2013-14).
- **SynergyPlayTypes** returned rows for 2014-15 as well as 2015-16: the earliest season is 2014-15
  or earlier (not probed further, request budget).
- Requests: 34 of 40 used, 0 failures, no throttling seen at ~4.5 s spacing.
