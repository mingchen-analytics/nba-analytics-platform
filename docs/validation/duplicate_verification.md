# Duplicated source events verified against the official PBP

Run 2026-10-17. IDs, codes and column names only.

(a) copies differ only in ramirobentes-derived columns; (b) the official PBP
(shufinskiy `nbastats_*`) has that game's event number exactly once.

**8 of 8** events meet both conditions → 8 new `source duplicate verified against official PBP` corrections (one copy dropped; the copies differ only in derived columns we do not load).

| file | game_id | event_num | msg | act | differing columns | NBA fields differing | (a) | official count | (b) | applied |
|---|---|---|---|---|---|---|---|---|---|---|
| pbp_regular_2001.parquet | 0020000409 | 435 | 6 | 14 | total_fta player_ft shot_pts_home | — | yes | 1 | yes | **yes** |
| pbp_regular_2003.parquet | 0020200954 | 472 | 6 | 14 | player_ft shot_pts_away | — | yes | 1 | yes | **yes** |
| pbp_regular_2004.parquet | 0020300970 | 318 | 6 | 2 | player_ft poss_home | — | yes | 1 | yes | **yes** |
| pbp_regular_2012.parquet | 0021100220 | 540 | 6 | 1 | player_ft shot_pts_home poss_home | — | yes | 1 | yes | **yes** |
| pbp_regular_2013.parquet | 0021200299 | 253 | 6 | 2 | player_ft shot_pts_home poss_home | — | yes | 1 | yes | **yes** |
| pbp_regular_2013.parquet | 0021200758 | 207 | 6 | 3 | player_ft shot_pts_away poss_away | — | yes | 1 | yes | **yes** |
| pbp_regular_2018.parquet | 0021701140 | 640 | 6 | 1 | player_ft shot_pts_home poss_home | — | yes | 1 | yes | **yes** |
| pbp_regular_2020.parquet | 0021900622 | 454 | 6 | 2 | player_ft poss_away | — | yes | 1 | yes | **yes** |

Not corrected: 0.
