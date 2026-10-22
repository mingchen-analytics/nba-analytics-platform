# Possession checks: 2001-02 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2378 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1189 | 3 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2378 | 47 |

Check 8: 98.02% of team-games identical to pbpstats, 99.96% within 1. Distribution of (ours - pbpstats): {'-2': 1, '-1': 31, '0': 2331, '1': 15}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0020100002` | WAS | 91 | 92 | -1 |
| `0020100072` | MIL | 90 | 91 | -1 |
| `0020100089` | CHI | 90 | 91 | -1 |
| `0020100115` | TOR | 92 | 93 | -1 |
| `0020100134` | NJN | 93 | 94 | -1 |
| `0020100169` | BOS | 87 | 88 | -1 |
| `0020100182` | CLE | 94 | 93 | +1 |
| `0020100231` | CHI | 91 | 90 | +1 |
| `0020100236` | DAL | 93 | 94 | -1 |
| `0020100255` | CHI | 91 | 92 | -1 |
| `0020100255` | ORL | 90 | 89 | +1 |
| `0020100259` | DAL | 94 | 95 | -1 |
| `0020100277` | DEN | 89 | 88 | +1 |
| `0020100319` | PHX | 96 | 97 | -1 |
| `0020100319` | SAS | 97 | 96 | +1 |
| `0020100385` | PHX | 98 | 99 | -1 |
| `0020100385` | SAC | 98 | 97 | +1 |
| `0020100397` | POR | 91 | 92 | -1 |
| `0020100408` | MIA | 94 | 95 | -1 |
| `0020100423` | TOR | 88 | 89 | -1 |
| `0020100428` | HOU | 84 | 83 | +1 |
| `0020100428` | LAL | 86 | 85 | +1 |
| `0020100438` | CHI | 97 | 98 | -1 |
| `0020100438` | DAL | 96 | 98 | -2 |
| `0020100445` | NYK | 104 | 103 | +1 |
| `0020100450` | ORL | 90 | 91 | -1 |
| `0020100456` | PHX | 97 | 98 | -1 |
| `0020100514` | CHI | 100 | 99 | +1 |
| `0020100570` | CHH | 89 | 90 | -1 |
| `0020100588` | DEN | 92 | 93 | -1 |
| `0020100599` | ORL | 93 | 94 | -1 |
| `0020100639` | ORL | 97 | 98 | -1 |
| `0020100665` | SAS | 110 | 109 | +1 |
| `0020100679` | ORL | 103 | 104 | -1 |
| `0020100855` | DET | 84 | 85 | -1 |
| `0020100855` | MIA | 85 | 84 | +1 |
| `0020100883` | PHX | 91 | 92 | -1 |
| `0020100912` | SEA | 87 | 88 | -1 |
| `0020101014` | UTA | 85 | 86 | -1 |
| `0020101016` | LAL | 92 | 93 | -1 |
| `0020101029` | SAC | 94 | 95 | -1 |
| `0020101031` | MIL | 93 | 94 | -1 |
| `0020101032` | DAL | 104 | 105 | -1 |
| `0020101068` | TOR | 94 | 95 | -1 |
| `0020101113` | CHH | 82 | 81 | +1 |
| `0020101169` | ORL | 102 | 101 | +1 |
| `0020101171` | UTA | 96 | 95 | +1 |
