# Box marts (layer 1): row counts and consistency

Built by `nba_platform.marts.box_marts` from the official box score. Numbers and IDs only.

| table | rows |
|---|---|
| `marts.player_game` | 786,768 |
| `marts.player_season` | 22,572 |
| `marts.team_game` | 75,972 |
| `marts.team_season` | 1,372 |

## Team points: official box vs final score in `core.games`

Team-games where the player box points do not add up to the final score: 6 (in 5 games). Reported, not corrected. A box that agrees with the event points (EV) but not the score is a score conflict in the source; a box that disagrees with both is an inconsistency in the official box.

| game_id | home | box points | event points (EV) | score |
|---|---|---|---|---|
| `0020300778` | away | 98 | 101 | 101 |
| `0021201066` | away | 120 | 119 | 119 |
| `0022500029` | home | 115 | 115 | 114 |
| `0029600070` | away | 79 | 86 | 86 |
| `0029600070` | home | 108 | 101 | 101 |
| `0029800661` | away | 97 | 93 | 93 |
