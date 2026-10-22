# Possession checks: 2004-05 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 168 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | pass | 84 | 0 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 168 | 1 |

Check 8: 99.40% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 1, '0': 167}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0040400164` | SAC | 93 | 94 | -1 |
