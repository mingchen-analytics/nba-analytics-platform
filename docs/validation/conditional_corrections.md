# Conditional corrections (plan 2026-10-17, step 2)

Run 2026-10-17. IDs and numbers only.

## 1. Duplicated source events

8 duplicated events; 0 identical in every raw column → 0 `source exact duplicate` corrections written.

Not corrected (some raw column differs):

| file | game_id | event_num | msg | act | differing columns |
|---|---|---|---|---|---|
| pbp_regular_2001.parquet | 0020000409 | 435 | 6 | 14 | total_fta player_ft shot_pts_home |
| pbp_regular_2003.parquet | 0020200954 | 472 | 6 | 14 | player_ft shot_pts_away |
| pbp_regular_2004.parquet | 0020300970 | 318 | 6 | 2 | player_ft poss_home |
| pbp_regular_2012.parquet | 0021100220 | 540 | 6 | 1 | player_ft shot_pts_home poss_home |
| pbp_regular_2013.parquet | 0021200299 | 253 | 6 | 2 | player_ft shot_pts_home poss_home |
| pbp_regular_2013.parquet | 0021200758 | 207 | 6 | 3 | player_ft shot_pts_away poss_away |
| pbp_regular_2018.parquet | 0021701140 | 640 | 6 | 1 | player_ft shot_pts_home poss_home |
| pbp_regular_2020.parquet | 0021900622 | 454 | 6 | 2 | player_ft poss_away |

## 2. Player keys without an ID (verified against BigDataBall)

- `0021401022` (pbp_regular_2015.parquet): 48/48 rows consistent with BigDataBall → **applied** (48 new correction rows; proposed IDs [202711])
