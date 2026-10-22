# Possession checks: 2005-06 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2460 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1230 | 2 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 2460 | 29 |

Check 8: 98.82% of team-games identical to pbpstats, 99.92% within 1. Distribution of (ours - pbpstats): {'-2': 2, '-1': 24, '0': 2431, '1': 3}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0020500034` | DET | 95 | 96 | -1 |
| `0020500121` | IND | 94 | 95 | -1 |
| `0020500220` | TOR | 87 | 88 | -1 |
| `0020500311` | NYK | 91 | 92 | -1 |
| `0020500311` | ORL | 90 | 91 | -1 |
| `0020500347` | ORL | 90 | 91 | -1 |
| `0020500529` | UTA | 89 | 90 | -1 |
| `0020500563` | SAC | 103 | 104 | -1 |
| `0020500708` | LAC | 87 | 88 | -1 |
| `0020500712` | GSW | 102 | 103 | -1 |
| `0020500769` | CHA | 88 | 89 | -1 |
| `0020500777` | CHI | 95 | 96 | -1 |
| `0020500793` | NJN | 86 | 85 | +1 |
| `0020500793` | ORL | 86 | 85 | +1 |
| `0020500804` | ATL | 95 | 97 | -2 |
| `0020500804` | IND | 99 | 100 | -1 |
| `0020500857` | WAS | 99 | 100 | -1 |
| `0020500870` | MIL | 88 | 89 | -1 |
| `0020500887` | ORL | 82 | 83 | -1 |
| `0020500890` | ATL | 96 | 98 | -2 |
| `0020500911` | CLE | 82 | 83 | -1 |
| `0020500911` | ORL | 82 | 83 | -1 |
| `0020500969` | NYK | 88 | 89 | -1 |
| `0020501023` | NOK | 90 | 91 | -1 |
| `0020501035` | NJN | 83 | 84 | -1 |
| `0020501080` | BOS | 95 | 96 | -1 |
| `0020501114` | GSW | 99 | 98 | +1 |
| `0020501114` | NOK | 99 | 100 | -1 |
| `0020501178` | CHA | 93 | 94 | -1 |
