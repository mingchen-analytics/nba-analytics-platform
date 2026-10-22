# Possession checks: 2006-07 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 158 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | pass | 79 | 0 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 158 | 2 |

Check 8: 98.73% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 2, '0': 156}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0040600103` | DET | 84 | 85 | -1 |
| `0040600171` | HOU | 88 | 89 | -1 |
