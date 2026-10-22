# NBA.com season tracking: plausibility

League medians (players with 20+ games and 300+ minutes) per season, and player-seasons flagged `movement_suspect`
(average speed above 5.5 mph; kept in `marts.player_tracking_season`, hidden by default on the Tracking page). Numbers only.

| season | type | player-seasons | flagged | max speed (mph) | median miles / 36 min | median speed (mph) | median possession time / min | median touches / 36 min |
|---|---|---|---|---|---|---|---|---|
| 2013-14 | regular | 482 | 0 | 4.84 | 2.53 | 4.23 | 0.051 | 56.5 |
| 2014-15 | regular | 492 | 0 | 5.88 | 2.52 | 4.2 | 0.054 | 58.3 |
| 2015-16 | regular | 476 | 0 | 4.92 | 2.55 | 4.26 | 0.054 | 59.9 |
| 2016-17 | regular | 486 | 0 | 7.24 | 2.55 | 4.26 | 0.055 | 58.0 |
| 2017-18 | regular | 540 | 0 | 5.54 | 2.59 | 4.35 | 0.056 | 59.2 |
| 2018-19 | regular | 530 | 0 | 6.28 | 2.73 | 4.25 | 0.055 | 60.6 |
| 2019-20 | regular | 529 | 0 | 4.85 | 2.69 | 4.22 | 0.057 | 58.6 |
| 2020-21 | regular | 540 | 0 | 7.51 | 2.7 | 4.26 | 0.057 | 56.2 |
| 2021-22 | regular | 605 | 0 | 5.69 | 2.69 | 4.2 | 0.058 | 56.6 |
| 2022-23 | regular | 539 | 0 | 5.13 | 2.7 | 4.19 | 0.055 | 56.3 |
| 2023-24 | regular | 572 | 0 | 5.29 | 2.75 | 4.26 | 0.057 | 56.5 |
| 2024-25 | regular | 569 | 0 | 5.18 | 2.59 | 4.41 | 0.11 | 52.3 |
| 2025-26 | regular | 582 | 44 | 22.58 | 2.67 | 4.47 | 0.074 | 52.1 |
| 2013-14 | playoffs | 204 | 0 | 4.97 | 2.55 | 4.3 | 0.061 | 63.6 |
| 2014-15 | playoffs | 208 | 0 | 5.26 | 2.59 | 4.22 | 0.072 | 61.3 |
| 2015-16 | playoffs | 215 | 0 | 4.98 | 2.42 | 4.03 | 0.051 | 54.5 |
| 2016-17 | playoffs | 215 | 0 | 5.0 | None | None | None | None |
| 2017-18 | playoffs | 210 | 0 | 5.43 | 2.42 | 4.03 | 0.05 | 49.7 |
| 2018-19 | playoffs | 212 | 0 | 5.29 | 2.66 | 4.13 | 0.072 | 62.4 |
| 2019-20 | playoffs | 217 | 0 | 5.32 | 2.65 | 4.18 | 0.052 | 56.3 |
| 2020-21 | playoffs | 239 | 0 | 6.42 | 2.62 | 4.1 | 0.035 | 53.1 |
| 2021-22 | playoffs | 217 | 0 | 5.56 | 2.55 | 3.98 | 0.099 | 63.0 |
| 2022-23 | playoffs | 217 | 0 | 5.37 | 2.52 | 3.94 | 0.084 | 55.6 |
| 2023-24 | playoffs | 214 | 0 | 5.53 | 2.68 | 4.19 | 0.035 | 49.3 |
| 2024-25 | playoffs | 219 | 0 | 5.06 | 2.65 | 4.54 | 0.137 | 55.4 |
| 2025-26 | playoffs | 230 | 0 | 4.89 | 2.66 | 4.38 | 0.065 | 57.3 |

Reading the table: miles / 36 min and speed are stable from 2013-14 to 2024-25 and break only in the flagged season. Possession time per minute and touches per 36 minutes change level from 2024-25 (NBA.com's tracking measurement changed), so they are not comparable across that line.

## Teams with flagged player-seasons

| season | type | team | flagged players | share of the flagged players' minutes in the team's tracked minutes |
|---|---|---|---|---|
| 2025-26 | regular | DAL | 9 | 66 % |
| 2025-26 | regular | MIL | 9 | 66 % |
| 2025-26 | regular | NYK | 9 | 75 % |
| 2025-26 | regular | POR | 9 | 74 % |
| 2025-26 | regular | WAS | 5 | 27 % |
| 2025-26 | regular | ATL | 2 | 15 % |
| 2025-26 | regular | PHX | 1 | 2 % |
