# BigDataBall cross-check (validation check 11)

BigDataBall is used for validation only; nothing from it is loaded into core tables except
`core.player_xref` rows (source `bigdataball`). Numbers and IDs only, except the list of
unmatched BigDataBall names, which is the point of that list.

## 2004-05

| measure | value |
|---|---|
| BigDataBall game files | 1,011 |
| … found in core.games | 1,011 |
| … not in core.games | 0 |
| final score differs | 0 |
| BigDataBall events | 458,692 |
| … same event number in our events | 458,684 (100.00%) |
| … and same period + clock (aligned) | 458,143 (99.88%) |
| aligned events with identical home **and** away lineups | 455,377 (99.40%) |
| aligned team-lineups identical | 912,346 / 916,286 (99.57%) |
| BigDataBall names | 460 |
| … mapped by name | 457 |
| … mapped by lineup | 2 |
| … unmatched (listed below) | 1 |

Where the lineups differ:

| players different | team-lineups |
|---|---|
| 0 | 293 |
| 1 | 1,795 |
| 2 | 1,152 |
| 3 | 461 |
| 4 | 188 |
| 5 | 51 |

Differences come in runs: 99 runs; the event where a run starts:

| event type | runs |
|---|---|
| period_start | 63 |
| substitution | 22 |
| free_throw | 10 |
| turnover | 3 |
| shot_missed | 1 |

Reading: almost every difference is **one** player, persisting from a substitution or
a period start until the next substitution — the two sources reconstruct some lineups
differently (typically substitutions not logged between periods). Neither source is
the ground truth; which one is right needs a third source (e.g. box-score minutes
or video). Unmatched names below also count as disagreement.

Games with the lowest lineup agreement:

| game_id | team-lineups identical |
|---|---|
| 0020400818 | 68.22% |
| 0020401031 | 69.03% |
| 0020400545 | 74.03% |
| 0020401080 | 74.05% |
| 0020400193 | 74.28% |
| 0020400732 | 76.19% |
| 0020400521 | 76.70% |
| 0020401014 | 77.04% |
| 0020400377 | 80.57% |
| 0020401062 | 81.82% |

Unmatched BigDataBall names (not guessed):

| name | votes by candidate ID (`ambiguous` = not a single leftover) |
|---|---|
| Ha Seung-Jin | {2775: 590, 2216: 1} |

An unmatched name can be added by hand as a `manual` row in `core.player_xref` after
checking it; the candidate IDs above are evidence, not decisions.

### Arbitration of lineup disagreements (2004-05)

Report only. Evidence: box-score minutes (nba_api) and official play-by-play substitutions
(shufinskiy `nbastats_*`); rules in `src/nba_platform/validate/bdb_arbitration.py`. Each verdict is an
**inference** from that evidence.

Disagreement runs (our event order): 97.

**Runs starting at a substitution: 22**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 13 | 0 | 2 | 0 | — | 7 |
| official substitutions | 17 | 1 | — | — | 4 | 0 |
| **combined** | **18** | **1** | — | — | 0 | 3 |

**Runs starting at a period start: 63**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 44 | 0 | 16 | 0 | — | 3 |
| official substitutions | 41 | 0 | — | — | 16 | 6 |
| **combined** | **62** | **0** | — | — | 0 | 1 |

**Runs starting at a other: 12**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 1 | 0 | 0 | 0 | — | 11 |
| official substitutions | 0 | 6 | — | — | 0 | 6 |
| **combined** | **1** | **6** | — | — | 0 | 5 |

Overall: 88 of 97 runs decided (91%) — ramirobentes right in 81, BigDataBall right in 7; 0 with conflicting evidence, 9 undetermined.

## 2005-06

| measure | value |
|---|---|
| BigDataBall game files | 1,313 |
| … found in core.games | 1,313 |
| … not in core.games | 0 |
| final score differs | 0 |
| BigDataBall events | 591,352 |
| … same event number in our events | 591,349 (100.00%) |
| … and same period + clock (aligned) | 591,347 (100.00%) |
| aligned events with identical home **and** away lineups | 567,635 (95.99%) |
| aligned team-lineups identical | 1,158,982 / 1,182,694 (98.00%) |
| BigDataBall names | 458 |
| … mapped by name | 455 |
| … mapped by lineup | 2 |
| … unmatched (listed below) | 1 |

Where the lineups differ:

| players different | team-lineups |
|---|---|
| 1 | 23,709 |
| 2 | 3 |

Differences come in runs: 268 runs; the event where a run starts:

| event type | runs |
|---|---|
| substitution | 204 |
| period_start | 54 |
| free_throw | 10 |

Reading: almost every difference is **one** player, persisting from a substitution or
a period start until the next substitution — the two sources reconstruct some lineups
differently (typically substitutions not logged between periods). Neither source is
the ground truth; which one is right needs a third source (e.g. box-score minutes
or video). Unmatched names below also count as disagreement.

Games with the lowest lineup agreement:

| game_id | team-lineups identical |
|---|---|
| 0040500203 | 53.11% |
| 0020500618 | 53.17% |
| 0020500897 | 54.00% |
| 0020500844 | 54.21% |
| 0020500891 | 55.63% |
| 0020501004 | 55.70% |
| 0020500855 | 56.17% |
| 0020500879 | 56.44% |
| 0040500206 | 56.78% |
| 0020501133 | 57.93% |

Unmatched BigDataBall names (not guessed):

| name | votes by candidate ID (`ambiguous` = not a single leftover) |
|---|---|
| Ronald Murray | {2436: 23689, 951: 1} |

An unmatched name can be added by hand as a `manual` row in `core.player_xref` after
checking it; the candidate IDs above are evidence, not decisions.

### Arbitration of lineup disagreements (2005-06)

Report only. Evidence: box-score minutes (nba_api) and official play-by-play substitutions
(shufinskiy `nbastats_*`); rules in `src/nba_platform/validate/bdb_arbitration.py`. Each verdict is an
**inference** from that evidence.

Disagreement runs (our event order): 16.

**Runs starting at a substitution: 3**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 0 | 0 | 0 | 0 | — | 3 |
| official substitutions | 0 | 0 | — | — | 3 | 0 |
| **combined** | **0** | **0** | — | — | 0 | 3 |

**Runs starting at a period start: 5**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 0 | 0 | 0 | 0 | — | 5 |
| official substitutions | 5 | 0 | — | — | 0 | 0 |
| **combined** | **5** | **0** | — | — | 0 | 0 |

**Runs starting at a other: 8**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 0 | 0 | 0 | 0 | — | 8 |
| official substitutions | 0 | 6 | — | — | 0 | 2 |
| **combined** | **0** | **6** | — | — | 0 | 2 |

Overall: 11 of 16 runs decided (69%) — ramirobentes right in 5, BigDataBall right in 6; 0 with conflicting evidence, 5 undetermined.

## 2007-08

| measure | value |
|---|---|
| BigDataBall game files | 1,309 |
| … found in core.games | 1,309 |
| … not in core.games | 0 |
| final score differs | 0 |
| BigDataBall events | 586,142 |
| … same event number in our events | 586,140 (100.00%) |
| … and same period + clock (aligned) | 586,132 (100.00%) |
| aligned events with identical home **and** away lineups | 562,290 (95.93%) |
| aligned team-lineups identical | 1,148,159 / 1,172,264 (97.94%) |
| BigDataBall names | 450 |
| … mapped by name | 445 |
| … mapped by lineup | 2 |
| … unmatched (listed below) | 3 |

Where the lineups differ:

| players different | team-lineups |
|---|---|
| 1 | 24,105 |

Differences come in runs: 393 runs; the event where a run starts:

| event type | runs |
|---|---|
| substitution | 275 |
| period_start | 108 |
| free_throw | 10 |

Reading: almost every difference is **one** player, persisting from a substitution or
a period start until the next substitution — the two sources reconstruct some lineups
differently (typically substitutions not logged between periods). Neither source is
the ground truth; which one is right needs a third source (e.g. box-score minutes
or video). Unmatched names below also count as disagreement.

Games with the lowest lineup agreement:

| game_id | team-lineups identical |
|---|---|
| 0020700943 | 39.89% |
| 0020700321 | 58.78% |
| 0020700487 | 62.69% |
| 0020700793 | 62.80% |
| 0020700952 | 62.99% |
| 0020700440 | 65.05% |
| 0020700837 | 65.55% |
| 0020700817 | 65.91% |
| 0020701152 | 66.34% |
| 0020701049 | 66.34% |

Unmatched BigDataBall names (not guessed):

| name | votes by candidate ID (`ambiguous` = not a single leftover) |
|---|---|
| Charles Hayes | {101236: 13899, 'ambiguous': 968} |
| Marcus Williams | {200766: 8171, 201173: 380} |
| Michael Harris | {'ambiguous': 968, 200839: 611, 101236: 3} |

An unmatched name can be added by hand as a `manual` row in `core.player_xref` after
checking it; the candidate IDs above are evidence, not decisions.

### Arbitration of lineup disagreements (2007-08)

Report only. Evidence: box-score minutes (nba_api) and official play-by-play substitutions
(shufinskiy `nbastats_*`); rules in `src/nba_platform/validate/bdb_arbitration.py`. Each verdict is an
**inference** from that evidence.

Disagreement runs (our event order): 205.

**Runs starting at a substitution: 163**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 153 | 0 | 0 | 0 | — | 10 |
| official substitutions | 161 | 0 | — | — | 0 | 2 |
| **combined** | **161** | **0** | — | — | 0 | 2 |

**Runs starting at a period start: 33**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 30 | 0 | 0 | 0 | — | 3 |
| official substitutions | 29 | 0 | — | — | 0 | 4 |
| **combined** | **33** | **0** | — | — | 0 | 0 |

**Runs starting at a other: 9**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 0 | 0 | 0 | 0 | — | 9 |
| official substitutions | 0 | 9 | — | — | 0 | 0 |
| **combined** | **0** | **9** | — | — | 0 | 0 |

Overall: 203 of 205 runs decided (99%) — ramirobentes right in 194, BigDataBall right in 9; 0 with conflicting evidence, 2 undetermined.

## 2010-11

| measure | value |
|---|---|
| BigDataBall game files | 1,306 |
| … found in core.games | 1,306 |
| … not in core.games | 0 |
| final score differs | 0 |
| BigDataBall events | 584,789 |
| … same event number in our events | 584,789 (100.00%) |
| … and same period + clock (aligned) | 584,781 (100.00%) |
| aligned events with identical home **and** away lineups | 565,999 (96.79%) |
| aligned team-lineups identical | 1,150,780 / 1,169,562 (98.39%) |
| BigDataBall names | 452 |
| … mapped by name | 448 |
| … mapped by lineup | 2 |
| … unmatched (listed below) | 2 |

Where the lineups differ:

| players different | team-lineups |
|---|---|
| 1 | 18,782 |

Differences come in runs: 236 runs; the event where a run starts:

| event type | runs |
|---|---|
| substitution | 132 |
| period_start | 100 |
| free_throw | 2 |
| jump_ball | 2 |

Reading: almost every difference is **one** player, persisting from a substitution or
a period start until the next substitution — the two sources reconstruct some lineups
differently (typically substitutions not logged between periods). Neither source is
the ground truth; which one is right needs a third source (e.g. box-score minutes
or video). Unmatched names below also count as disagreement.

Games with the lowest lineup agreement:

| game_id | team-lineups identical |
|---|---|
| 0021000885 | 57.38% |
| 0021001009 | 57.88% |
| 0021000728 | 58.05% |
| 0021000749 | 58.16% |
| 0021001146 | 58.23% |
| 0021001189 | 58.39% |
| 0021000659 | 59.41% |
| 0021001108 | 59.80% |
| 0021000718 | 59.98% |
| 0021001062 | 60.30% |

Unmatched BigDataBall names (not guessed):

| name | votes by candidate ID (`ambiguous` = not a single leftover) |
|---|---|
| Charles Hayes | {101236: 18602, 'ambiguous': 81} |
| Michael Harris | {200839: 77, 'ambiguous': 81} |

An unmatched name can be added by hand as a `manual` row in `core.player_xref` after
checking it; the candidate IDs above are evidence, not decisions.

### Arbitration of lineup disagreements (2010-11)

Report only. Evidence: box-score minutes (nba_api) and official play-by-play substitutions
(shufinskiy `nbastats_*`); rules in `src/nba_platform/validate/bdb_arbitration.py`. Each verdict is an
**inference** from that evidence.

Disagreement runs (our event order): 15.

**Runs starting at a substitution: 5**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 4 | 0 | 0 | 0 | — | 1 |
| official substitutions | 5 | 0 | — | — | 0 | 0 |
| **combined** | **5** | **0** | — | — | 0 | 0 |

**Runs starting at a period start: 6**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 0 | 0 | 0 | 0 | — | 6 |
| official substitutions | 6 | 0 | — | — | 0 | 0 |
| **combined** | **6** | **0** | — | — | 0 | 0 |

**Runs starting at a other: 4**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 0 | 0 | 0 | 0 | — | 4 |
| official substitutions | 1 | 1 | — | — | 0 | 2 |
| **combined** | **1** | **1** | — | — | 0 | 2 |

Overall: 13 of 15 runs decided (87%) — ramirobentes right in 12, BigDataBall right in 1; 0 with conflicting evidence, 2 undetermined.

## 2012-13

| measure | value |
|---|---|
| BigDataBall game files | 1,314 |
| … found in core.games | 1,314 |
| … not in core.games | 0 |
| final score differs | 1 |
| BigDataBall events | 586,028 |
| … same event number in our events | 586,027 (100.00%) |
| … and same period + clock (aligned) | 586,023 (100.00%) |
| aligned events with identical home **and** away lineups | 567,812 (96.89%) |
| aligned team-lineups identical | 1,153,819 / 1,172,046 (98.44%) |
| BigDataBall names | 470 |
| … mapped by name | 463 |
| … mapped by lineup | 5 |
| … unmatched (listed below) | 2 |

Final score differences:

| game_id | home bdb | home ours | away bdb | away ours |
|---|---|---|---|---|
| 0021201066 | 117 | 117 | 120 | 119 |

Where the lineups differ:

| players different | team-lineups |
|---|---|
| 1 | 18,227 |

Differences come in runs: 202 runs; the event where a run starts:

| event type | runs |
|---|---|
| substitution | 176 |
| period_start | 24 |
| turnover | 2 |

Reading: almost every difference is **one** player, persisting from a substitution or
a period start until the next substitution — the two sources reconstruct some lineups
differently (typically substitutions not logged between periods). Neither source is
the ground truth; which one is right needs a third source (e.g. box-score minutes
or video). Unmatched names below also count as disagreement.

Games with the lowest lineup agreement:

| game_id | team-lineups identical |
|---|---|
| 0021200400 | 62.12% |
| 0021200863 | 63.52% |
| 0021200973 | 64.25% |
| 0021200597 | 64.32% |
| 0021200958 | 65.34% |
| 0021200632 | 65.48% |
| 0021200645 | 65.55% |
| 0021200940 | 65.83% |
| 0021200879 | 65.90% |
| 0021200230 | 66.00% |

Unmatched BigDataBall names (not guessed):

| name | votes by candidate ID (`ambiguous` = not a single leftover) |
|---|---|
| Chris Johnson | {'ambiguous': 1784, 202419: 871, 203187: 952} |
| Jose Juan Barea | {200826: 14614, 'ambiguous': 1784} |

An unmatched name can be added by hand as a `manual` row in `core.player_xref` after
checking it; the candidate IDs above are evidence, not decisions.

### Arbitration of lineup disagreements (2012-13)

Report only. Evidence: box-score minutes (nba_api) and official play-by-play substitutions
(shufinskiy `nbastats_*`); rules in `src/nba_platform/validate/bdb_arbitration.py`. Each verdict is an
**inference** from that evidence.

Disagreement runs (our event order): 26.

**Runs starting at a substitution: 20**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 0 | 0 | 0 | 0 | — | 20 |
| official substitutions | 20 | 0 | — | — | 0 | 0 |
| **combined** | **20** | **0** | — | — | 0 | 0 |

**Runs starting at a period start: 4**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 0 | 0 | 0 | 0 | — | 4 |
| official substitutions | 3 | 0 | — | — | 1 | 0 |
| **combined** | **3** | **0** | — | — | 0 | 1 |

**Runs starting at a other: 2**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 0 | 0 | 0 | 0 | — | 2 |
| official substitutions | 0 | 0 | — | — | 0 | 2 |
| **combined** | **0** | **0** | — | — | 0 | 2 |

Overall: 23 of 26 runs decided (88%) — ramirobentes right in 23, BigDataBall right in 0; 0 with conflicting evidence, 3 undetermined.

## 2013-14

| measure | value |
|---|---|
| BigDataBall game files | 1,319 |
| … found in core.games | 1,319 |
| … not in core.games | 0 |
| final score differs | 1 |
| BigDataBall events | 599,673 |
| … same event number in our events | 599,671 (100.00%) |
| … and same period + clock (aligned) | 599,665 (100.00%) |
| aligned events with identical home **and** away lineups | 566,869 (94.53%) |
| aligned team-lineups identical | 1,166,115 / 1,199,330 (97.23%) |
| BigDataBall names | 481 |
| … mapped by name | 471 |
| … mapped by lineup | 4 |
| … unmatched (listed below) | 6 |

Final score differences:

| game_id | home bdb | home ours | away bdb | away ours |
|---|---|---|---|---|
| 0021301006 | 115 | 117 | 111 | 111 |

Where the lineups differ:

| players different | team-lineups |
|---|---|
| 1 | 33,215 |

Differences come in runs: 496 runs; the event where a run starts:

| event type | runs |
|---|---|
| substitution | 381 |
| period_start | 115 |

Reading: almost every difference is **one** player, persisting from a substitution or
a period start until the next substitution — the two sources reconstruct some lineups
differently (typically substitutions not logged between periods). Neither source is
the ground truth; which one is right needs a third source (e.g. box-score minutes
or video). Unmatched names below also count as disagreement.

Games with the lowest lineup agreement:

| game_id | team-lineups identical |
|---|---|
| 0021300200 | 46.23% |
| 0021300014 | 48.09% |
| 0021300906 | 50.12% |
| 0021300085 | 52.20% |
| 0021300064 | 52.36% |
| 0021300274 | 53.54% |
| 0021300038 | 55.27% |
| 0021300030 | 56.02% |
| 0021300297 | 56.57% |
| 0021300169 | 57.67% |

Unmatched BigDataBall names (not guessed):

| name | votes by candidate ID (`ambiguous` = not a single leftover) |
|---|---|
| Enes Kanter | {202683: 18378, 'ambiguous': 1006} |
| Glen Rice Jr. | {203318: 843, 'ambiguous': 199} |
| Michael Harris | {'ambiguous': 1006, 200839: 1227} |
| Otto Porter | {203490: 2970, 'ambiguous': 199} |
| Perry Jones | {203103: 7717, 200757: 1} |
| Tony Mitchell | {203502: 781, 203183: 81} |

An unmatched name can be added by hand as a `manual` row in `core.player_xref` after
checking it; the candidate IDs above are evidence, not decisions.

### Arbitration of lineup disagreements (2013-14)

Report only. Evidence: box-score minutes (nba_api) and official play-by-play substitutions
(shufinskiy `nbastats_*`); rules in `src/nba_platform/validate/bdb_arbitration.py`. Each verdict is an
**inference** from that evidence.

Disagreement runs (our event order): 159.

**Runs starting at a substitution: 142**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 123 | 0 | 0 | 0 | — | 19 |
| official substitutions | 139 | 0 | — | — | 3 | 0 |
| **combined** | **142** | **0** | — | — | 0 | 0 |

**Runs starting at a period start: 17**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 12 | 0 | 0 | 0 | — | 5 |
| official substitutions | 14 | 0 | — | — | 1 | 2 |
| **combined** | **17** | **0** | — | — | 0 | 0 |

Overall: 159 of 159 runs decided (100%) — ramirobentes right in 159, BigDataBall right in 0; 0 with conflicting evidence, 0 undetermined.

## 2014-15

| measure | value |
|---|---|
| BigDataBall game files | 1,311 |
| … found in core.games | 1,311 |
| … not in core.games | 0 |
| final score differs | 0 |
| BigDataBall events | 600,602 |
| … same event number in our events | 600,584 (100.00%) |
| … and same period + clock (aligned) | 600,574 (100.00%) |
| aligned events with identical home **and** away lineups | 557,871 (92.89%) |
| aligned team-lineups identical | 1,158,278 / 1,201,148 (96.43%) |
| BigDataBall names | 492 |
| … mapped by name | 480 |
| … mapped by lineup | 8 |
| … unmatched (listed below) | 4 |

Where the lineups differ:

| players different | team-lineups |
|---|---|
| 0 | 114 |
| 1 | 42,714 |
| 2 | 42 |

Differences come in runs: 591 runs; the event where a run starts:

| event type | runs |
|---|---|
| substitution | 414 |
| period_start | 177 |

Reading: almost every difference is **one** player, persisting from a substitution or
a period start until the next substitution — the two sources reconstruct some lineups
differently (typically substitutions not logged between periods). Neither source is
the ground truth; which one is right needs a third source (e.g. box-score minutes
or video). Unmatched names below also count as disagreement.

Games with the lowest lineup agreement:

| game_id | team-lineups identical |
|---|---|
| 0021400350 | 53.70% |
| 0021401090 | 55.98% |
| 0021401071 | 56.02% |
| 0021400020 | 57.00% |
| 0021400450 | 57.73% |
| 0041400203 | 57.92% |
| 0021401147 | 58.69% |
| 0021401157 | 58.89% |
| 0021400036 | 59.08% |
| 0021400982 | 59.85% |

Unmatched BigDataBall names (not guessed):

| name | votes by candidate ID (`ambiguous` = not a single leftover) |
|---|---|
| Enes Kanter | {202683: 19427, 'ambiguous': 110} |
| Glen Rice Jr. | {'ambiguous': 368, 203318: 59} |
| Otto Porter | {203490: 16626, 'ambiguous': 368} |
| Perry Jones | {203103: 6032, 'ambiguous': 110} |

An unmatched name can be added by hand as a `manual` row in `core.player_xref` after
checking it; the candidate IDs above are evidence, not decisions.

### Arbitration of lineup disagreements (2014-15)

Report only. Evidence: box-score minutes (nba_api) and official play-by-play substitutions
(shufinskiy `nbastats_*`); rules in `src/nba_platform/validate/bdb_arbitration.py`. Each verdict is an
**inference** from that evidence.

Disagreement runs (our event order): 216.

**Runs starting at a substitution: 186**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 184 | 0 | 0 | 0 | — | 2 |
| official substitutions | 180 | 0 | — | — | 6 | 0 |
| **combined** | **186** | **0** | — | — | 0 | 0 |

**Runs starting at a period start: 30**

| evidence | ramirobentes right | BigDataBall right | leans ramirobentes | leans BigDataBall | conflicting | undetermined / none |
|---|---|---|---|---|---|---|
| box-score minutes | 25 | 0 | 0 | 0 | — | 5 |
| official substitutions | 21 | 0 | — | — | 1 | 8 |
| **combined** | **29** | **0** | — | — | 0 | 1 |

Overall: 215 of 216 runs decided (100%) — ramirobentes right in 215, BigDataBall right in 0; 0 with conflicting evidence, 1 undetermined.

