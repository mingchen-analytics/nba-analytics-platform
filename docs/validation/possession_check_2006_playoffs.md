# Possession checks: 2005-06 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 178 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 89 | 1 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 178 | 5 |

Check 8: 97.19% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 5, '0': 173}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0040500105` | MIL | 92 | 93 | -1 |
| `0040500112` | MIA | 96 | 97 | -1 |
| `0040500132` | CLE | 90 | 91 | -1 |
| `0040500223` | SAS | 88 | 89 | -1 |
| `0040500311` | PHX | 97 | 98 | -1 |
