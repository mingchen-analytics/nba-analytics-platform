# 2017-18 corrections: audit of the 16 time changes

Each row is an event whose clock was changed (`clock` / `secs_game` rows of `corrections/corrections.csv`, added 2026-10-22), shown in the corrected order with the event before it and the event after it (event number, type, team, clock). Compare with NBA.com's play-by-play of the game (the event numbers are the official ones). Team tags and clocks only. Rule: after a **blocked** shot the rebound happens at the shot's time (the owner checked the video of 0021700079 event 90: 3:58), so it takes the missed shot's time; otherwise the cause is not known and the rebound takes the next event's time, the latest time that keeps the clock from running backwards (the true time lies between the previous and the next event).

| game | date | home / away | event | type | old clock | new clock | moved earlier by (s) | event before | event after | same team as the next event | previous shot blocked |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `0021700079` | 2017-10-28 | CHI / OKC | 90 | rebound | 03:49 | 03:58 | 9.0 | 88 missed shot CHI 03:58 | 91 made shot OKC 03:55 | yes | yes |
| `0021700075` | 2017-10-27 | GSW / WAS | 392 | rebound | 09:17 | 09:23 | 6.0 | 391 missed shot GSW 09:23 | 393 made shot WAS 09:18 | yes | yes |
| `0021700192` | 2017-11-13 | WAS / SAC | 266 | rebound | 02:30 | 02:34 | 4.0 | 264 missed shot WAS 02:34 | 267 foul SAC 02:31 | yes | yes |
| `0021700012` | 2017-10-18 | PHX / POR | 300 | rebound | 02:04 | 02:07 | 3.0 | 298 missed shot PHX 02:07 | 301 foul PHX 02:05 | no | yes |
| `0021700215` | 2017-11-16 | BOS / GSW | 469 | rebound | 02:04 | 02:07 | 3.0 | 468 missed shot GSW 02:07 | 470 missed shot BOS 02:07 | yes | no |
| `0021700192` | 2017-11-13 | WAS / SAC | 260 | rebound | 03:12 | 03:14 | 2.0 | 259 missed shot WAS 03:17 | 262 substitution SAC 03:14 | yes | no |
| `0021700199` | 2017-11-13 | GSW / ORL | 350 | rebound | 09:09 | 09:11 | 2.0 | 349 missed shot GSW 09:14 | 351 missed shot ORL 09:11 | yes | no |
| `0021700042` | 2017-10-23 | MIA / ATL | 607 | rebound | 01:31 | 01:32 | 1.0 | 606 missed shot MIA 01:35 | 608 made shot ATL 01:32 | yes | no |
| `0021700086` | 2017-10-29 | IND / SAS | 476 | rebound | 11:24 | 11:25 | 1.0 | 475 missed shot IND 11:27 | 477 turnover SAS 11:25 | yes | no |
| `0021700090` | 2017-10-29 | CLE / NYK | 470 | rebound | 02:12 | 02:13 | 1.0 | 469 missed shot CLE 02:15 | 471 turnover NYK 02:13 | yes | no |
| `0021700104` | 2017-10-31 | LAL / DET | 257 | rebound | 02:17 | 02:18 | 1.0 | 256 missed shot DET 02:21 | 258 turnover LAL 02:18 | yes | no |
| `0021700303` | 2017-11-29 | DET / PHX | 237 | rebound | 04:14 | 04:15 | 1.0 | 236 missed shot PHX 04:20 | 238 turnover DET 04:15 | yes | no |
| `0021700200` | 2017-11-13 | LAC / PHI | 524 | made shot | 00:00.3 | 00:00.6 | 0.3 | 523 rebound LAC 00:01.6 | 525 missed shot PHI 00:00.6 | no | no |
| `0021700252` | 2017-11-21 | LAL / CHI | 648 | rebound | 00:00.1 | 00:00.4 | 0.3 | 647 free throw LAL 00:02.0 | 649 missed shot CHI 00:00.4 | yes | no |
| `0021700002` | 2017-10-17 | GSW / HOU | 488 | rebound | 00:57.8 | 00:57.9 | 0.1 | 487 missed shot GSW 01:02 | 489 turnover HOU 00:57.9 | yes | no |
| `0021700040` | 2017-10-22 | LAL / NOP | 164 | rebound | 00:00.5 | 00:00.6 | 0.1 | 163 missed shot NOP 00:04.2 | 165 missed shot LAL 00:00.6 | yes | no |

Size of the changes (seconds, number of rows): 0.1 s: 2, 0.3 s: 2, 1.0 s: 5, 2.0 s: 2, 3.0 s: 2, 4.0 s: 1, 6.0 s: 1, 9.0 s: 1.
