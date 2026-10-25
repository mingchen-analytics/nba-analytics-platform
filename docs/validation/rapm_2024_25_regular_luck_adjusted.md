# RAPM: 2024-25 regular (luck_adjusted)

Ridge regression on our own possessions (`metrics/rapm.py`). Numbers only. **Prototype**: `marts.player_rapm` waits for the owner's approval; every choice below is `rules.yaml` `rapm` and marked [待確認].

- Variant **luck_adjusted**: every three-point attempt counts 3 x the shooter's expected percentage and every free throw his expected percentage (season rate shrunk toward the league's, priors 500 / 200 attempts); unknown shot types keep their result.
- Observations: **236,863** possessions; credit: `end_lineup`; end-of-period heaves excluded; garbage time excluded.
- Players with their own column: **472**; pooled into the replacement column: 94 (fewer than 500 possessions). Replacement player: offense -0.90, defense -1.44 points per 100.
- League average: 113.7 points per 100 possessions; home court: **+0.73** points per 100.

Standard errors: bootstrap of whole games, 50 resamples, same penalty. Players with 1,000+ possessions: median standard error **1.26** points per 100 (offense 0.89, defense 0.89); **80** of 432 players have a rating more than two standard errors from zero (10 of the top 10, 10 of the bottom 10). Sampling noise only; the shrinkage bias of ridge is not in it.

## Penalty (cross-validation grouped by game)

Folds: 5. Chosen alpha: **1,778**; grid extended 0 time(s); best at the edge of the grid: False. Mean squared error 0.76055 (± 0.00230) against 0.76277 for predicting the mean: **0.29 %** lower (small by nature: points in one possession are mostly luck; what matters is that the gain is real, larger than its standard error, and the best penalty lies inside the grid).

| alpha | mean squared error | standard error |
|---|---|---|
| 100 | 0.76231 | 0.00240 |
| 178 | 0.76188 | 0.00238 |
| 316 | 0.76141 | 0.00236 |
| 562 | 0.76098 | 0.00233 |
| 1,000 | 0.76068 | 0.00232 |
| 1,778 | 0.76055 | 0.00230 |
| 3,162 | 0.76060 | 0.00230 |
| 5,623 | 0.76080 | 0.00230 |
| 10,000 | 0.76109 | 0.00230 |
| 17,783 | 0.76144 | 0.00231 |
| 31,623 | 0.76180 | 0.00231 |
| 56,234 | 0.76212 | 0.00231 |
| 100,000 | 0.76236 | 0.00231 |

## Reliability (two random halves of the games, same penalty)

Players with 1,000+ possessions in both halves: **340**. Correlation between halves: RAPM **0.42**, offense 0.38, defense 0.37.

## How much the choices matter

Same penalty, players with 1,000+ possessions; RAPM of the configured fit against a variant.

| variant | players | correlation | mean abs difference | max abs difference |
|---|---|---|---|---|
| heaves and garbage time both in | 432 | 0.982 | 0.27 | 1.55 |
| heaves out, garbage time in | 432 | 0.985 | 0.22 | 1.43 |

Correlation with the raw on/off net (`marts.player_onoff_season`, 381 players): **0.65**.

## Highest and lowest RAPM (players with 1,000+ possessions; points per 100)

| | player | RAPM | ± standard error | offense | defense | possessions |
|---|---|---|---|---|---|---|
| top | Nikola Jokić | +6.77 | 1.10 | +6.18 | +0.58 | 10,812 |
| top | Shai Gilgeous-Alexander | +6.31 | 1.17 | +4.83 | +1.48 | 10,888 |
| top | Luke Kornet | +6.07 | 1.54 | +3.20 | +2.86 | 5,215 |
| top | Giannis Antetokounmpo | +5.75 | 1.13 | +3.87 | +1.88 | 9,397 |
| top | Luka Dončić | +5.26 | 1.44 | +3.11 | +2.16 | 7,241 |
| top | Franz Wagner | +5.12 | 1.14 | +2.74 | +2.38 | 8,066 |
| top | Keon Ellis | +4.84 | 1.15 | +3.64 | +1.20 | 7,802 |
| top | Victor Wembanyama | +4.30 | 1.37 | +0.63 | +3.67 | 6,265 |
| top | Chet Holmgren | +4.22 | 1.20 | +1.14 | +3.08 | 3,686 |
| top | Pascal Siakam | +4.09 | 0.92 | +0.57 | +3.52 | 10,521 |
| bottom | Nick Smith Jr. | -5.83 | 1.36 | -3.48 | -2.34 | 5,322 |
| bottom | Amir Coffey | -4.85 | 1.54 | -1.96 | -2.89 | 6,702 |
| bottom | Alex Len | -4.43 | 1.41 | -2.51 | -1.92 | 1,321 |
| bottom | Jordan Hawkins | -4.32 | 1.29 | -1.40 | -2.91 | 5,275 |
| bottom | Taj Gibson | -4.00 | 1.04 | -2.61 | -1.39 | 1,552 |
| bottom | Tidjane Salaün | -3.96 | 1.55 | -3.16 | -0.80 | 4,740 |
| bottom | Gradey Dick | -3.85 | 1.07 | -0.66 | -3.19 | 6,527 |
| bottom | DaQuan Jeffries | -3.77 | 1.40 | -1.59 | -2.18 | 4,084 |
| bottom | Keon Johnson | -3.72 | 1.44 | -2.97 | -0.75 | 7,560 |
| bottom | Jamal Cain | -3.70 | 1.30 | -1.06 | -2.63 | 1,735 |

Reading: ridge shrinks every player toward the average, so the spread is smaller than raw on/off. Differences between players that are smaller than their standard errors are noise.
