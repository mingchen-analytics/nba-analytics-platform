# Possession checks: 2000-01 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 142 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | pass | 71 | 0 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 142 | 1 |

Check 8: 99.30% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'0': 141, '1': 1}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0040000023` | PHX | 103 | 102 | +1 |
