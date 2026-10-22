# RAPM prototype: 2024-25 regular

Ridge regression on our own possessions (`metrics/rapm.py`). Numbers only. **Prototype**: `marts.player_rapm` waits for the owner's approval; every choice below is `rules.yaml` `rapm` and marked [待確認].

- Observations: **236,863** possessions; credit: `end_lineup`; end-of-period heaves excluded; garbage time excluded.
- Players with their own column: **472**; pooled into the replacement column: 94 (fewer than 500 possessions). Replacement player: offense -2.09, defense -0.39 points per 100.
- League average: 112.7 points per 100 possessions; home court: **+1.56** points per 100.

Standard errors: bootstrap of whole games, 50 resamples, same penalty. Players with 1,000+ possessions: median standard error **1.22** points per 100 (offense 0.86, defense 0.86); **73** of 432 players have a rating more than two standard errors from zero (10 of the top 10, 10 of the bottom 10). Sampling noise only; the shrinkage bias of ridge is not in it.

## Penalty (cross-validation grouped by game)

Folds: 5. Chosen alpha: **3,162**; grid extended 0 time(s); best at the edge of the grid: False. Mean squared error 1.42760 (± 0.00273) against 1.43042 for predicting the mean: **0.20 %** lower (small by nature: points in one possession are mostly luck; what matters is that the gain is real, larger than its standard error, and the best penalty lies inside the grid).

| alpha | mean squared error | standard error |
|---|---|---|
| 100 | 1.43141 | 0.00286 |
| 178 | 1.43061 | 0.00285 |
| 316 | 1.42971 | 0.00284 |
| 562 | 1.42883 | 0.00282 |
| 1,000 | 1.42813 | 0.00279 |
| 1,778 | 1.42771 | 0.00276 |
| 3,162 | 1.42760 | 0.00273 |
| 5,623 | 1.42775 | 0.00269 |
| 10,000 | 1.42809 | 0.00267 |
| 17,783 | 1.42854 | 0.00264 |
| 31,623 | 1.42902 | 0.00261 |
| 56,234 | 1.42946 | 0.00260 |
| 100,000 | 1.42981 | 0.00258 |

## Reliability (two random halves of the games, same penalty)

Players with 1,000+ possessions in both halves: **340**. Correlation between halves: RAPM **0.37**, offense 0.43, defense 0.26.

## How much the choices matter

Same penalty, players with 1,000+ possessions; RAPM of the configured fit against a variant.

| variant | players | correlation | mean abs difference | max abs difference |
|---|---|---|---|---|
| heaves and garbage time both in | 432 | 0.986 | 0.21 | 1.77 |
| heaves out, garbage time in | 432 | 0.988 | 0.19 | 1.70 |

Correlation with the raw on/off net (`marts.player_onoff_season`, 381 players): **0.81**.

## Highest and lowest RAPM (players with 1,000+ possessions; points per 100)

| | player | RAPM | ± standard error | offense | defense | possessions |
|---|---|---|---|---|---|---|
| top | Shai Gilgeous-Alexander | +6.12 | 1.06 | +4.30 | +1.82 | 10,888 |
| top | Nikola Jokić | +5.85 | 1.25 | +5.77 | +0.08 | 10,812 |
| top | Dorian Finney-Smith | +5.70 | 1.46 | +3.47 | +2.23 | 7,257 |
| top | Giannis Antetokounmpo | +5.34 | 1.27 | +3.64 | +1.70 | 9,397 |
| top | Luka Dončić | +4.44 | 1.36 | +3.10 | +1.34 | 7,241 |
| top | Franz Wagner | +3.96 | 1.24 | +1.62 | +2.34 | 8,066 |
| top | Christian Braun | +3.95 | 1.42 | +3.62 | +0.34 | 11,047 |
| top | Ivica Zubac | +3.88 | 1.55 | +1.31 | +2.57 | 10,583 |
| top | Al Horford | +3.86 | 1.28 | +2.09 | +1.77 | 6,622 |
| top | Pascal Siakam | +3.85 | 1.06 | +0.54 | +3.31 | 10,521 |
| bottom | Nick Smith Jr. | -4.68 | 1.16 | -3.05 | -1.63 | 5,322 |
| bottom | Bub Carrington | -4.67 | 1.06 | -2.91 | -1.75 | 10,174 |
| bottom | Alex Len | -4.36 | 1.14 | -1.90 | -2.46 | 1,321 |
| bottom | Tidjane Salaün | -4.03 | 1.35 | -4.05 | +0.02 | 4,740 |
| bottom | Yves Missi | -3.87 | 1.40 | -1.57 | -2.30 | 7,895 |
| bottom | Cody Williams | -3.73 | 1.75 | -2.50 | -1.23 | 4,379 |
| bottom | Nic Claxton | -3.62 | 1.49 | -3.13 | -0.49 | 7,430 |
| bottom | Keyonte George | -3.49 | 1.11 | -0.07 | -3.43 | 8,626 |
| bottom | Jordan Hawkins | -3.47 | 1.36 | -1.93 | -1.55 | 5,275 |
| bottom | Kyle Kuzma | -3.42 | 1.44 | -2.66 | -0.76 | 8,107 |

Reading: ridge shrinks every player toward the average, so the spread is smaller than raw on/off. Differences between players that are smaller than their standard errors are noise.
