# Possession checks: 2004-05 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2460 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1230 | 4 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2460 | 36 |

Check 8: 98.54% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 28, '0': 2424, '1': 8}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0020400065` | LAL | 90 | 91 | -1 |
| `0020400127` | POR | 91 | 92 | -1 |
| `0020400140` | DET | 108 | 107 | +1 |
| `0020400197` | SEA | 80 | 81 | -1 |
| `0020400233` | NYK | 93 | 94 | -1 |
| `0020400264` | DEN | 92 | 93 | -1 |
| `0020400278` | NJN | 92 | 93 | -1 |
| `0020400319` | CLE | 95 | 96 | -1 |
| `0020400377` | LAL | 94 | 93 | +1 |
| `0020400458` | MIA | 89 | 88 | +1 |
| `0020400458` | NYK | 90 | 89 | +1 |
| `0020400468` | MIL | 99 | 100 | -1 |
| `0020400610` | NJN | 93 | 94 | -1 |
| `0020400648` | MIA | 87 | 88 | -1 |
| `0020400705` | ATL | 100 | 99 | +1 |
| `0020400721` | IND | 85 | 86 | -1 |
| `0020400726` | NOH | 83 | 84 | -1 |
| `0020400742` | PHI | 107 | 108 | -1 |
| `0020400763` | DEN | 88 | 89 | -1 |
| `0020400855` | GSW | 94 | 95 | -1 |
| `0020400855` | WAS | 94 | 95 | -1 |
| `0020400872` | HOU | 92 | 93 | -1 |
| `0020400906` | MIN | 94 | 95 | -1 |
| `0020400927` | DET | 79 | 80 | -1 |
| `0020401057` | SAC | 87 | 88 | -1 |
| `0020401067` | CHA | 94 | 95 | -1 |
| `0020401070` | NYK | 90 | 91 | -1 |
| `0020401075` | GSW | 93 | 94 | -1 |
| `0020401076` | PHX | 98 | 99 | -1 |
| `0020401089` | TOR | 89 | 90 | -1 |
| `0020401140` | MIA | 84 | 83 | +1 |
| `0020401142` | LAL | 95 | 96 | -1 |
| `0020401160` | CHI | 104 | 103 | +1 |
| `0020401160` | WAS | 104 | 103 | +1 |
| `0020401193` | IND | 82 | 83 | -1 |
| `0020401193` | MIA | 82 | 83 | -1 |
