# 回合程式實作指南（2026-10-21）

> **更新（2026-10-21）**：約定 1 已改成 Claude 撰寫 `core/`、Ming 決定規則並審查（CLAUDE.md）。下面的順序和檢查照舊適用；stint 規則改為「同一秒連續換人合併、每節開新 stint」（CLAUDE.md「lineups on court」）。

這份文件只寫「做什麼、照什麼順序、怎麼驗證」，**不包含任何回合邏輯**；邏輯由你寫在
`src/nba_platform/core/`（CLAUDE.md 約定 1）。規則的唯一來源是 CLAUDE.md「Possession
rules」和 `config/rules.yaml`（`rules_version: 2026-10-21.1`），這份指南如果和它們不同，以它們為準。

## 0. 先決定的範圍

- **只做 2004-05 例行賽**（約定 3）。先跑通一場：`0020400027`（SAS @ LAL，105–96），再做整季。
- **只做 `pbpstats_compat` 設定檔**，先和 `reference.pbpstats_possessions` 對到大多數比賽一致，之後才做 `custom`（「先照抄、再偏離」）。
- 程式寫成**純函式**：DataFrame 進、DataFrame 出，不碰資料庫。寫入 DuckDB 由 pipeline 負責（只有 pipeline 寫資料庫），這部分我可以幫你接。

## 1. 輸入

| 來源 | 你會用到的欄位 | 備註 |
|---|---|---|
| `core.events` | `game_id, event_seq, source_event_num, period, secs_elapsed_game, team_id, event_type, event_subtype, source_msg_type, player1_id, player2_id, player3_id, points, home_score, away_score` | 依 `event_seq` 排序就是來源順序（決定：不在程式裡重排） |
| `staging.event_lineups` | `game_id, event_seq, home_player_ids, away_player_ids` | 每個事件的場上 10 人；換人列是**換人後**的陣容 |
| `core.games` | `home_team_id, away_team_id, num_periods, home_score, away_score` | 主客隊、節數 |
| `load_rules(profile="pbpstats_compat")` | 全部門檻與定義 | 不要在程式裡寫死任何數字 |

`event_type` 是我們自己的詞彙：`shot_made, shot_missed, free_throw, rebound, turnover, foul, substitution, timeout, jump_ball, violation, period_start, period_end, other`。
`other` 一律忽略（包括 2025-26 的 msg 95 / 92 / 22 / 93 / 0 / 20，決定 2026-10-21）。

## 2. 輸出（欄位照 CLAUDE.md「Core schema」）

- **events 新增欄位**：`stint_id`、`possession_id`、`chance_id`、`foul_event_seq`、`is_technical_ft`、`is_between_possessions_ft`（schema 已經有這些欄位，現在都是 NULL）。
- **`core.stints`**：`game_id, stint_id, start_secs, end_secs, home_p1..p5, away_p1..p5`。
- **`core.possessions`**：`game_id, possession_id, offense_team_id, defense_team_id, start_secs, end_secs, start_type, end_type, points, num_chances, rules_version, period, secs_remaining_period_at_start, secs_remaining_game_at_start, start_margin_offense, offense_is_home, is_end_of_period_heave, is_garbage_time, is_after_timeout`，以及決定中提到的「叫暫停的球隊」`timeout_team_id`（已確認 2026-10-21；官方暫停或沒有暫停時為 NULL）。
- **`core.possession_stint_segments`**：`game_id, possession_id, segment_seq, stint_id, start_event_seq, end_event_seq, start_secs, end_secs`。

## 3. 建議的函式切分與實作順序

每一步都先讓對應的測試通過，再做下一步。函式名稱只是建議。

| 步驟 | 建議函式（`core/`） | 做什麼 | 對應測試（`tests/test_possession_rules.py` 的 fixture） |
|---|---|---|---|
| 1 | `stints.build_stints(events, lineups)` | 每次換人開新 stint（決定：換人列算換人後）；回傳 stints 表 + 每個事件的 `stint_id` | 新增：stint 的 10 人等於該事件的陣容；每次 substitution 都換 stint |
| 2 | `possessions.link_free_throws(events)` | 每個罰球找到造成它的犯規 → `foul_event_seq`；標記 `is_technical_ft`、`is_between_possessions_ft` | `technical_free_throw`、`substitution_between_free_throws` |
| 3 | `possessions.classify_rebounds(events)` | 進攻 / 防守籃板；**忽略**非最後一罰後的球隊籃板 | `team_rebound_after_non_final_ft`、`missed_final_free_throw`、`offensive_rebound` |
| 4 | `possessions.possession_ending(events, rules)` | 每個事件是否結束回合：投進（and-1 在罰球後）、防守籃板、失誤、最後一罰投進、節末；跳球看下一個有球隊的事件 | `jump_ball`、`flagrant_foul`、`missed_final_free_throw` |
| 5 | `possessions.assign_possessions(events, rules)` | 依步驟 4 編 `possession_id`、`chance_id`（只有進攻籃板開新 chance）；技術犯規罰球和 between-possessions 罰球不開始也不結束回合 | `offensive_rebound`、`technical_free_throw` |
| 6 | `possessions.summarize(events, games, rules)` | 一個回合一列：起訖、`start_type`（6 種）、`points`（不含技術罰球）、`num_chances`、情境欄位、旗標 | `start_type`、`end_of_period`、`garbage_time` |
| 7 | `possessions.stint_segments(events)` | 一個回合跨幾個 stint 就切幾段 | `substitution_between_free_throws` |

## 4. 各步驟要自己檢查的數字（這些我可以寫成驗證，不寫邏輯）

- 每個事件剛好屬於 0 或 1 個回合；技術犯規罰球和 between-possessions 罰球屬於 0 個。
- **得分守恆**：每隊 `sum(possessions.points)` + 技術罰球得分 + between-possessions 罰球得分 = 終場比分（檢查 2 的延伸）。
- 同一場兩隊回合數差 ≤ 2（檢查 7，warning）。
- 和 `reference.pbpstats_possessions` 逐場比對每隊回合數（檢查 8）；`reference.possession_count_benchmark` 現在是 ramirobentes vs pbpstats，可以當作「別人做到幾 %」的參考：2004-05 例行賽 98.9 % 的 team-game 完全一致、其餘差 1（`docs/validation/possession_benchmark.md`）。
- 回合跨 stint 時，segments 的時間加總 = 回合時間。

## 5. 已知會出問題的地方（資料面）

- **球員欄位的角色依時代不同**：跳球（2004-05 player3 = 拿到球的人，2025-26 player1）、阻攻（player3 → player2）、抄截（2016-17 → 2024-25 在 player3）。回合程式**不要依賴 player 欄位判斷球權**，用 `team_id` 和事件順序。
- **同一秒的多個事件**：罰球、換人、犯規、暫停常常在同一個 `secs_elapsed_game`。照 `event_seq` 走；發現順序錯誤先記下 game_id / event_seq，確認後加 correction，不要寫重排規則。
- **and-1**：投進後同一秒的 1 of 1 罰球屬於同一個回合，回合在罰球後結束。
- **惡意犯規**：罰球一個回合，保留球權後再一個回合（決定）。
- **節末**：`period_end` 一定結束回合；開始時剩 ≤ 2 秒且 0 分 → `is_end_of_period_heave`。
- **between-possessions 罰球**：目前已知 2 筆（`0020400278` event 200、`0022400105` event 501）。pbpstats 在這種情況（最後一罰投進後、同一秒對手又犯規）**不讓最後一罰結束回合**，我們的決定不同，比對時這幾場可能差 1，屬於規則差異，記錄就好。
- **球隊失誤 / 球隊籃板**：`player1_id` 是 NULL，但 `team_id` 有值，照樣結束回合（防守籃板、失誤）。

## 6. 你寫好之後我會做的事

1. 審查程式：找邊界情況、建議補的測試（不改你的邏輯）。
2. 接 pipeline：把你的函式輸出寫進 DuckDB（`core.stints`、`core.possessions`、`core.possession_stint_segments`、events 欄位）。
3. 寫檢查 7、8 的報告：逐場和 pbpstats 比對，列出不一致的比賽給你調查。
4. 之後建第二層的 marts（on/off、陣容、四因素）和頁面。

## 7. 還沒決定、但寫程式時不需要先決定的事

- `custom` 的換人計分方式（A / B / C）：資料設計已經能算三種，先不決定（2026-10-21）。
- chance 是否增加進攻籃板以外的邊界：要先對照 CTG 公開的定義。
