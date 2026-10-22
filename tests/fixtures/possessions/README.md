# Possession fixtures (2004-05, real sequences)

Built by `scripts/build_possession_fixtures.py`. One CSV per possession-rule case, two
sequences each (`fixture` = A / B), in the `core.events` layout plus on-court lineups
(`home_player_ids` / `away_player_ids`, `|`-separated, as the source gives them: on a
substitution row the source lineup is already post-sub). IDs and codes only.

| file | sequences |
|---|---|
| `end_of_period.csv` | possession starting with <= 2 s left in a period (one 0-point, one scoring) |
| `substitution_between_free_throws.csv` | substitution between the first and last FT of a trip (shooting team / defending team) |
| `offensive_rebound.csv` | possession with 2 and with 3 chances (offensive rebounds) |
| `flagrant_foul.csv` | flagrant foul: FT trip, then the fouled team keeps the ball |
| `technical_free_throw.csv` | technical FT shot by the defense / by the offense |
| `team_rebound_after_non_final_ft.csv` | team rebound row after a missed non-final FT |
| `missed_final_free_throw.csv` | missed final FT followed by an offensive / a defensive rebound |
| `jump_ball.csv` | jump ball that is not an opening tip (possession changes / is kept, approximated) |
| `start_type.csv` | possession after a steal / possession after a timeout |
| `garbage_time.csv` | start of garbage time (CTG, retroactive) / margin that closes again (not garbage time) |
