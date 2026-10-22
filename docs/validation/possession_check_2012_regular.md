# Possession checks: 2011-12 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 1980 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 990 | 4 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 1980 | 19 |

Check 8: 99.04% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 12, '0': 1961, '1': 7}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0021100100` | NYK | 100 | 99 | +1 |
| `0021100100` | WAS | 100 | 99 | +1 |
| `0021100148` | OKC | 86 | 87 | -1 |
| `0021100199` | DEN | 100 | 99 | +1 |
| `0021100234` | DAL | 90 | 91 | -1 |
| `0021100266` | UTA | 110 | 109 | +1 |
| `0021100338` | HOU | 94 | 95 | -1 |
| `0021100395` | NYK | 95 | 94 | +1 |
| `0021100409` | CHI | 93 | 94 | -1 |
| `0021100436` | OKC | 94 | 95 | -1 |
| `0021100502` | OKC | 90 | 91 | -1 |
| `0021100528` | TOR | 90 | 91 | -1 |
| `0021100560` | LAC | 87 | 88 | -1 |
| `0021100663` | LAC | 93 | 92 | +1 |
| `0021100671` | NJN | 89 | 90 | -1 |
| `0021100715` | NOH | 86 | 87 | -1 |
| `0021100791` | CHA | 82 | 83 | -1 |
| `0021100882` | HOU | 99 | 98 | +1 |
| `0021100973` | CHI | 86 | 87 | -1 |
