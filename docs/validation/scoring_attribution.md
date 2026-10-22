# Scoring events by the team not on offense (design check, plan 2026-10-18 step 6c)

Reference possessions: ramirobentes' own possession flag (not our possession logic).
A row = scoring events whose team differs from the offense of the possession they fall in.

## 2004-05 regular season

Scoring events: 136,897; by the team not on offense: 4,154 (4,154 points).

| event | type | situation | events | points | example game_id / event_num | technical FT? |
|---|---|---|---|---|---|---|
| free throw | FT 1 of 1 | and-1 | 3,915 | 3,915 | 0020400001 / 20 | **no** |
| free throw | technical FT | other | 190 | 190 | 0020400005 / 438 | yes |
| free throw | technical FT | and-1 | 42 | 42 | 0020400005 / 446 | yes |
| free throw | technical FT | period boundary | 5 | 5 | 0020400394 / 335 | yes |
| free throw | FT 1 of 2 | period boundary | 1 | 1 | 0020400520 / 208 | **no** |
| free throw | FT 1 of 1 | other | 1 | 1 | 0020400278 / 200 | **no** |

## 2024-25 regular season

Scoring events: 144,140; by the team not on offense: 4,457 (4,457 points).

| event | type | situation | events | points | example game_id / event_num | technical FT? |
|---|---|---|---|---|---|---|
| free throw | FT 1 of 1 | and-1 | 4,231 | 4,231 | 0022400001 / 121 | **no** |
| free throw | technical FT | other | 154 | 154 | 0022400019 / 812 | yes |
| free throw | technical FT | and-1 | 54 | 54 | 0022400104 / 397 | yes |
| free throw | technical FT | period boundary | 13 | 13 | 0022400043 / 325 | yes |
| free throw | technical FT 2 of 2 | other | 1 | 1 | 0022400718 / 713 | yes |
| free throw | FT 1 of 1 | other | 1 | 1 | 0022400105 / 501 | **no** |
| free throw | FT 1 of 2 | period boundary | 1 | 1 | 0022400303 / 502 | **no** |
| free throw | technical FT 1 of 2 | other | 1 | 1 | 0022400718 / 712 | yes |
| free throw | FT 2 of 2 | period boundary | 1 | 1 | 0022400303 / 503 | **no** |

## Verdict

Not every scoring event by the team not on offense is a technical free throw, so by the plan's rule
the design is **not** declared valid here and nothing is changed. **[待確認]**

- **and-1 free throws: 8,146.** The reference segmentation ends the possession on the made
  field goal, so the and-1 FT lands in the opponent's next possession. Under CLAUDE.md's rule
  (an and-1 possession ends after the free throw) these FTs belong to the shooter's possession —
  a reference artifact, not a counter-example (inference).
- **Free throws at a period boundary: 3** (clock 0:00 or a period's starting clock): FTs
  from a foul at the buzzer, shot when the reference has already moved to the next possession.
- **Other: 2.** Listed above; to be looked at one by one.

If the owner's possession code ends and-1 possessions after the FT, only the boundary cases and the
'other' rows remain to be decided.

