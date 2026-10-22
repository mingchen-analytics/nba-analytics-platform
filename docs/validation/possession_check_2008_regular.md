# Possession checks: 2007-08 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2460 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1230 | 4 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2460 | 20 |

Check 8: 99.19% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 18, '0': 2440, '1': 2}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0020700018` | TOR | 85 | 86 | -1 |
| `0020700034` | GSW | 99 | 100 | -1 |
| `0020700053` | GSW | 103 | 102 | +1 |
| `0020700378` | MIA | 95 | 94 | +1 |
| `0020700402` | CLE | 94 | 95 | -1 |
| `0020700528` | NOH | 85 | 86 | -1 |
| `0020700572` | LAL | 101 | 102 | -1 |
| `0020700622` | MIA | 86 | 87 | -1 |
| `0020700705` | DEN | 100 | 101 | -1 |
| `0020700707` | PHI | 91 | 92 | -1 |
| `0020700707` | WAS | 91 | 92 | -1 |
| `0020700708` | BOS | 89 | 90 | -1 |
| `0020700794` | DET | 91 | 92 | -1 |
| `0020700796` | LAL | 99 | 100 | -1 |
| `0020700796` | PHX | 101 | 102 | -1 |
| `0020700925` | WAS | 90 | 91 | -1 |
| `0020701084` | NJN | 96 | 97 | -1 |
| `0020701084` | PHX | 96 | 97 | -1 |
| `0020701215` | POR | 87 | 88 | -1 |
| `0020701216` | LAL | 100 | 101 | -1 |
