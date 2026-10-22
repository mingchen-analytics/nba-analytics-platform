# Possession checks: 2019-20 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 166 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | pass | 83 | 0 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 166 | 44 |

Check 8: 73.49% of team-games identical to pbpstats, 98.19% within 1. Distribution of (ours - pbpstats): {'-1': 3, '0': 122, '1': 38, '2': 3}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0041900101` | MIL | 106 | 105 | +1 |
| `0041900111` | TOR | 101 | 100 | +1 |
| `0041900121` | BOS | 91 | 90 | +1 |
| `0041900124` | BOS | 95 | 93 | +2 |
| `0041900133` | IND | 104 | 103 | +1 |
| `0041900142` | POR | 96 | 95 | +1 |
| `0041900143` | POR | 103 | 102 | +1 |
| `0041900144` | LAL | 99 | 97 | +2 |
| `0041900162` | DEN | 89 | 88 | +1 |
| `0041900166` | DEN | 93 | 92 | +1 |
| `0041900166` | UTA | 93 | 92 | +1 |
| `0041900167` | DEN | 89 | 88 | +1 |
| `0041900173` | HOU | 114 | 113 | +1 |
| `0041900174` | HOU | 100 | 99 | +1 |
| `0041900176` | HOU | 104 | 103 | +1 |
| `0041900177` | HOU | 97 | 98 | -1 |
| `0041900201` | MIL | 99 | 98 | +1 |
| `0041900202` | MIA | 96 | 95 | +1 |
| `0041900204` | MIL | 101 | 100 | +1 |
| `0041900205` | MIA | 98 | 97 | +1 |
| `0041900211` | TOR | 105 | 104 | +1 |
| `0041900216` | BOS | 110 | 109 | +1 |
| `0041900216` | TOR | 109 | 108 | +1 |
| `0041900223` | HOU | 91 | 90 | +1 |
| `0041900225` | LAL | 100 | 99 | +1 |
| `0041900231` | DEN | 98 | 97 | +1 |
| `0041900232` | DEN | 95 | 94 | +1 |
| `0041900233` | DEN | 101 | 100 | +1 |
| `0041900233` | LAC | 100 | 99 | +1 |
| `0041900234` | DEN | 93 | 92 | +1 |
| `0041900235` | DEN | 94 | 93 | +1 |
| `0041900236` | LAC | 95 | 94 | +1 |
| `0041900237` | LAC | 93 | 92 | +1 |
| `0041900301` | MIA | 99 | 98 | +1 |
| `0041900303` | BOS | 100 | 99 | +1 |
| `0041900303` | MIA | 98 | 96 | +2 |
| `0041900311` | LAL | 99 | 98 | +1 |
| `0041900314` | DEN | 90 | 89 | +1 |
| `0041900315` | DEN | 98 | 97 | +1 |
| `0041900315` | LAL | 98 | 99 | -1 |
| `0041900401` | MIA | 97 | 96 | +1 |
| `0041900403` | LAL | 99 | 98 | +1 |
| `0041900405` | LAL | 93 | 92 | +1 |
| `0041900405` | MIA | 92 | 93 | -1 |
