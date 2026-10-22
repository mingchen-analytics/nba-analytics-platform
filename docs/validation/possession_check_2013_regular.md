# Possession checks: 2012-13 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2458 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1229 | 6 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2458 | 18 |

Check 8: 99.27% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 16, '0': 2440, '1': 2}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0021200089` | DEN | 109 | 110 | -1 |
| `0021200178` | HOU | 99 | 100 | -1 |
| `0021200215` | MIL | 90 | 91 | -1 |
| `0021200250` | ORL | 90 | 91 | -1 |
| `0021200299` | GSW | 95 | 96 | -1 |
| `0021200327` | PHI | 90 | 91 | -1 |
| `0021200359` | MIA | 87 | 88 | -1 |
| `0021200558` | ATL | 90 | 89 | +1 |
| `0021200629` | ORL | 88 | 89 | -1 |
| `0021200631` | LAC | 93 | 94 | -1 |
| `0021200647` | GSW | 97 | 98 | -1 |
| `0021200706` | DET | 98 | 99 | -1 |
| `0021200849` | MIN | 99 | 100 | -1 |
| `0021201012` | OKC | 95 | 96 | -1 |
| `0021201020` | DEN | 95 | 96 | -1 |
| `0021201047` | PHI | 93 | 92 | +1 |
| `0021201053` | GSW | 98 | 99 | -1 |
| `0021201206` | PHI | 93 | 94 | -1 |
