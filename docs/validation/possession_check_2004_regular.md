# Possession checks: 2003-04 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2378 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1189 | 5 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2378 | 33 |

Check 8: 98.61% of team-games identical to pbpstats, 99.92% within 1. Distribution of (ours - pbpstats): {'-2': 2, '-1': 25, '0': 2345, '1': 6}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0020300025` | LAC | 97 | 98 | -1 |
| `0020300088` | DET | 92 | 91 | +1 |
| `0020300165` | NOH | 80 | 81 | -1 |
| `0020300171` | SAC | 97 | 96 | +1 |
| `0020300193` | NOH | 87 | 88 | -1 |
| `0020300234` | LAL | 93 | 94 | -1 |
| `0020300345` | PHX | 102 | 101 | +1 |
| `0020300345` | SEA | 101 | 102 | -1 |
| `0020300398` | DAL | 85 | 86 | -1 |
| `0020300440` | CLE | 85 | 86 | -1 |
| `0020300463` | PHI | 91 | 92 | -1 |
| `0020300463` | SAS | 90 | 92 | -2 |
| `0020300529` | DAL | 103 | 104 | -1 |
| `0020300547` | DET | 85 | 86 | -1 |
| `0020300570` | ORL | 83 | 84 | -1 |
| `0020300577` | POR | 95 | 96 | -1 |
| `0020300613` | HOU | 83 | 84 | -1 |
| `0020300691` | CHI | 85 | 86 | -1 |
| `0020300691` | SEA | 85 | 86 | -1 |
| `0020300733` | NJN | 90 | 91 | -1 |
| `0020300733` | PHI | 88 | 89 | -1 |
| `0020300753` | DET | 86 | 85 | +1 |
| `0020300790` | DET | 87 | 88 | -1 |
| `0020300884` | PHI | 96 | 95 | +1 |
| `0020300884` | SAC | 95 | 96 | -1 |
| `0020300894` | LAL | 89 | 90 | -1 |
| `0020300894` | SEA | 90 | 91 | -1 |
| `0020300959` | MIN | 78 | 79 | -1 |
| `0020300959` | POR | 78 | 79 | -1 |
| `0020300972` | MIL | 88 | 89 | -1 |
| `0020301028` | DAL | 92 | 94 | -2 |
| `0020301040` | TOR | 93 | 94 | -1 |
| `0020301099` | SAS | 83 | 82 | +1 |
