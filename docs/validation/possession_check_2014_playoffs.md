# Possession checks: 2013-14 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 178 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | pass | 89 | 0 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 178 | 3 |

Check 8: 98.31% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 3, '0': 175}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0041300166` | LAC | 92 | 93 | -1 |
| `0041300301` | IND | 88 | 89 | -1 |
| `0041300305` | IND | 83 | 84 | -1 |
