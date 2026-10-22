# Possession checks: 2025-26 regular

Our possessions (`core.possessions`, profile and rules version recorded per row) against the sources. Numbers and IDs only.

| check | what | level | status | checked | failed |
|---|---|---|---|---|---|
| 111 | possession points + FTs outside possessions = final score | hard | pass | 2460 | 0 |
| 7 | team possession counts in a game differ by <= 2 | warning | fail | 1230 | 3 |
| 8 | our possession counts vs pbpstats | warning | skip | None | None |

No pbpstats reference exists for this season, so check 8 is skipped.

Check 111, known source score conflicts (registered in `core.known_gaps`, not failed): [['0022500029', 1610612764, 114, 115]].
