# Possession checks: 2010-11 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2460 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1230 | 4 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2460 | 25 |

Check 8: 98.98% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 15, '0': 2435, '1': 10}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0021000005` | DET | 88 | 89 | -1 |
| `0021000014` | DEN | 99 | 100 | -1 |
| `0021000036` | MIN | 107 | 108 | -1 |
| `0021000061` | UTA | 98 | 99 | -1 |
| `0021000186` | MIL | 89 | 90 | -1 |
| `0021000252` | HOU | 94 | 93 | +1 |
| `0021000289` | CHA | 84 | 85 | -1 |
| `0021000308` | SAC | 94 | 93 | +1 |
| `0021000323` | PHX | 96 | 95 | +1 |
| `0021000402` | TOR | 98 | 99 | -1 |
| `0021000461` | DEN | 86 | 87 | -1 |
| `0021000475` | POR | 89 | 90 | -1 |
| `0021000557` | SAS | 99 | 98 | +1 |
| `0021000678` | MIA | 95 | 94 | +1 |
| `0021000678` | NYK | 95 | 94 | +1 |
| `0021000737` | WAS | 95 | 96 | -1 |
| `0021000740` | DAL | 85 | 86 | -1 |
| `0021000791` | LAC | 100 | 101 | -1 |
| `0021000808` | TOR | 91 | 92 | -1 |
| `0021000849` | SAC | 100 | 101 | -1 |
| `0021000883` | ORL | 90 | 89 | +1 |
| `0021000903` | CLE | 93 | 92 | +1 |
| `0021001065` | WAS | 113 | 112 | +1 |
| `0021001078` | POR | 90 | 91 | -1 |
| `0021001110` | MIA | 93 | 92 | +1 |
