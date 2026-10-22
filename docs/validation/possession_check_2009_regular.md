# Possession checks: 2008-09 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2460 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1230 | 8 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2460 | 17 |

Check 8: 99.31% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 16, '0': 2443, '1': 1}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0020800023` | MEM | 89 | 90 | -1 |
| `0020800051` | IND | 97 | 98 | -1 |
| `0020800165` | LAC | 97 | 96 | +1 |
| `0020800274` | DAL | 93 | 94 | -1 |
| `0020800307` | UTA | 92 | 93 | -1 |
| `0020800346` | HOU | 87 | 88 | -1 |
| `0020800433` | UTA | 87 | 88 | -1 |
| `0020800512` | LAC | 91 | 92 | -1 |
| `0020800563` | DEN | 95 | 96 | -1 |
| `0020800574` | SAS | 87 | 88 | -1 |
| `0020800707` | MEM | 89 | 90 | -1 |
| `0020800757` | OKC | 93 | 94 | -1 |
| `0020800757` | SAC | 94 | 95 | -1 |
| `0020800875` | CHA | 96 | 97 | -1 |
| `0020801042` | SAS | 86 | 87 | -1 |
| `0020801072` | POR | 94 | 95 | -1 |
| `0020801155` | NOH | 89 | 90 | -1 |
