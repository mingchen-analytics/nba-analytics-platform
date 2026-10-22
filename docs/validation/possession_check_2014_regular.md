# Possession checks: 2013-14 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2460 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1230 | 7 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2460 | 38 |

Check 8: 98.46% of team-games identical to pbpstats, 99.96% within 1. Distribution of (ours - pbpstats): {'-1': 26, '0': 2422, '1': 11, '2': 1}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0021300026` | DET | 100 | 101 | -1 |
| `0021300028` | MIA | 96 | 95 | +1 |
| `0021300089` | BOS | 89 | 90 | -1 |
| `0021300091` | MEM | 95 | 96 | -1 |
| `0021300188` | IND | 102 | 101 | +1 |
| `0021300188` | PHI | 102 | 101 | +1 |
| `0021300233` | LAL | 95 | 96 | -1 |
| `0021300283` | BOS | 90 | 89 | +1 |
| `0021300283` | DEN | 90 | 89 | +1 |
| `0021300311` | IND | 90 | 89 | +1 |
| `0021300316` | CHI | 86 | 87 | -1 |
| `0021300333` | NYK | 85 | 86 | -1 |
| `0021300373` | DET | 96 | 97 | -1 |
| `0021300403` | LAC | 98 | 99 | -1 |
| `0021300474` | MIA | 100 | 101 | -1 |
| `0021300476` | BKN | 89 | 90 | -1 |
| `0021300537` | BKN | 94 | 93 | +1 |
| `0021300574` | LAL | 109 | 108 | +1 |
| `0021300594` | IND | 93 | 91 | +2 |
| `0021300600` | DAL | 98 | 99 | -1 |
| `0021300606` | DAL | 92 | 93 | -1 |
| `0021300616` | ORL | 88 | 89 | -1 |
| `0021300633` | ORL | 100 | 101 | -1 |
| `0021300634` | TOR | 94 | 95 | -1 |
| `0021300710` | ORL | 88 | 89 | -1 |
| `0021300726` | PHI | 101 | 102 | -1 |
| `0021300742` | WAS | 94 | 95 | -1 |
| `0021300754` | PHX | 92 | 93 | -1 |
| `0021300757` | LAL | 94 | 93 | +1 |
| `0021300787` | PHI | 99 | 98 | +1 |
| `0021300817` | PHI | 104 | 105 | -1 |
| `0021300906` | UTA | 88 | 89 | -1 |
| `0021300956` | DAL | 96 | 97 | -1 |
| `0021301031` | LAL | 108 | 109 | -1 |
| `0021301033` | HOU | 99 | 98 | +1 |
| `0021301067` | MIA | 86 | 87 | -1 |
| `0021301167` | MEM | 85 | 86 | -1 |
| `0021301172` | SAC | 95 | 96 | -1 |
