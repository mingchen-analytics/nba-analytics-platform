# Possession checks: 2007-08 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 172 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | pass | 86 | 0 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 172 | 3 |

Check 8: 98.26% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 2, '0': 169, '1': 1}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0040700131` | WAS | 91 | 92 | -1 |
| `0040700143` | LAL | 98 | 97 | +1 |
| `0040700233` | SAS | 88 | 89 | -1 |
