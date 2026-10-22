# Possession checks: 2021-22 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 174 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 87 | 1 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 174 | 31 |

Check 8: 82.18% of team-games identical to pbpstats, 95.40% within 1. Distribution of (ours - pbpstats): {'-1': 1, '0': 143, '1': 22, '2': 8}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0042100104` | ATL | 86 | 87 | -1 |
| `0042100113` | BKN | 90 | 89 | +1 |
| `0042100113` | BOS | 90 | 89 | +1 |
| `0042100114` | BOS | 95 | 94 | +1 |
| `0042100122` | CHI | 101 | 99 | +2 |
| `0042100123` | CHI | 97 | 96 | +1 |
| `0042100125` | MIL | 104 | 103 | +1 |
| `0042100132` | TOR | 89 | 88 | +1 |
| `0042100142` | PHX | 96 | 95 | +1 |
| `0042100144` | PHX | 91 | 90 | +1 |
| `0042100145` | NOP | 96 | 95 | +1 |
| `0042100146` | NOP | 93 | 92 | +1 |
| `0042100152` | MEM | 103 | 102 | +1 |
| `0042100153` | MIN | 97 | 95 | +2 |
| `0042100154` | MEM | 103 | 102 | +1 |
| `0042100163` | GSW | 98 | 97 | +1 |
| `0042100164` | GSW | 101 | 99 | +2 |
| `0042100171` | DAL | 90 | 89 | +1 |
| `0042100172` | UTA | 89 | 88 | +1 |
| `0042100173` | DAL | 95 | 93 | +2 |
| `0042100211` | MIL | 100 | 99 | +1 |
| `0042100212` | BOS | 94 | 93 | +1 |
| `0042100217` | BOS | 99 | 98 | +1 |
| `0042100221` | DAL | 93 | 91 | +2 |
| `0042100222` | DAL | 94 | 92 | +2 |
| `0042100223` | PHX | 89 | 87 | +2 |
| `0042100224` | PHX | 92 | 91 | +1 |
| `0042100225` | PHX | 94 | 93 | +1 |
| `0042100302` | BOS | 94 | 92 | +2 |
| `0042100304` | MIA | 92 | 91 | +1 |
| `0042100307` | MIA | 96 | 95 | +1 |
