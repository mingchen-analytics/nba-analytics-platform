# Possession checks: 2009-10 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2460 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1230 | 4 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2458 | 26 |

Check 8: 98.94% of team-games identical to pbpstats, 100.00% within 1. Distribution of (ours - pbpstats): {'-1': 20, '0': 2432, '1': 6}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0020900007` | CLE | 97 | 98 | -1 |
| `0020900007` | TOR | 99 | 100 | -1 |
| `0020900086` | NJN | 92 | 91 | +1 |
| `0020900207` | NYK | 101 | 100 | +1 |
| `0020900210` | BOS | 91 | 92 | -1 |
| `0020900215` | DAL | 93 | 94 | -1 |
| `0020900321` | HOU | 91 | 92 | -1 |
| `0020900387` | ATL | 92 | 93 | -1 |
| `0020900406` | PHI | 94 | 95 | -1 |
| `0020900423` | CLE | 94 | 95 | -1 |
| `0020900467` | LAC | 88 | 89 | -1 |
| `0020900567` | POR | 90 | 91 | -1 |
| `0020900590` | UTA | 98 | 99 | -1 |
| `0020900595` | POR | 84 | 83 | +1 |
| `0020900595` | WAS | 85 | 84 | +1 |
| `0020900618` | SAS | 97 | 98 | -1 |
| `0020900670` | HOU | 95 | 96 | -1 |
| `0020900672` | POR | 89 | 90 | -1 |
| `0020900720` | NJN | 95 | 94 | +1 |
| `0020900730` | SAS | 84 | 85 | -1 |
| `0020900789` | BOS | 94 | 95 | -1 |
| `0020900811` | NOH | 100 | 99 | +1 |
| `0020900932` | IND | 96 | 97 | -1 |
| `0020901067` | MEM | 102 | 103 | -1 |
| `0020901166` | ORL | 89 | 90 | -1 |
| `0020901171` | CLE | 95 | 96 | -1 |
