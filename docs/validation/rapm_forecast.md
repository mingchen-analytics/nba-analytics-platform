# RAPM out of sample: predicting the next season's team net rating

For each team-season, the sum over its players of (share of the team's offensive possessions he was on the floor) x (his RAPM from the window that ends the season **before**) is compared with the team's net rating of the season (without end-of-period heaves and garbage time). A player without a rating counts 0. Numbers only.

Team-seasons in the common sample: **803** (every method has a prediction for each of them). `RMSE` is after the best linear rescaling of the prediction; the baseline predicts a team's net rating by last season's net rating.

| method | window | correlation | RMSE | slope |
|---|---|---|---|---|
| RAPM raw | one season | 0.690 | 3.70 | 0.93 |
| RAPM raw | three seasons | 0.724 | 3.53 | 0.86 |
| RAPM luck_adjusted | one season | 0.687 | 3.72 | 1.07 |
| RAPM luck_adjusted | three seasons | 0.721 | 3.55 | 0.97 |
| last season's net rating | - | 0.607 | 4.07 | 0.61 |

Reading: a higher correlation and a lower RMSE are better. A prediction that uses the players' ratings knows the roster of the season it predicts (a roster known in advance, which is the usual forecasting set-up) but not its results.
