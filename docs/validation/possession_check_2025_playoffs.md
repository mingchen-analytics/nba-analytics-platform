# Possession checks: 2024-25 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 166 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | pass | 83 | 0 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 166 | 32 |

Check 8: 80.72% of team-games identical to pbpstats, 97.59% within 1. Distribution of (ours - pbpstats): {'-1': 1, '0': 134, '1': 27, '2': 3, '4': 1}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0042400112` | BOS | 88 | 86 | +2 |
| `0042400122` | DET | 95 | 93 | +2 |
| `0042400124` | NYK | 94 | 93 | +1 |
| `0042400125` | NYK | 97 | 96 | +1 |
| `0042400126` | NYK | 102 | 101 | +1 |
| `0042400151` | GSW | 89 | 88 | +1 |
| `0042400152` | GSW | 94 | 90 | +4 |
| `0042400155` | GSW | 98 | 97 | +1 |
| `0042400162` | MIN | 88 | 87 | +1 |
| `0042400165` | LAL | 94 | 93 | +1 |
| `0042400171` | LAC | 100 | 99 | +1 |
| `0042400172` | DEN | 93 | 92 | +1 |
| `0042400173` | LAC | 89 | 88 | +1 |
| `0042400174` | DEN | 89 | 90 | -1 |
| `0042400175` | DEN | 95 | 94 | +1 |
| `0042400176` | DEN | 89 | 88 | +1 |
| `0042400176` | LAC | 88 | 87 | +1 |
| `0042400202` | CLE | 101 | 100 | +1 |
| `0042400203` | IND | 103 | 102 | +1 |
| `0042400205` | IND | 100 | 99 | +1 |
| `0042400212` | BOS | 94 | 93 | +1 |
| `0042400223` | OKC | 105 | 104 | +1 |
| `0042400225` | DEN | 98 | 96 | +2 |
| `0042400302` | NYK | 90 | 89 | +1 |
| `0042400303` | IND | 95 | 94 | +1 |
| `0042400303` | NYK | 95 | 94 | +1 |
| `0042400305` | NYK | 96 | 95 | +1 |
| `0042400313` | MIN | 101 | 100 | +1 |
| `0042400314` | MIN | 96 | 95 | +1 |
| `0042400315` | OKC | 104 | 103 | +1 |
| `0042400403` | OKC | 100 | 99 | +1 |
| `0042400406` | OKC | 101 | 100 | +1 |
