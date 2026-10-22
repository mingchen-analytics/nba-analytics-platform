# Possession checks: 2010-11 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 162 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 81 | 1 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 162 | 8 |

Check 8: 95.06% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 5, '0': 154, '1': 3}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0041000101` | IND | 88 | 89 | -1 |
| `0041000105` | CHI | 92 | 93 | -1 |
| `0041000132` | ATL | 86 | 87 | -1 |
| `0041000206` | ATL | 85 | 84 | +1 |
| `0041000214` | MIA | 96 | 97 | -1 |
| `0041000231` | LAL | 89 | 90 | -1 |
| `0041000313` | DAL | 91 | 90 | +1 |
| `0041000313` | OKC | 91 | 90 | +1 |
