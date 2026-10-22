# Possession checks: 2016-17 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 158 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | pass | 79 | 0 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 158 | 32 |

Check 8: 79.75% of team-games identical to pbpstats, 99.37% within 1. Distribution of (ours - pbpstats): {'-1': 1, '0': 126, '1': 30, '2': 1}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0041600111` | IND | 90 | 89 | +1 |
| `0041600113` | IND | 94 | 93 | +1 |
| `0041600123` | MIL | 90 | 89 | +1 |
| `0041600123` | TOR | 90 | 89 | +1 |
| `0041600124` | MIL | 97 | 95 | +2 |
| `0041600125` | TOR | 92 | 91 | +1 |
| `0041600131` | ATL | 99 | 98 | +1 |
| `0041600131` | WAS | 97 | 98 | -1 |
| `0041600141` | POR | 100 | 99 | +1 |
| `0041600142` | POR | 102 | 101 | +1 |
| `0041600143` | GSW | 102 | 101 | +1 |
| `0041600144` | GSW | 100 | 99 | +1 |
| `0041600144` | POR | 101 | 100 | +1 |
| `0041600171` | UTA | 90 | 89 | +1 |
| `0041600172` | UTA | 90 | 89 | +1 |
| `0041600173` | UTA | 89 | 88 | +1 |
| `0041600201` | WAS | 93 | 92 | +1 |
| `0041600206` | WAS | 92 | 91 | +1 |
| `0041600221` | GSW | 92 | 91 | +1 |
| `0041600222` | GSW | 102 | 101 | +1 |
| `0041600223` | GSW | 93 | 92 | +1 |
| `0041600223` | UTA | 94 | 93 | +1 |
| `0041600224` | GSW | 99 | 98 | +1 |
| `0041600232` | SAS | 88 | 87 | +1 |
| `0041600233` | SAS | 96 | 95 | +1 |
| `0041600236` | HOU | 94 | 93 | +1 |
| `0041600301` | BOS | 92 | 91 | +1 |
| `0041600312` | SAS | 102 | 101 | +1 |
| `0041600313` | SAS | 105 | 104 | +1 |
| `0041600314` | GSW | 109 | 108 | +1 |
| `0041600404` | CLE | 96 | 95 | +1 |
| `0041600405` | CLE | 100 | 99 | +1 |
