# On/off under two ways to credit a substitution during a possession

**B = `pbpstats_hybrid`** (what the marts use): free-throw points go to the lineup on the floor at the foul.
**A = `end_lineup`**: every point of a possession goes to the lineup on the floor when it ends.
Possession counts are the same under both (a possession always goes to the lineup at its end); only free-throw points
whose foul and possession end fall in different stints move. Option C (chance split) is not computed. Numbers only.

Free-throw points that move between lineups: **548,053** of 7,723,936 possession points (7.10 %).

Reading: substitutions are usually made in the dead ball after a foul, before the free throws, so under A the players who
enter are credited with free throws earned while the players they replaced were on the floor; under B they are not.

## Change in a player's net on-off (A minus B), players with at least 1,000 offensive possessions on the floor

| season | type | players | mean abs change | 95th percentile | max | players changing by more than 1 point |
|---|---|---|---|---|---|---|
| 1996-97 | regular | 317 | 1.115 | 3.071 | 6.17 | 138 |
| 1997-98 | regular | 320 | 1.274 | 3.360 | 10.49 | 150 |
| 1998-99 | regular | 261 | 1.422 | 3.650 | 7.47 | 135 |
| 1999-00 | regular | 313 | 1.149 | 3.054 | 5.70 | 138 |
| 2000-01 | regular | 324 | 1.203 | 3.153 | 7.22 | 152 |
| 2001-02 | regular | 328 | 1.163 | 3.059 | 6.64 | 153 |
| 2002-03 | regular | 316 | 1.136 | 2.838 | 6.41 | 143 |
| 2003-04 | regular | 329 | 1.078 | 2.869 | 6.11 | 147 |
| 2004-05 | regular | 345 | 1.206 | 3.259 | 5.59 | 162 |
| 2005-06 | regular | 335 | 1.181 | 3.101 | 6.95 | 157 |
| 2006-07 | regular | 340 | 1.233 | 3.253 | 6.06 | 158 |
| 2007-08 | regular | 328 | 0.991 | 2.627 | 5.83 | 133 |
| 2008-09 | regular | 338 | 1.185 | 2.719 | 4.72 | 176 |
| 2009-10 | regular | 338 | 1.052 | 2.913 | 6.34 | 137 |
| 2010-11 | regular | 349 | 1.024 | 2.756 | 4.19 | 153 |
| 2011-12 | regular | 327 | 1.060 | 2.874 | 4.23 | 138 |
| 2012-13 | regular | 345 | 1.023 | 2.816 | 4.97 | 135 |
| 2013-14 | regular | 342 | 0.982 | 2.306 | 7.46 | 144 |
| 2014-15 | regular | 386 | 1.120 | 3.190 | 5.78 | 160 |
| 2015-16 | regular | 354 | 1.153 | 3.254 | 7.46 | 150 |
| 2016-17 | regular | 360 | 1.139 | 2.892 | 6.62 | 172 |
| 2017-18 | regular | 366 | 0.949 | 2.430 | 6.13 | 148 |
| 2018-19 | regular | 388 | 0.899 | 2.371 | 4.59 | 140 |
| 2019-20 | regular | 352 | 1.084 | 2.811 | 6.42 | 151 |
| 2020-21 | regular | 369 | 1.058 | 2.673 | 6.10 | 163 |
| 2021-22 | regular | 387 | 0.989 | 2.582 | 3.87 | 154 |
| 2022-23 | regular | 386 | 1.069 | 2.881 | 6.31 | 156 |
| 2023-24 | regular | 375 | 1.099 | 2.977 | 6.38 | 164 |
| 2024-25 | regular | 392 | 1.048 | 2.797 | 6.11 | 164 |
| 2025-26 | regular | 395 | 1.246 | 3.475 | 7.60 | 191 |
| 1996-97 | playoffs | 14 | 3.301 | 6.623 | 8.99 | 11 |
| 1997-98 | playoffs | 10 | 4.566 | 10.508 | 10.53 | 7 |
| 1998-99 | playoffs | 7 | 2.591 | 5.268 | 5.69 | 6 |
| 1999-00 | playoffs | 15 | 2.380 | 5.414 | 9.37 | 11 |
| 2000-01 | playoffs | 13 | 3.340 | 6.432 | 7.47 | 11 |
| 2001-02 | playoffs | 16 | 3.289 | 10.223 | 10.30 | 13 |
| 2002-03 | playoffs | 20 | 2.605 | 5.707 | 8.84 | 15 |
| 2003-04 | playoffs | 14 | 3.256 | 6.766 | 6.87 | 11 |
| 2004-05 | playoffs | 19 | 3.155 | 7.117 | 7.74 | 14 |
| 2005-06 | playoffs | 25 | 2.640 | 5.845 | 9.49 | 16 |
| 2006-07 | playoffs | 18 | 2.787 | 6.724 | 7.78 | 13 |
| 2007-08 | playoffs | 17 | 2.377 | 6.067 | 10.28 | 11 |
| 2008-09 | playoffs | 20 | 3.629 | 7.635 | 7.77 | 17 |
| 2009-10 | playoffs | 14 | 2.288 | 5.563 | 6.64 | 7 |
| 2010-11 | playoffs | 14 | 2.543 | 6.247 | 7.97 | 9 |
| 2011-12 | playoffs | 13 | 2.686 | 7.181 | 7.68 | 9 |
| 2012-13 | playoffs | 17 | 2.772 | 4.981 | 5.02 | 15 |
| 2013-14 | playoffs | 18 | 1.748 | 3.803 | 6.07 | 10 |
| 2014-15 | playoffs | 20 | 3.311 | 7.650 | 7.79 | 17 |
| 2015-16 | playoffs | 19 | 2.077 | 3.898 | 3.97 | 16 |
| 2016-17 | playoffs | 16 | 2.037 | 4.085 | 4.26 | 11 |
| 2017-18 | playoffs | 20 | 1.793 | 3.727 | 4.68 | 12 |
| 2018-19 | playoffs | 16 | 2.822 | 8.389 | 9.50 | 12 |
| 2019-20 | playoffs | 20 | 3.282 | 7.009 | 10.26 | 15 |
| 2020-21 | playoffs | 20 | 2.598 | 5.808 | 7.43 | 14 |
| 2021-22 | playoffs | 18 | 2.981 | 5.875 | 6.65 | 15 |
| 2022-23 | playoffs | 21 | 2.371 | 5.376 | 5.88 | 14 |
| 2023-24 | playoffs | 18 | 3.020 | 6.501 | 7.50 | 15 |
| 2024-25 | playoffs | 22 | 3.942 | 7.775 | 8.75 | 18 |
| 2025-26 | playoffs | 17 | 2.253 | 4.753 | 6.16 | 12 |

## Largest changes

Playoff rows have small off-the-floor samples, which magnifies any change.

| season | type | team | player | on-off under B | under A | change | free-throw points moved (on floor) |
|---|---|---|---|---|---|---|---|
| 1997-98 | playoffs | CHI | Toni Kukoc | +11.85 | +1.31 | -10.53 | 45 |
| 1997-98 | regular | WAS | Darvin Ham | -0.13 | +10.36 | +10.49 | 114 |
| 1997-98 | playoffs | CHI | Ron Harper | -11.68 | -1.21 | +10.48 | 47 |
| 2001-02 | playoffs | BOS | Paul Pierce | +15.65 | +5.35 | -10.30 | 17 |
| 2007-08 | playoffs | DET | Richard Hamilton | +14.29 | +4.01 | -10.28 | 24 |
| 2019-20 | playoffs | DEN | Nikola Jokić | +4.69 | -5.57 | -10.26 | 35 |
| 2001-02 | playoffs | LAL | Kobe Bryant | -2.64 | +7.55 | +10.20 | 15 |
| 2018-19 | playoffs | DEN | Nikola Jokić | +23.26 | +13.76 | -9.50 | 21 |
| 2005-06 | playoffs | LAC | Elton Brand | +6.14 | -3.36 | -9.49 | 16 |
| 1999-00 | playoffs | LAL | Shaquille O'Neal | +30.75 | +21.39 | -9.37 | 31 |
| 1996-97 | playoffs | CHI | Michael Jordan | +26.62 | +17.63 | -8.99 | 27 |
| 2002-03 | playoffs | DAL | Michael Finley | -6.25 | -15.09 | -8.84 | 22 |
| 2024-25 | playoffs | NYK | OG Anunoby | -11.14 | -2.39 | +8.75 | 23 |
| 1997-98 | regular | WAS | Tracy Murray | +4.02 | -4.23 | -8.25 | 156 |
| 2018-19 | playoffs | MIL | Khris Middleton | +8.22 | +0.20 | -8.02 | 26 |

## Free-throw points moved per season

| season | type | free throws made in possessions | points moved |
|---|---|---|---|
| 1996-97 | regular | 43,114 | 16,312 |
| 1997-98 | regular | 44,660 | 18,137 |
| 1998-99 | regular | 26,512 | 10,927 |
| 1999-00 | regular | 43,778 | 17,957 |
| 2000-01 | regular | 42,597 | 16,780 |
| 2001-02 | regular | 40,927 | 16,202 |
| 2002-03 | regular | 42,379 | 16,656 |
| 2003-04 | regular | 41,878 | 16,643 |
| 2004-05 | regular | 46,995 | 19,808 |
| 2005-06 | regular | 46,704 | 19,405 |
| 2006-07 | regular | 46,504 | 19,709 |
| 2007-08 | regular | 44,952 | 18,574 |
| 2008-09 | regular | 45,422 | 18,407 |
| 2009-10 | regular | 44,432 | 18,077 |
| 2010-11 | regular | 44,152 | 18,283 |
| 2011-12 | regular | 32,385 | 13,255 |
| 2012-13 | regular | 39,891 | 16,379 |
| 2013-14 | regular | 42,670 | 17,016 |
| 2014-15 | regular | 41,217 | 17,327 |
| 2015-16 | regular | 42,325 | 17,651 |
| 2016-17 | regular | 42,765 | 17,562 |
| 2017-18 | regular | 39,841 | 15,816 |
| 2018-19 | regular | 42,330 | 16,780 |
| 2019-20 | regular | 36,859 | 14,872 |
| 2020-21 | regular | 35,771 | 14,178 |
| 2021-22 | regular | 40,471 | 16,275 |
| 2022-23 | regular | 44,084 | 17,669 |
| 2023-24 | regular | 40,687 | 16,604 |
| 2024-25 | regular | 40,689 | 16,706 |
| 2025-26 | regular | 44,330 | 19,338 |
| 1996-97 | playoffs | 2,793 | 1,110 |
| 1997-98 | playoffs | 2,712 | 1,151 |
| 1998-99 | playoffs | 2,525 | 1,040 |
| 1999-00 | playoffs | 2,837 | 1,155 |
| 2000-01 | playoffs | 2,679 | 1,114 |
| 2001-02 | playoffs | 2,714 | 1,130 |
| 2002-03 | playoffs | 3,499 | 1,499 |
| 2003-04 | playoffs | 2,870 | 1,242 |
| 2004-05 | playoffs | 3,239 | 1,489 |
| 2005-06 | playoffs | 3,584 | 1,561 |
| 2006-07 | playoffs | 2,968 | 1,299 |
| 2007-08 | playoffs | 3,307 | 1,341 |
| 2008-09 | playoffs | 3,289 | 1,369 |
| 2009-10 | playoffs | 3,264 | 1,363 |
| 2010-11 | playoffs | 3,137 | 1,383 |
| 2011-12 | playoffs | 2,917 | 1,282 |
| 2012-13 | playoffs | 2,959 | 1,355 |
| 2013-14 | playoffs | 3,268 | 1,421 |
| 2014-15 | playoffs | 2,884 | 1,357 |
| 2015-16 | playoffs | 2,975 | 1,258 |
| 2016-17 | playoffs | 2,855 | 1,212 |
| 2017-18 | playoffs | 2,772 | 1,219 |
| 2018-19 | playoffs | 3,118 | 1,264 |
| 2019-20 | playoffs | 3,065 | 1,393 |
| 2020-21 | playoffs | 2,917 | 1,188 |
| 2021-22 | playoffs | 3,025 | 1,317 |
| 2022-23 | playoffs | 2,844 | 1,183 |
| 2023-24 | playoffs | 2,546 | 1,137 |
| 2024-25 | playoffs | 3,024 | 1,387 |
| 2025-26 | playoffs | 3,189 | 1,529 |
