# Possession checks: 2015-16 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2460 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1230 | 5 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2460 | 35 |

Check 8: 98.58% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 25, '0': 2425, '1': 10}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0021500098` | DET | 97 | 98 | -1 |
| `0021500114` | LAL | 90 | 91 | -1 |
| `0021500171` | NOP | 97 | 96 | +1 |
| `0021500171` | OKC | 96 | 97 | -1 |
| `0021500201` | POR | 94 | 93 | +1 |
| `0021500211` | MEM | 102 | 103 | -1 |
| `0021500253` | IND | 104 | 103 | +1 |
| `0021500276` | LAC | 99 | 100 | -1 |
| `0021500299` | MEM | 93 | 94 | -1 |
| `0021500301` | LAL | 100 | 101 | -1 |
| `0021500420` | MIA | 85 | 86 | -1 |
| `0021500480` | GSW | 95 | 94 | +1 |
| `0021500510` | LAL | 95 | 96 | -1 |
| `0021500564` | POR | 97 | 98 | -1 |
| `0021500570` | DET | 102 | 103 | -1 |
| `0021500587` | CHI | 103 | 102 | +1 |
| `0021500605` | GSW | 99 | 100 | -1 |
| `0021500626` | NOP | 92 | 93 | -1 |
| `0021500701` | OKC | 108 | 109 | -1 |
| `0021500727` | TOR | 97 | 98 | -1 |
| `0021500739` | WAS | 111 | 112 | -1 |
| `0021500751` | CHA | 94 | 93 | +1 |
| `0021500751` | MIA | 95 | 96 | -1 |
| `0021500784` | MIA | 95 | 94 | +1 |
| `0021500784` | SAS | 95 | 94 | +1 |
| `0021500805` | DAL | 107 | 106 | +1 |
| `0021500811` | PHI | 101 | 102 | -1 |
| `0021500836` | GSW | 100 | 101 | -1 |
| `0021500838` | MIN | 103 | 104 | -1 |
| `0021500863` | NYK | 97 | 96 | +1 |
| `0021500863` | ORL | 95 | 96 | -1 |
| `0021500889` | OKC | 99 | 100 | -1 |
| `0021500976` | PHI | 99 | 100 | -1 |
| `0021501057` | BOS | 89 | 90 | -1 |
| `0021501057` | TOR | 90 | 91 | -1 |
