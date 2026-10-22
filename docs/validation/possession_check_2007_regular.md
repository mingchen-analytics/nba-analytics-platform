# Possession checks: 2006-07 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2460 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1230 | 5 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2460 | 29 |

Check 8: 98.82% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 28, '0': 2431, '1': 1}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0020600004` | CHA | 102 | 103 | -1 |
| `0020600037` | GSW | 91 | 92 | -1 |
| `0020600083` | BOS | 93 | 94 | -1 |
| `0020600103` | MIN | 95 | 96 | -1 |
| `0020600115` | SAC | 94 | 95 | -1 |
| `0020600170` | GSW | 102 | 103 | -1 |
| `0020600180` | DEN | 110 | 111 | -1 |
| `0020600216` | TOR | 91 | 92 | -1 |
| `0020600240` | DEN | 102 | 103 | -1 |
| `0020600283` | DEN | 95 | 96 | -1 |
| `0020600321` | POR | 82 | 83 | -1 |
| `0020600496` | POR | 100 | 101 | -1 |
| `0020600597` | NJN | 90 | 91 | -1 |
| `0020600601` | GSW | 112 | 113 | -1 |
| `0020600661` | ATL | 87 | 88 | -1 |
| `0020600674` | TOR | 95 | 96 | -1 |
| `0020600713` | WAS | 93 | 94 | -1 |
| `0020600751` | MEM | 93 | 94 | -1 |
| `0020600763` | GSW | 98 | 99 | -1 |
| `0020600839` | IND | 101 | 102 | -1 |
| `0020600872` | DET | 85 | 86 | -1 |
| `0020600872` | MIA | 86 | 87 | -1 |
| `0020600923` | HOU | 95 | 96 | -1 |
| `0020600923` | NJN | 95 | 96 | -1 |
| `0020601047` | MIA | 85 | 86 | -1 |
| `0020601048` | DET | 99 | 100 | -1 |
| `0020601073` | TOR | 109 | 110 | -1 |
| `0020601085` | PHI | 83 | 84 | -1 |
| `0020601139` | NYK | 107 | 106 | +1 |
