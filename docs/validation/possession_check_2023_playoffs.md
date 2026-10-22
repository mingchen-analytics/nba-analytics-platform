# Possession checks: 2022-23 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 168 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | pass | 84 | 0 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 168 | 29 |

Check 8: 82.74% of team-games identical to pbpstats, 98.81% within 1. Distribution of (ours - pbpstats): {'0': 139, '1': 27, '2': 2}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0042200101` | MIA | 102 | 101 | +1 |
| `0042200103` | MIA | 98 | 97 | +1 |
| `0042200105` | MIL | 114 | 113 | +1 |
| `0042200111` | BOS | 103 | 102 | +1 |
| `0042200114` | BOS | 106 | 105 | +1 |
| `0042200115` | ATL | 96 | 95 | +1 |
| `0042200116` | BOS | 97 | 96 | +1 |
| `0042200121` | PHI | 90 | 89 | +1 |
| `0042200132` | CLE | 91 | 90 | +1 |
| `0042200144` | MIN | 100 | 99 | +1 |
| `0042200145` | DEN | 94 | 93 | +1 |
| `0042200161` | SAC | 105 | 104 | +1 |
| `0042200163` | GSW | 101 | 100 | +1 |
| `0042200172` | PHX | 92 | 91 | +1 |
| `0042200215` | PHI | 95 | 94 | +1 |
| `0042200221` | DEN | 97 | 96 | +1 |
| `0042200222` | DEN | 93 | 92 | +1 |
| `0042200223` | PHX | 102 | 101 | +1 |
| `0042200225` | PHX | 99 | 98 | +1 |
| `0042200231` | LAL | 100 | 98 | +2 |
| `0042200232` | GSW | 102 | 101 | +1 |
| `0042200232` | LAL | 101 | 100 | +1 |
| `0042200234` | LAL | 97 | 96 | +1 |
| `0042200301` | MIA | 97 | 96 | +1 |
| `0042200304` | MIA | 94 | 93 | +1 |
| `0042200305` | MIA | 86 | 85 | +1 |
| `0042200307` | BOS | 93 | 91 | +2 |
| `0042200313` | LAL | 96 | 95 | +1 |
| `0042200404` | MIA | 91 | 90 | +1 |
