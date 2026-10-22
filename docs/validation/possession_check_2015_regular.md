# Possession checks: 2014-15 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2460 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1230 | 6 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2460 | 31 |

Check 8: 98.74% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 19, '0': 2429, '1': 12}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0021400017` | DET | 90 | 89 | +1 |
| `0021400031` | MIL | 98 | 99 | -1 |
| `0021400071` | CHA | 111 | 112 | -1 |
| `0021400078` | MEM | 88 | 87 | +1 |
| `0021400078` | OKC | 87 | 86 | +1 |
| `0021400118` | MEM | 91 | 92 | -1 |
| `0021400154` | CHI | 86 | 87 | -1 |
| `0021400188` | DAL | 94 | 93 | +1 |
| `0021400188` | HOU | 92 | 93 | -1 |
| `0021400244` | MEM | 91 | 90 | +1 |
| `0021400244` | SAC | 92 | 91 | +1 |
| `0021400345` | MEM | 104 | 105 | -1 |
| `0021400453` | CLE | 89 | 90 | -1 |
| `0021400454` | HOU | 99 | 100 | -1 |
| `0021400457` | DEN | 94 | 93 | +1 |
| `0021400457` | TOR | 92 | 91 | +1 |
| `0021400522` | CHA | 94 | 95 | -1 |
| `0021400729` | UTA | 90 | 91 | -1 |
| `0021400779` | MIN | 93 | 94 | -1 |
| `0021400808` | PHX | 98 | 99 | -1 |
| `0021400870` | DET | 91 | 92 | -1 |
| `0021400909` | CHI | 94 | 95 | -1 |
| `0021400920` | WAS | 94 | 93 | +1 |
| `0021400969` | ORL | 98 | 99 | -1 |
| `0021400972` | DAL | 90 | 91 | -1 |
| `0021400999` | LAL | 101 | 100 | +1 |
| `0021401010` | MIL | 91 | 92 | -1 |
| `0021401010` | SAS | 92 | 91 | +1 |
| `0021401047` | PHI | 91 | 90 | +1 |
| `0021401161` | CHI | 93 | 94 | -1 |
| `0021401161` | ORL | 93 | 94 | -1 |
