# Possession checks: 2017-18 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 164 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 82 | 1 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 164 | 32 |

Check 8: 80.49% of team-games identical to pbpstats, 98.78% within 1. Distribution of (ours - pbpstats): {'-1': 1, '0': 132, '1': 29, '2': 2}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0041700102` | TOR | 102 | 100 | +2 |
| `0041700102` | WAS | 103 | 104 | -1 |
| `0041700104` | TOR | 100 | 99 | +1 |
| `0041700123` | MIA | 97 | 96 | +1 |
| `0041700131` | IND | 94 | 93 | +1 |
| `0041700136` | CLE | 90 | 89 | +1 |
| `0041700141` | HOU | 94 | 93 | +1 |
| `0041700143` | HOU | 95 | 94 | +1 |
| `0041700145` | HOU | 91 | 90 | +1 |
| `0041700152` | GSW | 95 | 94 | +1 |
| `0041700155` | SAS | 95 | 94 | +1 |
| `0041700161` | POR | 98 | 97 | +1 |
| `0041700163` | POR | 103 | 102 | +1 |
| `0041700164` | NOP | 100 | 98 | +2 |
| `0041700164` | POR | 101 | 100 | +1 |
| `0041700173` | UTA | 97 | 96 | +1 |
| `0041700174` | OKC | 101 | 100 | +1 |
| `0041700174` | UTA | 100 | 99 | +1 |
| `0041700176` | UTA | 89 | 88 | +1 |
| `0041700203` | TOR | 90 | 89 | +1 |
| `0041700204` | TOR | 93 | 92 | +1 |
| `0041700211` | BOS | 95 | 94 | +1 |
| `0041700212` | PHI | 94 | 93 | +1 |
| `0041700215` | BOS | 101 | 100 | +1 |
| `0041700221` | HOU | 95 | 94 | +1 |
| `0041700233` | GSW | 104 | 103 | +1 |
| `0041700234` | GSW | 108 | 107 | +1 |
| `0041700235` | NOP | 106 | 105 | +1 |
| `0041700305` | BOS | 94 | 93 | +1 |
| `0041700306` | BOS | 91 | 90 | +1 |
| `0041700315` | HOU | 96 | 95 | +1 |
| `0041700402` | CLE | 93 | 92 | +1 |
