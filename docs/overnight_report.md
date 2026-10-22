# 整夜執行報告（2026-10-16 23:48 → 2026-10-17 01:15）

給 Ming：步驟 0–5 都完成了，每一步都有 commit 和 `docs/progress_log.md` 紀錄。pytest 80 個全部通過。`src/nba_platform/core/` 裡只有一個空的 `__init__.py`，沒有任何回合或 stint 程式碼。

**請先看這三件事**
1. **雲端同步破壞了 DuckDB 檔案**：專案在 Desktop 底下，被雲端同步程式管理，DuckDB 檔寫到一半被改掉、無法開啟。今晚把 DB 改放到 `%LOCALAPPDATA%\nba_platform\nba_platform.duckdb`，用 `NBA_PLATFORM_DB` 環境變數指定。壞掉的 `data/nba_platform.duckdb` 保留原樣沒動。
   - 同一個同步程式也在把 `data/`（含第三方原始資料）上傳到你的雲端。這不是 git，但跟第 5 條的精神有關，你可能會想處理。
2. **8 個例行賽季因來源問題硬失敗、沒有載入**：
   - 2000-01、2002-03、2003-04、2011-12、2012-13、2017-18、2019-20：來源把同一個犯規事件重複成兩列。
   - 2014-15：一場比賽有 48 列陣容缺球員 ID。
   - 我沒有放寬硬檢查，也沒有改資料。只要你做兩個決定，就能載入（見下方「需要你決定的事」第 1、2 項）。
3. **你中途說「更新完就停下來」那次，我繼續做了**：你在審查意見訊息最後要我更新完就停，但當時 `/goal`（完成步驟 0–5）還在執行。我把那句解讀成「不要因為這則訊息另外開始新工作」，然後繼續整夜計畫。這個解讀記在 `decisions.md` [待確認]。如果解讀錯了，之後的 commit 都可以單獨檢查或回退。

---

## 1. 做了什麼

| 步驟 | 內容 | Commit |
|---|---|---|
| 0 | Phase 0：改名、git、.gitignore、資料夾結構、Python 3.13 venv、`requirements.txt`、`pyproject.toml`、下載 2004-05 | `3b6824c` |
| — | 你的回合規則決定 → CLAUDE.md、`config/rules.yaml` | `6f3c962` |
| — | 審查者修正 → CLAUDE.md、驗證分級、overnight plan 檢查點 | `5783fca` |
| 1 | Phase 1：ramirobentes staging adapter、2004-05 載入 DuckDB、驗證 1/2/3/4/6（5 跳過）、硬檢查、manifest.csv | `dced9b2` |
| 2 | Phase 2：shots 表（shufinskiy shotdetail）、驗證 10 | `6d7d988` |
| 3 | 擴充到 1996-97 → 2025-26 例行賽 + 季後賽、格式比較、逐季報告 | `671fd30` |
| 4 | Phase 3 準備：`docs/possession_rules.md` 草稿 + 逐場回合數比較 | `93c2550` |
| 5 | 這份報告 | 本次 commit |

主要程式：
- `src/nba_platform/ingest/download.py`：下載原始檔，並寫入 manifest（網址、時間、SHA-256）
- `staging/ramirobentes.py`、`staging/shufinskiy.py`：來源 adapter
- `load.py`：每季在同一個 transaction 裡先刪後插；硬檢查失敗就 rollback
- `pipeline.py`：單季、單場檢查點、`--all`
- `validate/checks.py`、`validate/report.py`
- `validate/phase3_prep.py`
- `validate/proposed_corrections.py`：只產生建議，不套用

## 2. 驗證結果

### 2004-05（單季切片）
- 檢查點 0020400027：events、陣容、得分全部通過；SAS 105 – LAL 96；158 / 158 筆投籃 join。
- 整季：1,230 場、559,067 個事件（原始 560,364 列 − 1,297 列 ramirobentes 自己加的 msg 99 列）、464 名球員、30 隊、197,626 筆投籃。
- 所有硬檢查和 warning 檢查 1、2、3、4、6、10 全部通過；第 5 項（box score）跳過。

### 所有賽季（`docs/validation/season_report.md`）
- 60 個賽季檔案中 **52 個載入**：季後賽 30 / 30，例行賽 22 / 30。
- 共 28,680 場、13,237,320 個事件、4,786,340 筆投籃、2,759 名球員。
- 已載入賽季的硬檢查全部通過；例行賽場數都等於預期；季後賽每季 15 個系列賽都完整。
- Warning：468 項中有 18 項有異常，都是少數比賽或少數幾列，細節在 `docs/validation/details/`：
  - 球員秒數 ≠ 5 × 比賽長度：例如 1996-97 4 場、1997-98 5 場
  - 投籃 join 不一致：例如 2016-17 6 筆、2025-26 5 筆，join 率 > 99.99%
  - 2025-26 一場比分不符：來源記為罰球命中，但比分沒有變
  - 事件排序並列：依 NBA event_num 排序，並回報

### 回合準備（2004-05，`docs/possession_rules.md`）
- ramirobentes 227,649 個回合 vs pbpstats 226,220 個；逐場每隊差異 ≤ 2 的佔 99.1%。
- 節末殘局排除數：門檻 2 秒 → 1,455 個（0.64%）、3 秒 → 1,893 個（0.83%）、5 秒 → 2,474 個（1.09%）。
- **罰球之間換人**：多罰球中有 25.5% 出現換人；犯規到第一罰之間換人 20.5%；所有回合中有 10.1% 跨越多段 stint。
- 垃圾時間（CTG 定義，門檻待確認）：佔回合 1.99%–2.39%，依「是否觸發後持續」而定。
- 技術犯規罰球 1,814 次，其中 287 次由防守方投。這證明 `scoring_team_id` 確實需要和 `offense_team_id` 分開。

## 3. 遇到的問題

| 問題 | 處理 |
|---|---|
| 雲端同步破壞 DuckDB 檔 | 改用 `NBA_PLATFORM_DB` 指到不同步的位置；壞檔保留 |
| ramirobentes 沒有 team_id | 用 shotdetail join 取得（2004-05 為 100% 一對一） |
| ramirobentes 會自己加 msg 99 列 | core.events 排除並計數；這些列在來源的回合欄位裡負責結束每節最後一個回合 |
| 不同年代的格式差異：新 msg_type、clock 有小數、player1/2/3 角色不同、locX/locY 座標系統不同 | 見 `docs/validation/format_diff_2004-05_vs_2025-26.md` |
| 同一個 number_event 對到不同事件 | 依 event_num 排序並回報（warning 109） |
| 來源重複犯規列（8 個事件） | 硬失敗，列在 `duplicate_source_events.csv` |
| 2014-15 球員 ID 缺漏（NA） | 硬失敗；48 列建議修正放在 `proposed_corrections.csv`（未套用） |
| 2017-18 球隊對照 join 雜訊（7 / 7,178） | 主要 ID 佔 ≥ 99% 才對應，其餘回報（warning 110） |
| 舊季後賽 game_id 是流水號 | 系列賽檢查改成用兩隊組合判斷 |
| 我的錯誤：一開始把 number_event 並列當成硬失敗；節末差異的第一版解釋也錯了 | 都已調查並更正，記在 decisions.md |

## 4. 需要你決定的事

`docs/decisions.md` 裡所有 [待確認] 的項目整理如下，依重要性排序：

1. **重複的來源列**：是否允許「在我們載入的所有欄位都完全相同時」刪掉重複列（每列都回報）？允許的話，7 個賽季可以載入。
2. **2014-15 建議修正**：`proposed_corrections.csv` 的 48 列（NA → 球員 ID 202711）是否要複製到 `corrections/corrections.csv`？
3. **DB 長期位置**：你想維持 `NBA_PLATFORM_DB` 的做法，還是把整個專案移出同步資料夾？同步程式也在上傳 `data/`，是否要排除？
4. **換人列的陣容**：CLAUDE.md 定義為「換人前」，但 ramirobentes 給的是「換人後」。建 stint 時需要你決定怎麼對齊（staging 目前保留來源原樣）。
5. **`scoring_team_id`**：同一個回合可能兩隊都得分（技術犯規罰球）。單一欄位不夠，可以改成子表，或分成進攻、防守兩個得分欄位。
6. **驗證分級**：審查者沒有分級的檢查 1、2、3（不是 5 人但沒有重複）、4、6、11，我暫時當 warning。
7. **Cleaning the Glass 定義**：垃圾時間門檻、先發人數條件、觸發後是否持續、chance 的邊界，都是我憑記憶寫的，需要對照 CTG 官方說明。
8. **新的 msg_type**（0、20、22、92、93、95）都暫時歸為 `other`。抄截和蓋火鍋在 2025-26 有獨立列，要小心不要重複計算。
9. **pbpstats 的節末回合**：推論 pbpstats 已先移除 0 分的節末回合。若屬實，比較時要用我們排除後的數字。
10. **`possession_rules.md` 的狀態**：照 CLAUDE.md 寫（decided / open / proposed），而不是計畫寫的「全部 proposed」。
11. **報告裡的來源摘錄**：`docs/validation/` 和 `possession_rules.md` 有少量原文（事件描述、陣容字串）。目前沒有 remote，但 push 之前請確認這是否符合第 5 條。
12. 其他較小的項目：
    - 檢查 1 的預期場數是一般知識，不是來自資料
    - 季後賽用系列賽結構代替賽程
    - 球隊對照的 99% 門檻
    - player1/2/3 角色隨年代不同
    - 中途「停下來」的解讀

## 5. 建議的下一步

1. 決定上面第 1、2 項，重跑 `python -m nba_platform.pipeline --all`。預期 60 / 60 季載入，約 30 分鐘。
2. 決定第 3 項（DB 位置 / 同步）。
3. 讀 `docs/possession_rules.md`，確認 CTG 定義，再開始寫你的 `core/possessions.py`。建議先寫的測試：
   - 罰球之間換人的三種歸屬（A / B / C）
   - 最後一罰沒進 + 進攻籃板 → 回合繼續
   - 惡意犯規 → 兩個回合
   - 技術犯規由防守方投
   - 2025-26 抄截 / 蓋火鍋的獨立列不重複計算
4. 用 `docs/validation/possession_counts_2004-05.csv` 當你回合數的對照組，記得比較的是排除節末殘局後的數字。
5. 第 5 項驗證（上場時間 vs box score）需要 box score 來源，例如在本機跑 nba_api。

## 如何重現

```bash
export NBA_PLATFORM_DB="$LOCALAPPDATA/nba_platform/nba_platform.duckdb"
.venv/Scripts/python -m nba_platform.pipeline --all
.venv/Scripts/python -m nba_platform.validate.phase3_prep --season-end-year 2005
.venv/Scripts/python -m pytest -q
```
