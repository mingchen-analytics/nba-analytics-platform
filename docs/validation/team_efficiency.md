# Team efficiency mart: check against the official box score

Our team points (possession points + technical and between-possession free throws) against NBA.com's season box
score (`marts.team_season`). Numbers only. Ratings: `marts.team_efficiency_season`.

Team-seasons compared: **1,372**; equal: **1,365**; different: **7**; without a box score: 0.

| season | type | team | ours | official | difference | games without play-by-play |
|---|---|---|---|---|---|---|
| 1996-97 | regular | CLE | 7,173 | 7,180 | -7 | 0 |
| 1996-97 | regular | DEN | 8,020 | 8,013 | +7 | 0 |
| 1998-99 | regular | BKN | 4,569 | 4,573 | -4 | 0 |
| 2003-04 | regular | WAS | 7,531 | 7,528 | +3 | 0 |
| 2012-13 | regular | LAL | 8,380 | 8,381 | -1 | 0 |
| 2024-25 | playoffs | GSW | 1,138 | 1,237 | -99 | 1 |
| 2024-25 | playoffs | MIN | 1,548 | 1,636 | -88 | 1 |

Differences come from games whose source score and official box disagree, or incomplete box scores (see `docs/validation/box_vs_pbp.md` and check 111 in `docs/validation/possession_summary.md`), or from a game that has a box score but no play-by-play (last column; it has no possessions).
