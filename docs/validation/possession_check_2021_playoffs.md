# Possession checks: 2020-21 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 170 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 85 | 3 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 170 | 50 |

Check 8: 70.59% of team-games identical to pbpstats, 97.65% within 1. Distribution of (ours - pbpstats): {'-1': 6, '0': 120, '1': 40, '2': 4}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0042000102` | PHI | 98 | 97 | +1 |
| `0042000102` | WAS | 98 | 97 | +1 |
| `0042000104` | PHI | 107 | 108 | -1 |
| `0042000104` | WAS | 110 | 108 | +2 |
| `0042000105` | WAS | 102 | 101 | +1 |
| `0042000112` | BKN | 101 | 100 | +1 |
| `0042000115` | BKN | 96 | 95 | +1 |
| `0042000115` | BOS | 95 | 94 | +1 |
| `0042000122` | MIA | 95 | 96 | -1 |
| `0042000122` | MIL | 95 | 94 | +1 |
| `0042000123` | MIL | 99 | 98 | +1 |
| `0042000133` | NYK | 91 | 92 | -1 |
| `0042000135` | NYK | 93 | 92 | +1 |
| `0042000141` | MEM | 98 | 97 | +1 |
| `0042000141` | UTA | 99 | 98 | +1 |
| `0042000142` | MEM | 102 | 101 | +1 |
| `0042000144` | UTA | 100 | 99 | +1 |
| `0042000145` | MEM | 104 | 103 | +1 |
| `0042000145` | UTA | 103 | 101 | +2 |
| `0042000152` | LAL | 92 | 91 | +1 |
| `0042000152` | PHX | 90 | 89 | +1 |
| `0042000155` | PHX | 99 | 98 | +1 |
| `0042000156` | LAL | 89 | 88 | +1 |
| `0042000156` | PHX | 88 | 87 | +1 |
| `0042000162` | DEN | 95 | 94 | +1 |
| `0042000163` | DEN | 96 | 95 | +1 |
| `0042000164` | POR | 93 | 92 | +1 |
| `0042000166` | DEN | 96 | 95 | +1 |
| `0042000166` | POR | 96 | 95 | +1 |
| `0042000171` | LAC | 88 | 87 | +1 |
| `0042000175` | DAL | 92 | 93 | -1 |
| `0042000177` | DAL | 94 | 93 | +1 |
| `0042000203` | ATL | 97 | 96 | +1 |
| `0042000204` | ATL | 99 | 98 | +1 |
| `0042000205` | ATL | 98 | 97 | +1 |
| `0042000211` | MIL | 105 | 104 | +1 |
| `0042000212` | BKN | 95 | 94 | +1 |
| `0042000216` | BKN | 94 | 93 | +1 |
| `0042000217` | BKN | 93 | 92 | +1 |
| `0042000221` | UTA | 93 | 92 | +1 |
| `0042000223` | UTA | 95 | 94 | +1 |
| `0042000226` | UTA | 93 | 91 | +2 |
| `0042000231` | DEN | 94 | 93 | +1 |
| `0042000233` | DEN | 97 | 95 | +2 |
| `0042000234` | DEN | 105 | 104 | +1 |
| `0042000314` | PHX | 92 | 91 | +1 |
| `0042000316` | LAC | 91 | 92 | -1 |
| `0042000401` | PHX | 100 | 101 | -1 |
| `0042000403` | MIL | 97 | 96 | +1 |
| `0042000405` | MIL | 92 | 91 | +1 |
