# Matchup data: coverage

`marts.matchup_pairs` (NBA.com matchup data, 2017-18 -> 2024-25) against `core.games`. Numbers only.

| season | type | player pairs | games in the matchup data | games in core (with play-by-play) | games without matchups |
|---|---|---|---|---|---|
| 2017-18 | regular | 231,888 | 1,222 | 1,230 | 8 |
| 2018-19 | regular | 232,985 | 1,223 | 1,230 | 7 |
| 2019-20 | regular | 181,840 | 967 | 1,059 | 92 |
| 2020-21 | regular | 202,195 | 1,080 | 1,080 | 0 |
| 2021-22 | regular | 229,901 | 1,229 | 1,230 | 1 |
| 2022-23 | regular | 229,185 | 1,230 | 1,230 | 0 |
| 2023-24 | regular | 230,703 | 1,227 | 1,230 | 3 |
| 2024-25 | regular | 231,961 | 1,229 | 1,230 | 1 |
| 2017-18 | playoffs | 14,555 | 82 | 82 | 0 |
| 2018-19 | playoffs | 14,616 | 82 | 82 | 0 |
| 2019-20 | playoffs | 14,071 | 83 | 83 | 0 |
| 2020-21 | playoffs | 15,060 | 85 | 85 | 0 |
| 2021-22 | playoffs | 15,312 | 87 | 87 | 0 |
| 2022-23 | playoffs | 13,817 | 84 | 84 | 0 |
| 2023-24 | playoffs | 13,600 | 82 | 82 | 0 |
| 2024-25 | playoffs | 15,000 | 84 | 83 | 0 |

Sanity: for 181,745 defender-games with 10+ minutes on the floor, the sum of a defender's matched seconds is **0.40** of his time on our stints (5th percentile 0.34, 95th 0.46); the defender is matched only while his team defends (about half the time) and not always, so the ratio is expected below 0.5.
