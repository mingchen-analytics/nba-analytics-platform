# Possession checks: 2023-24 playoffs

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 164 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 82 | 1 |
| 8 | our possession counts vs pbpstats (per team-game) | warning | fail | 164 | 32 |

Check 8: 80.49% of team-games identical to pbpstats, 99.39% within 1. Distribution of (ours - pbpstats): {'-1': 2, '0': 132, '1': 29, '2': 1}.

## Team-games that differ from pbpstats

Reported, never fixed to match (working agreement 11).

| game_id | team (defense) | ours | pbpstats | ours - pbpstats |
|---|---|---|---|---|
| `0042300101` | BOS | 89 | 88 | +1 |
| `0042300101` | MIA | 89 | 88 | +1 |
| `0042300103` | MIA | 85 | 84 | +1 |
| `0042300104` | MIA | 94 | 93 | +1 |
| `0042300111` | NYK | 89 | 88 | +1 |
| `0042300116` | PHI | 90 | 89 | +1 |
| `0042300123` | MIL | 97 | 96 | +1 |
| `0042300133` | ORL | 90 | 89 | +1 |
| `0042300134` | ORL | 95 | 94 | +1 |
| `0042300136` | CLE | 96 | 95 | +1 |
| `0042300143` | OKC | 98 | 97 | +1 |
| `0042300151` | LAL | 94 | 93 | +1 |
| `0042300152` | DEN | 92 | 91 | +1 |
| `0042300153` | DEN | 97 | 96 | +1 |
| `0042300161` | MIN | 96 | 95 | +1 |
| `0042300172` | DAL | 91 | 92 | -1 |
| `0042300201` | BOS | 92 | 91 | +1 |
| `0042300202` | CLE | 92 | 91 | +1 |
| `0042300204` | CLE | 91 | 90 | +1 |
| `0042300213` | NYK | 92 | 91 | +1 |
| `0042300215` | IND | 93 | 92 | +1 |
| `0042300216` | IND | 87 | 86 | +1 |
| `0042300221` | DAL | 95 | 94 | +1 |
| `0042300222` | OKC | 96 | 95 | +1 |
| `0042300223` | OKC | 96 | 95 | +1 |
| `0042300225` | OKC | 89 | 88 | +1 |
| `0042300231` | DEN | 92 | 91 | +1 |
| `0042300234` | DEN | 90 | 91 | -1 |
| `0042300234` | MIN | 93 | 92 | +1 |
| `0042300301` | IND | 112 | 110 | +2 |
| `0042300304` | BOS | 94 | 93 | +1 |
| `0042300312` | MIN | 93 | 92 | +1 |
