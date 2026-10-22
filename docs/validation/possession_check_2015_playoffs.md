# Possession checks: 2014-15 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 162 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | pass | 81 | 0 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | pass | 162 | 0 |

Check 8: 100.00% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'0': 162}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
