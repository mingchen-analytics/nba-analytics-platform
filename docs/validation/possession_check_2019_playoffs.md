# Possession checks: 2018-19 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 164 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | pass | 82 | 0 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 164 | 40 |

Check 8: 75.61% of team-games identical to pbpstats, 97.56% within 1. Distribution of (ours - pbpstats): {'0': 124, '1': 36, '2': 4}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0041800101` | MIL | 103 | 101 | +2 |
| `0041800102` | MIL | 100 | 99 | +1 |
| `0041800112` | TOR | 93 | 92 | +1 |
| `0041800115` | TOR | 100 | 99 | +1 |
| `0041800121` | PHI | 98 | 97 | +1 |
| `0041800123` | BKN | 108 | 107 | +1 |
| `0041800123` | PHI | 107 | 106 | +1 |
| `0041800132` | IND | 94 | 93 | +1 |
| `0041800133` | BOS | 94 | 93 | +1 |
| `0041800134` | IND | 99 | 98 | +1 |
| `0041800141` | GSW | 109 | 108 | +1 |
| `0041800144` | GSW | 98 | 97 | +1 |
| `0041800146` | LAC | 104 | 103 | +1 |
| `0041800154` | DEN | 95 | 94 | +1 |
| `0041800155` | DEN | 92 | 91 | +1 |
| `0041800163` | OKC | 98 | 97 | +1 |
| `0041800164` | OKC | 103 | 102 | +1 |
| `0041800165` | OKC | 99 | 98 | +1 |
| `0041800171` | HOU | 98 | 97 | +1 |
| `0041800172` | UTA | 100 | 99 | +1 |
| `0041800201` | BOS | 100 | 98 | +2 |
| `0041800201` | MIL | 100 | 99 | +1 |
| `0041800202` | BOS | 103 | 102 | +1 |
| `0041800214` | TOR | 92 | 91 | +1 |
| `0041800215` | TOR | 98 | 97 | +1 |
| `0041800221` | GSW | 98 | 97 | +1 |
| `0041800222` | GSW | 95 | 94 | +1 |
| `0041800224` | HOU | 97 | 96 | +1 |
| `0041800226` | GSW | 97 | 96 | +1 |
| `0041800231` | DEN | 99 | 97 | +2 |
| `0041800231` | POR | 99 | 98 | +1 |
| `0041800233` | POR | 124 | 123 | +1 |
| `0041800234` | POR | 94 | 92 | +2 |
| `0041800235` | DEN | 98 | 97 | +1 |
| `0041800235` | POR | 98 | 97 | +1 |
| `0041800237` | POR | 94 | 93 | +1 |
| `0041800303` | MIL | 119 | 118 | +1 |
| `0041800306` | TOR | 87 | 86 | +1 |
| `0041800314` | GSW | 106 | 105 | +1 |
| `0041800403` | GSW | 98 | 97 | +1 |
