# Possession checks: 2002-03 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2378 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1189 | 9 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2378 | 41 |

Check 8: 98.28% of team-games identical to pbpstats, 99.92% within 1. Distribution of (ours - pbpstats): {'-1': 30, '0': 2337, '1': 9, '2': 2}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0020200046` | TOR | 106 | 107 | -1 |
| `0020200104` | NOH | 88 | 89 | -1 |
| `0020200180` | ATL | 99 | 98 | +1 |
| `0020200180` | BOS | 98 | 97 | +1 |
| `0020200200` | ATL | 104 | 103 | +1 |
| `0020200200` | SEA | 104 | 103 | +1 |
| `0020200235` | DET | 88 | 86 | +2 |
| `0020200235` | MIL | 89 | 87 | +2 |
| `0020200286` | DEN | 89 | 88 | +1 |
| `0020200291` | SAC | 92 | 91 | +1 |
| `0020200295` | PHX | 97 | 98 | -1 |
| `0020200333` | MIL | 94 | 95 | -1 |
| `0020200378` | SEA | 92 | 93 | -1 |
| `0020200401` | PHX | 82 | 83 | -1 |
| `0020200401` | SEA | 82 | 83 | -1 |
| `0020200417` | UTA | 92 | 93 | -1 |
| `0020200434` | CLE | 92 | 93 | -1 |
| `0020200439` | DEN | 90 | 91 | -1 |
| `0020200475` | SAC | 93 | 94 | -1 |
| `0020200477` | BOS | 93 | 94 | -1 |
| `0020200509` | MIN | 106 | 107 | -1 |
| `0020200517` | SEA | 94 | 95 | -1 |
| `0020200536` | GSW | 98 | 99 | -1 |
| `0020200536` | MEM | 96 | 97 | -1 |
| `0020200545` | IND | 84 | 85 | -1 |
| `0020200556` | IND | 90 | 91 | -1 |
| `0020200648` | NOH | 95 | 96 | -1 |
| `0020200649` | DAL | 91 | 90 | +1 |
| `0020200655` | SEA | 91 | 90 | +1 |
| `0020200742` | SAC | 89 | 90 | -1 |
| `0020200744` | CHI | 89 | 90 | -1 |
| `0020200752` | SAC | 93 | 94 | -1 |
| `0020200752` | SAS | 94 | 93 | +1 |
| `0020200772` | NOH | 84 | 85 | -1 |
| `0020200849` | DET | 82 | 83 | -1 |
| `0020200864` | MIA | 94 | 95 | -1 |
| `0020200914` | IND | 84 | 85 | -1 |
| `0020200918` | TOR | 99 | 100 | -1 |
| `0020201029` | NOH | 88 | 89 | -1 |
| `0020201128` | CHI | 99 | 100 | -1 |
| `0020201154` | GSW | 102 | 103 | -1 |
