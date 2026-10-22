# 進度紀錄

## Step 0 — Phase 0 完成（2026-10-16）

**做了什麼**
- 專案改名：CLAUDE.md 中 5 處 `courtbase` → `nba-analytics-platform` / `src/nba_platform/` / `data/nba_platform.duckdb`（規則內容未動）。
- `git init`（分支 `main`），`.gitignore` 排除 `data/`、`*.duckdb`、`.venv/` 等；用 `git check-ignore` 確認 `data/` 下檔案被忽略。
- 照 CLAUDE.md Directory layout 建資料夾；`src/nba_platform/` 為 src layout 套件，`core/` 只有空 `__init__.py`。
- Python 3.13 虛擬環境 `.venv`；`requirements.txt` 固定 pandas 3.0.6、pyarrow 26.0.0、duckdb 1.5.6、pytest 9.1.1；最小 `pyproject.toml`（`pip install -e .`）。
- `src/nba_platform/ingest/download.py`：下載單季原始檔，已存在就跳過、先寫 `.part` 再改名。

**新增/修改的檔案**
`.gitignore`, `pyproject.toml`, `requirements.txt`, `README.md`, `CLAUDE.md`（改名）, `docs/decisions.md`, `docs/possession_rules.md`（佔位）, `docs/progress_log.md`, `docs/overnight_plan.md`, `src/nba_platform/**/__init__.py`, `src/nba_platform/ingest/download.py`, `tests/test_smoke.py`

**驗證數字**
| 檔案 | 大小 | 列數 | 欄數 |
|---|---|---|---|
| ramirobentes `pbp_regular_2005.parquet` | 10.7 MB | 560,364 | 61 |
| shufinskiy `shotdetail_2004.tar.xz`（內含 1 個 CSV） | 2.4 MB | 197,626 | 24 |
| shufinskiy `pbpstats_2004.tar.xz`（內含 1 個 CSV） | 5.9 MB | 478,748 | 19 |

- pytest：1 passed。

**遇到的問題**
- 無。附註：pbpstats_2004 有 478,748 列，約為一季回合數（~23 萬）的 2 倍，可能每列不是一個回合，Step 4 會查清楚。
- 已先查好季後賽命名：ramirobentes `pbp_playoffs_{結束年}.parquet`（1997–2026）；shufinskiy `shotdetail_po_{開始年}`、`pbpstats_po_{開始年}`。

**下一步**：Step 1 — ramirobentes staging adapter + 2004-05 載入 DuckDB + 驗證 1、2、3、4、6。

**預估剩餘時間**：約 4–6 小時。

## Step 1 — Phase 1 完成：2004-05 ramirobentes → DuckDB（2026-10-17 00:02）

**做了什麼**
- 先跑檢查點：只用比賽 0020400027（SAS @ LAL）跑 staging → 載入（in-memory DB）→ 驗證，全部通過；比分 SAS 105 – LAL 96，與 CLAUDE.md 記錄相同。之後才跑整季。
- `staging/ramirobentes.py`：解析 `"ID Name"`、陣容字串、clock → 秒數、msg_type → 我們的事件類型；無法對應就 `StagingError`（硬失敗）。msg_type 99（ramirobentes 自己加的「Last possession of quarter」列）排除並計數。
- `staging/shufinskiy.py`：串流讀 `.tar.xz` 內的 CSV，GAME_ID 補零。
- team_id：ramirobentes 只有隊名縮寫，用 shotdetail 的 join（game_id + event_num）取得 NBA team_id，存在 `core.team_xref`。
- `sql/schema.sql`、`db.py`、`load.py`（每季先刪後插，同一個 transaction；硬檢查在 commit 前執行，失敗就 rollback）、`pipeline.py`（CLI）。
- `validate/checks.py`：依審查者意見分 hard / warning 兩級；`validate/report.py` 寫 `docs/validation/`。
- `ingest/download.py`：新增 `data/raw/manifest.csv`（網址、時間、SHA-256）；`.gitignore` 改成只追蹤 manifest。
- 測試：58 個（staging 解析、錯誤路徑、corrections、載入冪等、每個檢查的正反例、季後賽系列賽檢查、manifest、真實 DB 的唯讀整合測試）。

**新增/修改的檔案**
`src/nba_platform/{seasons,db,load,pipeline}.py`, `src/nba_platform/staging/{ramirobentes,shufinskiy}.py`, `src/nba_platform/validate/{checks,report}.py`, `src/nba_platform/ingest/download.py`, `sql/schema.sql`, `corrections/corrections.csv`, `.gitignore`, `data/raw/manifest.csv`, `docs/validation/season_report.md`, `docs/validation/details/regular_2005.md`, `docs/decisions.md`, `tests/*`

**驗證數字（2004-05 例行賽）**
| 檢查 | 等級 | 結果 |
|---|---|---|
| 9 ID 可對應 | hard | ✅ 464 名球員、30 隊 |
| 102 事件唯一鍵 | hard | ✅ |
| 104 陣容無重複球員 | hard | ✅ 559,067 列 |
| 105 時間在範圍內 | hard | ✅ |
| 106 無 join 膨脹 | hard | ✅ |
| 1 場數 | warning | ✅ 1,230 / 1,230 |
| 2 事件得分 = 終場比分 | warning | ✅ 1,230 場 |
| 3 每列 5+5 名球員 | warning | ✅ 559,067 列 |
| 4 換人一致性 | warning | ✅ 48,251 次換人 |
| 5 上場時間 vs box score | — | skip（沒有 box score 來源） |
| 6 球員秒數 = 5 × 比賽長度 | warning | ✅ 1,230 場 |
| 101 clock 換算秒數 = 來源 secs_game | warning | ✅ |
- 事件 559,067 列（原始 560,364 列 − 1,297 列 msg_type 99）。
- pytest：58 passed。

**遇到的問題**
- 第一次載入時 DuckDB INT32 溢位（`2005 * 1000000000`），改成 BIGINT。
- Windows 主控台 cp950 印不出 `≈`，pipeline 改用 UTF-8 輸出。
- 測試初版改到 xref 依賴的投籃列，修正測試（不是程式錯誤）。
- 已知來源特性：ramirobentes 換人列的陣容是「換人後」，但 CLAUDE.md 定義為「換人前」→ 記在 decisions.md [待確認]，staging 保留來源原樣。
- 檢查 6 在這份資料上幾乎是恆等式（每列都是 5 人時，時間差加總必等於比賽長度），參考價值有限。
- 比賽 0020400756 有兩列「Start of 1st Period」（其中一列時間標 4:00 AM），來源資料錯誤，保留不改，未影響檢查。

**下一步**：Step 2 — shots 表（shufinskiy shotdetail）+ 驗證第 10 項。

**預估剩餘時間**：約 4–5 小時。

## Step 2 — Phase 2 完成：shots 表（2004-05，shufinskiy shotdetail）（2026-10-17 00:15）

**做了什麼**
- `staging/shufinskiy.py` 新增 `stage_shots()`：shotdetail → `core.shots`（LOC_X/LOC_Y 單位為 1/10 英尺，籃框在 0,0）。必要欄位缺失或關鍵欄位 NULL → 硬失敗。
- `load.py` 新增 `load_shots_season()`：每季先刪後插，同一個 transaction；硬檢查 107（每個事件最多一筆投籃、載入列數 = staging 列數）在 commit 前執行。
- `pipeline.py`：pbp 載入成功後接著載入 shots，再跑驗證第 10 項（warning）。
- 測試 8 個（欄位、NULL 失敗、GAME_ID 補零、join 通過、座標缺漏 = warning、來源不一致被回報、重複投籃 rollback、真實 DB 整合）。

**新增/修改的檔案**
`src/nba_platform/staging/shufinskiy.py`, `src/nba_platform/load.py`, `src/nba_platform/pipeline.py`, `src/nba_platform/validate/{checks,report}.py`, `tests/test_shots.py`, `tests/test_integration_db.py`, `docs/validation/*`

**驗證數字**
- 檢查點 0020400027：158 / 158 筆投籃 join（與 CLAUDE.md 的 BigDataBall 測試相同）。
- 整季：FGA 事件 197,626；join 197,626（100%）；有座標 197,626；投籃沒有對應事件 0；join 後命中/球員/球隊不一致 0。
- 107：staging 197,626 = 載入 197,626，重複鍵 0。
- 2PT 158,878 / 3PT 38,748；命中 88,435（= 事件表 shot_made 88,435）。
- pytest：66 passed。

**遇到的問題**：無。

**下一步**：Step 3 — 先比較 2025-26 與 2004-05 的欄位格式，再擴充到 1996-97 → 2025-26 例行賽 + 季後賽。

**預估剩餘時間**：約 4 小時。

## Step 3 — 擴充到所有賽季（1996-97 → 2025-26，例行賽 + 季後賽）（2026-10-17 00:55）

**做了什麼**
- 先比較 2025-26 與 2004-05 的來源格式 → `docs/validation/format_diff_2004-05_vs_2025-26.md`（新 msg_type、clock 有小數、player1/2/3 角色隨年代不同、locX/locY 座標系統不同等）。
- 查清季後賽命名：ramirobentes `pbp_playoffs_{結束年}`；shufinskiy `shotdetail_po_{開始年}`。下載 118 個新檔案（共 121 個，全部記在 `data/raw/manifest.csv`）。
- 投籃座標：shufinskiy shotdetail 每一季（含季後賽）都有，所以全部用 shufinskiy；ramirobentes 的 locX/locY 是不同座標系統（0–100 百分比），沒有混用。
- `pipeline.py --all`：每季獨立執行；任何一季失敗只影響該季，寫進報告。
- 第一次全季執行後逐一調查失敗原因再修正（細節見 decisions.md 2026-10-17 各條）：
  - number_event 並列 → 依 NBA event_num 排序並回報（新 warning 109）
  - 新 msg_type 0 / 20 / 22 / 92 / 93 / 95 → `other`
  - 球隊對照 join 雜訊 → 主要 ID ≥ 99% 才對應，其餘回報（新 warning 110）
  - 舊季後賽 game_id 是流水號 → 系列賽檢查改用兩隊組合
  - validation.results 每次重跑整季取代（避免殘留舊失敗）
- 發現 DuckDB 檔案被雲端同步程式破壞 → `NBA_PLATFORM_DB` 環境變數，今晚的 DB 放在 `%LOCALAPPDATA%\nba_platform\`（不同步的位置）。壞掉的檔案保留原樣。
- 新增 `validate/proposed_corrections.py`（只產生建議，不套用）。

**新增/修改的檔案**
`src/nba_platform/{db,pipeline}.py`, `src/nba_platform/staging/{ramirobentes,corrections_format}.py`, `src/nba_platform/validate/{checks,report,proposed_corrections}.py`, `tests/*`, `README.md`, `data/raw/manifest.csv`, `docs/validation/season_report.md`, `docs/validation/details/*.md`（60 個）, `docs/validation/format_diff_2004-05_vs_2025-26.md`, `docs/validation/duplicate_source_events.csv`, `docs/validation/proposed_corrections.csv`, `docs/decisions.md`

**驗證數字**
- 60 個賽季檔案中 **52 個載入**：季後賽 30 / 30，例行賽 22 / 30。
- 載入總量：28,680 場（例行賽 26,241、季後賽 2,439）、13,237,320 個事件、4,786,340 筆投籃、2,759 名球員、30 個 team_id。
- **8 個例行賽硬失敗（未載入）**：
  - 2000-01、2002-03、2003-04、2011-12、2012-13、2017-18、2019-20：來源把同一個犯規事件重複成兩列（共 8 個事件），event_num 重複 → 依規則硬失敗。
  - 2014-15：一場比賽 48 列陣容的球員沒有 ID（`NA <名字>`，建議 ID 202711）→ 依規則硬失敗；已產生 48 列建議修正（未套用）。
- 已載入賽季的所有硬檢查（9、102、104、105、106、107）全部通過；場數全部等於預期（季後賽 15 個系列賽全部完整）。
- Warning（有載入、待查）：468 項 warning 檢查中 18 項有異常，例如：
  - 檢查 6（球員秒數）：1996-97 4 場、1997-98 5 場等少數比賽
  - 檢查 10（投籃 join）：2016-17 6 筆、2025-26 5 筆等，整體 join 率 > 99.99%
  - 檢查 2（比分）：2025-26 一場（來源自相矛盾：罰球記為命中但比分沒變）
  - 檢查 109（事件排序並列）：數季各 2–8 列
- pytest：79 passed（設定 `NBA_PLATFORM_DB` 後執行）。

**遇到的問題**
- 雲端同步破壞 DuckDB 檔（已改位置，需要你決定長期做法）。
- 8 個例行賽因來源問題硬失敗，需要你決定是否允許「在我們載入的所有欄位都相同時」刪除重複列，以及是否套用 2014-15 的建議修正。

**下一步**：Step 4 — Phase 3 準備工作（2004-05）。

**預估剩餘時間**：約 1 小時。

## Step 4 — Phase 3 準備工作（2004-05，不寫回合邏輯）（2026-10-17 01:05）

**做了什麼**
- `validate/phase3_prep.py`：只讀原始檔，用兩個「參考」回合來源：ramirobentes 自己的 `possession` / `start_poss` 欄位，以及 shufinskiy pbpstats。不是我們的回合邏輯，也沒有放進 `core/`。
- `nba_platform/rules.py` 讀 `config/rules.yaml`；比較用的門檻 [2, 3, 5] 也放在 rules.yaml（`analysis` 區塊），不寫死在程式裡。
- 產生 `docs/possession_rules.md` 草稿：CLAUDE.md 回合規則表的每一種情況都有 2–3 個真實事件序列和整季次數。另外產生 `docs/validation/possession_counts_2004-05.csv`（1,230 場逐場比較）。
- 規則狀態照 CLAUDE.md 寫（decided / open / proposed），沒有替你做任何決定 [待確認]。

**新增/修改的檔案**
`src/nba_platform/rules.py`, `src/nba_platform/validate/phase3_prep.py`, `config/rules.yaml`（analysis 區塊）, `requirements.txt`（pyyaml 6.0.3）, `docs/possession_rules.md`, `docs/validation/possession_counts_2004-05.csv`, `tests/test_rules_and_prep.py`

**驗證數字（2004-05）**
- 回合數：ramirobentes 227,649；pbpstats 226,220（差 +1,429，0.63%）。
- 逐場每隊差異：0 → 53.3%、1 → 36.1%、2 → 9.8%、3–5 → 0.9%、> 5 → 0。
- 節末殘局（開始時剩 ≤ T 秒且 0 分 → 排除）：T = 2 → 1,455（0.639%）；T = 3 → 1,893（0.832%）；T = 5 → 2,474（1.087%）。
  - 發現：≥ 3 秒時兩個來源逐秒完全一致；差異幾乎都在 0–2 秒。推論 pbpstats 已先移除 0 分的節末回合（未驗證）。
- 罰球之間換人：28,315 次多罰球中有 7,212 次（25.47%）；犯規到第一罰之間換人 5,794 次（20.46%）。
- 回合中任何時候換人：22,927 / 227,649 個回合（10.07%）→ 會跨越多段 stint。
- 進攻籃板 37,353；chance 數：1 → 86.5%、2 → 11.5%、3 → 1.7%、4+ → 0.3%。
- 惡意犯規 86 次（罰球 170 次）；技術犯規罰球 1,814 次，其中 287 次由當時的防守方投。
- 罰球未中後的「球隊籃板」7,569 列；非開場跳球 863 次。
- 垃圾時間（CTG 定義，門檻待確認）：每回合判斷 → 1.99%；觸發後持續 → 2.39%。
- pytest：80 passed。

**遇到的問題**
- 一開始對節末差異的解釋寫錯了（以為 pbpstats 的開始時間集中在 3–9 秒），逐秒表格出來後已更正。
- CTG 定義是憑記憶寫的，需要你對照官方說明。

**下一步**：Step 5 — 撰寫 `docs/overnight_report.md`。

**預估剩餘時間**：約 20 分鐘。

## Step 5 — 整夜報告（2026-10-17 01:15）

**做了什麼**：撰寫 `docs/overnight_report.md`（中文），內容包含：做了什麼、驗證結果、遇到的問題、12 項需要你決定的事、建議的下一步、重現指令。

**新增/修改的檔案**：`docs/overnight_report.md`, `docs/decisions.md`, `docs/progress_log.md`

**驗證數字**：pytest 80 passed（`NBA_PLATFORM_DB` 指向 local DB）；`src/nba_platform/core/` 只有空的 `__init__.py`（0 bytes）。

**遇到的問題**：無。

**下一步**：等你決定報告第 4 節的事項（優先：重複來源列、2014-15 建議修正、DB 位置）。

**預估剩餘時間**：整夜計畫已完成。

## Plan 2026-10-17 Step 1 — 資料庫位置與隱私（2026-10-17 08:45）

**做了什麼**
- `db.py`：預設 DB 路徑改為 `%LOCALAPPDATA%\nba_platform\nba_platform.duckdb`，`NBA_PLATFORM_DB` 變成選用的覆寫；新增 `connect(read_only=True)`。CLAUDE.md 同步更新。
- 刪除專案裡壞掉的 `data/nba_platform.duckdb`。
- README 加上同步工具（Synology Drive 等）要排除 `data/`、`.venv/`、`*.duckdb` 的提醒。
- `docs/validation/details/` 加進 `.gitignore`，並移出 git 追蹤（檔案留在本機）。
- 已 commit 的摘要報告移除原文：
  - `possession_rules.md` 的序列改顯示 player1_id，並加上代碼說明
  - 新增 `validate/duplicates.py`，產生只含 ID 的 `duplicate_source_events.csv`
  - `proposed_corrections.csv` 改成只含 ID 和位置
  - 季報告的失敗原因不再引用來源值
  - decisions、進度紀錄、報告裡的描述都換成 ID 或代碼
- git 歷史沒有改寫。

**實際數字**：重複事件 8 個，其中「所有欄位都相同」0 個；缺 ID 的球員鍵 48 個，0 個無法解決。不設環境變數時 pytest 82 passed。

**遇到的問題**：heredoc 裡的 `\n` 被轉成換行，弄壞了 README 和 CLAUDE.md 的路徑，已修正。

**預估剩餘時間**：約 4–5 小時。

## Plan 2026-10-17 Step 2 — 依條件套用修正（2026-10-17 09:10）

**做了什麼**
- 新增「刪除完全重複列」的修正類型（`__row__` / `exact_duplicate` / `drop_one`）；套用時 adapter 會再檢查一次所有欄位都相同，否則失敗。
- `validate/conditional_corrections.py`：依你的條件決定是否寫入 `corrections/corrections.csv`，結果寫在 `docs/validation/conditional_corrections.md`。
- `staging/bigdataball.py`：BigDataBall adapter（只用於驗證）；1,312 個檔案登記到 manifest。
- 垃圾時間改為 CTG 的回溯定義，`rules_version` 升為 `2026-10-17.1`。

**實際數字**
- 重複事件 8 個，「所有原始欄位都相同」**0 個** → 沒有任何修正，8 個逐筆列在報告裡（7 季仍然會硬失敗）。
- 2014-15 缺 ID：48 / 48 列和 BigDataBall 陣容一致 → **套用 48 列修正**（ID 202711）。
- 垃圾時間（回溯定義，2004-05）：3,983 / 227,649 個回合 = **1.75%**（原本每回合各自判斷是 1.99%）。
- pytest：89 passed。

**遇到的問題**：manifest 的來源說明一開始寫了「license: personal use」，是我自己推測的，已刪除。

**預估剩餘時間**：約 4 小時。

## Plan 2026-10-17 Step 3 — 重跑 --all（2026-10-17 14:15）

**做了什麼**：套用步驟 2 的修正後重跑所有賽季（DB 在新的預設位置 `%LOCALAPPDATA%\nba_platform\`）。

**實際數字**
- **53 / 60 個賽季檔案載入**：季後賽 30 / 30，例行賽 23 / 30（多了 2014-15，套用 48 列修正後載入）。
- 載入總量：29,910 場（例行賽 27,471、季後賽 2,439）、13,799,508 個事件、4,991,890 筆投籃。
- **仍未載入（7 季，原因相同）**：2000-01、2002-03、2003-04、2011-12、2012-13、2017-18、2019-20。來源把同一個犯規事件重複成兩列，但兩列在 ramirobentes 推算的罰球歸屬欄位不同 → 不符合「所有欄位都相同」的修正條件 → event_num 重複，依規則硬失敗。
- pytest：109 passed、20 skipped（回合測試骨架）。

**遇到的問題**：重跑期間有一段比預期慢很多（可能是電腦休眠），沒有錯誤。

**預估剩餘時間**：約 2–3 小時。

## Plan 2026-10-17 Step 4 — 驗證第 5 項：上場時間 vs box score（2026-10-17 14:25）

**做了什麼**
- `ingest/nba_api_gamelog.py`：nba_api `LeagueGameLog`（球員層級），每個賽季 × 賽季類型一次請求，間隔 ≥ 3 秒，失敗重試 3 次後跳過。原始回應快取到 `data/raw/nba_api/`，並登記到 manifest。
- `validate/checks.py` 第 5 項：PBP 上場時間（和第 6 項相同的計時方式）對 box score 分鐘數，warning 等級；門檻放在 `rules.yaml` 的 `validation` 區塊（捨入容許 1 分鐘、> 5 分鐘列為特別大）。
- `validate/run_check.py`：不重新載入資料，只對所有已載入賽季重跑單一檢查。
- 報告：`docs/validation/minutes_vs_box.md`（只有數字和 game_id）。

**實際數字**
- 60 / 60 個請求成功（0 次失敗）。
- 53 個已載入賽季全部比對完成，每一筆 box score 的球員-比賽都在 PBP 裡找到，反之亦然（「只出現在 PBP」或「只出現在 box」的筆數 = 0）。
- 大部分賽季差異 ≤ 1 分鐘的佔 > 99.8%，平均絕對差約 0.25 分鐘（就是整數捨入）。
- 例外：
  - 2004-05、2005-06、2006-07 例行賽，以及 2003-04 → 2005-06 季後賽，差異 ±1–2 分鐘的有 3–6%。這幾季每隊 box 分鐘加總等於比賽長度的比例異常高（2004-05 只有 4.6% 的球隊-比賽不等於，一般是約 55%）→ 推論那幾季的 box 分鐘被「平衡」到總和 240 分鐘，造成個別球員偏差（推論，未驗證）。
  - 2005-06 有 110 筆、2006-07 有 243 筆差異 > 5 分鐘（最大約 30 分鐘）；1996-97 有 16 筆。已列在報告，待查。
- pytest：109 passed、20 skipped。

**遇到的問題**：無（nba_api 沒有被擋）。

**預估剩餘時間**：約 2 小時。

- 補充（14:30）：步驟 4 的 commit 送出時有 1 個整合測試失敗（它還假設 2004-05 的第 5 項是 skip）。已修正測試並另外 commit；修正後全部通過。

## Plan 2026-10-17 Step 5 — 驗證第 11 項：BigDataBall 跨來源比對（2026-10-17，約 14:30；時間為事後估計）

**做了什麼**
- `staging/bigdataball.py`（步驟 2 已建立）＋ `validate/bdb_crosscheck.py`：只用於驗證，不載入核心表（只有 `core.player_xref` 的 bigdataball 列）。
- 逐場比較最終比分；用 play_id = event_num 加上相同節數 + 時鐘對齊事件；比較陣容；用對齊結果建立 player_xref（auto，兩種規則）；對不到的名字列出來，不猜。
- 結果寫成 `docs/validation/bigdataball_crosscheck.md`，並把第 11 項記錄到 validation.results / 季報告。

**實際數字（2014-15，目前只有這一季的 BigDataBall）**
- 1,311 場（例行賽 1,230 + 季後賽 81）全部在 core.games 找到；**最終比分 0 場不同**。
- 事件對齊：600,574 / 600,602（99.995%）。
- 陣容：96.43% 的隊伍陣容完全一致（兩隊同時一致的事件 92.89%）。不一致的幾乎都只差 1 位球員，而且是一段一段的（591 段，414 段從換人開始、177 段從節開始）→ 兩個來源在部分換人上的陣容推論不同，無法判斷誰對。
- player_xref：492 個名字中，480 個用名字對上、8 個用陣容對上、4 個對不到（已列出候選 ID，未猜）。
- pytest：109 passed、20 skipped。

**遇到的問題**
- 最初用「最大 play_id 的那一列」當最終比分，結果有 42 場不一致；發現 play_id 在檔案裡不是遞增的，改用檔案最後一列後，0 場不一致。
- 「換人列陣容差異」的假設經驗證是錯的（換人列與其他列的一致率相同）。

**預估剩餘時間**：約 1.5 小時。

## Plan 2026-10-17 Step 6 — 投籃資料品質（2026-10-17，約 14:35；時間為事後估計）

**做了什麼**
- `validate/shot_quality.py`：分析每個賽季（例行賽 + 季後賽，全部 60 個 shotdetail 檔）的座標缺漏率、剛好在 (0,0) 的比例、出手距離分布、出手類型分布。
- `core.shots` 新增 `quality_flags` 欄位：只加旗標，不刪除也不修改資料。門檻放在 rules.yaml。
- 報告：`docs/validation/shot_quality.md`。

**實際數字**
- 座標 NULL：每一季都是 0%。
- 剛好在 (0,0)：1996-97 → 2009-10 有 22–36%（距離 0），2010-11 之後 0%（2020-21 起約 2.7%）→ 推論早期近距離出手沒有定位資料。
- 1996-97 → 1999-00：出手類型只有 9–10 種（之後 25–29 種）；1996-97 上籃佔 29.1%（隔年 23.7%，之後 21–23%），符合 Sports Reference「跳投被記成上籃」的提醒。
- 旗標筆數：`early_season_location_suspect` 533,178；`xy_zero_placeholder` 373,379；兩個都有 196,471；無旗標 3,888,862。投籃總數不變（4,991,890）。
- pytest：110 passed、20 skipped。

**遇到的問題**：pandas `itertuples` 會改掉含空格或連字號的欄位名稱，造成兩次 AttributeError；用 sed 改字串時又插入了換行，造成 SyntaxError。都已修正。

**預估剩餘時間**：約 1 小時。

## Plan 2026-10-17 Step 7 — 回合參考資料：pbpstats（2026-10-17，約 14:40；時間為事後估計）

**做了什麼**
- 從 shufinskiy 下載所有 `pbpstats_*`（只下載單一檔案，不 clone repo）：例行賽 + 季後賽共 50 個檔案（2000-01 → 2024-25；1996-97 → 1999-00 和 2025-26 沒有），已登記到 manifest。
- `reference/pbpstats.py`：載入 `reference.pbpstats_possessions`（一個 pbpstats 回合一列，不存事件原文）。不用它產生我們自己的回合。
- 涵蓋報告：`docs/validation/pbpstats_reference.md`。
- 第 1 項改進：有 box score 快取時，也比對 game_id 清單。

**實際數字**
- 6,082,716 個回合、32,089 場。
- 與已載入的 core.games 比對：2009-10 少 1 場、2023-24 少 2 場（pbpstats 缺）；2024-25 季後賽 pbpstats 多 1 場（`0042400231`）。
- **發現**：ramirobentes 的 2024-25 季後賽少了 `0042400231` 這場（box score 和 pbpstats 都有）。系列賽檢查抓不到，因為勝方仍是 4 勝。改用 box score 場次清單後，第 1 項會回報這一季；其他 52 季的場次和 box score 完全一致。
- pytest：112 passed、20 skipped。

**遇到的問題**：無。

**預估剩餘時間**：約 1 小時。

## Plan 2026-10-17 Step 8 — 資料健康 Dashboard（2026-10-17，約 14:45；時間為事後估計）

**做了什麼**
- `app/data_health.py`（Streamlit）：以唯讀方式開啟 DuckDB，一頁顯示所有賽季的載入狀態、場數、事件數、投籃數、每項驗證的結果（pass / warning / FAIL / skip）；可選擇賽季類型和賽季，看每項檢查的細節（JSON）。沒有任何球員指標。
- README 加上啟動方式：`.venv/Scripts/streamlit run app/data_health.py`。
- `tests/test_dashboard.py`：用 Streamlit `AppTest` 跑 headless 測試（頁面無例外、切換季後賽也正常），並檢查程式只用唯讀連線、沒有寫入語句。
- `requirements.txt`：加入 `streamlit==1.66.0`、`nba_api==1.11.4`。

**實際數字**：Dashboard 顯示 60 個賽季檔案、53 個已載入、29,910 場、13,799,508 個事件。pytest：112 passed、20 skipped。

**遇到的問題**：無。

**預估剩餘時間**：約 45 分鐘。

## Plan 2026-10-17 Step 9 — 文件（2026-10-17，約 14:48；時間為事後估計）

**做了什麼**
- `docs/data_dictionary.md`：每張表的用途、一列代表什麼、主鍵／唯一鍵、每個欄位的型別和意義（core、staging、reference、validation），並列出尚未建立的 owner 表。
- `README.md` 改寫成給招募者看的草稿：專案目的、文字版架構圖、資料來源與條款（沒有標示授權的來源只存在本機，不放進 repo）、驗證結果摘要、如何執行、進度。

**實際數字**：README 的數字都對照 DB 查過（例如每一季投籃 join 率最低 99.88%）。pytest：112 passed、20 skipped。

**遇到的問題**：草稿裡兩個數字寫得不精確（「29 季」、「99.99%+」），查 DB 後已更正。

**預估剩餘時間**：約 30 分鐘。

## Plan 2026-10-17 Step 10 — 切回合的測試案例（只有 fixture 和骨架，沒有實作）（2026-10-17 14:50）

**做了什麼**
- `tests/fixtures/possessions/`：CLAUDE.md 回合規則表的每一種情況，加上「最後一罰沒進」，共 10 種情況，各有 2 個 2004-05 的真實序列（A / B）。
  - 格式是 core.events 的欄位加上當下陣容，只有 ID、代碼和數字，沒有描述原文。
  - README 說明每個檔案的內容。
- `scripts/build_possession_fixtures.py`：只負責挑序列（用 phase3_prep 的參考查詢），可以重現；不含任何回合判斷。
- `tests/test_possession_rules.py`：
  - 10 個 fixture 完整性測試會執行。
  - 20 個規則測試（10 種情況 × A/B）標記為 skip，每個都寫了要驗證什麼，預期結果是 TODO，由你填寫。
- `src/nba_platform/core/` 仍然只有空的 `__init__.py`（0 bytes），沒有寫任何 possession 或 stint 程式碼。

**實際數字**：10 個 fixture 檔、136 列；pytest 112 passed、20 skipped。

**遇到的問題**：無。

**預估剩餘時間**：約 20 分鐘（最後的報告）。

- 更正（14:50）：步驟 5–9 的完成時間原本寫成 15:00–15:35，是預估值、晚於實際時間；已改成事後估計的時間並註明。實際上步驟 4–10 都在 14:20–14:50 之間完成。

## Plan 2026-10-17 Step 11 — 報告（2026-10-17 14:55）

**做了什麼**：撰寫 `docs/report_2026-10-17.md`（中文），內容包含：做了什麼、套用和被擋下的修正、驗證結果、遇到的問題、需要你決定的事、建議下一步、重現指令。

**實際數字**：pytest 112 passed、20 skipped；`src/nba_platform/core/` 只有 0 bytes 的 `__init__.py`。

**遇到的問題**：無。

**預估剩餘時間**：計畫已完成。

## Plan 2026-10-18 Step 1 — 重複犯規列：對照官方 PBP（完成時間 2026-10-17 23:35）

**做了什麼**
- 下載 7 季的 shufinskiy `nbastats_*`（官方 stats.nba.com PBP，只下載單一檔案），已登記到 manifest。
- `validate/duplicate_verification.py`：檢查條件 (a) 不同的欄位全部是 ramirobentes 推算的欄位，(b) 官方 PBP 中同一場同一個 event_num 只出現一次。兩者都成立才寫進 corrections。
- adapter 新增修正類型 `derived_only_duplicate`：套用時會再檢查一次，確認只有推算欄位不同。

**實際數字**：8 / 8 個重複事件符合兩個條件（官方 PBP 的次數都是 1），寫入 8 筆修正，原因 "source duplicate verified against official PBP"。0 筆被擋下。pytest：119 passed、20 skipped。

**遇到的問題**：舊測試比對的錯誤訊息改了，已更新。

**預估剩餘時間**：步驟 2–11，約 4–5 小時。

## Plan 2026-10-18 Step 2 — 已知缺漏和來源矛盾（完成時間 2026-10-17 23:41）

**做了什麼**
- `corrections/known_gaps.csv` + `known_gaps.py`：每次載入後重新套用。新增 `core.known_gaps` 表，以及 `core.games.pbp_missing`、`core.games.known_issue` 兩個欄位。
- `0042400231`：比賽列由 box score 建立（MIN 88 – GSW 99，2025-05-06），`pbp_missing = TRUE`，沒有事件。
- `0022500029`：標記 `source_score_conflict`。
- 驗證：新增狀態 `known`（顯示 ⚠ known），第 1、2 項遇到已知缺漏時顯示 known、不算失敗；第 2、5、6 項排除沒有 PBP 的比賽；新增資訊檢查 111。資料字典已更新。

**實際數字**：重跑 2024-25 季後賽 → 第 1 項 known（15 個系列賽完整、84 場）、第 2 項和第 6 項 pass、第 111 項 known；重跑 2025-26 → 第 2 項 known（1 場）、第 1 項 pass。pytest：123 passed、20 skipped。

**遇到的問題**：`core.games` 多了欄位後，三個舊測試用位置參數插入資料而失敗；改成明確列出欄位名稱。

**預估剩餘時間**：約 4 小時。

## Plan 2026-10-18 Step 3 — 上場時間差異（完成時間 2026-10-17 23:48）

**做了什麼**
- decisions.md 記錄：2004-05 → 2006-07 box 分鐘被平衡是已知來源現象（推論，未驗證），第 5 項維持 warning。
- `validate/minutes_large_diff.py`：調查差異 > 5 分鐘的球員-比賽，只寫報告不改資料。證據有四種：球隊 box 總分鐘、從節開始且沒有換人紀錄的上場段落、隊友互換、BigDataBall 第三來源。報告：`docs/validation/minutes_large_diff.md`。
- BigDataBall 2005-06 登記到 manifest，並跑了跨來源比對，產生該季的 player_xref。

**實際數字**
- 2005-06：110 筆全部判為 box score 比較可能錯。BigDataBall 分鐘數和我們 PBP 相差 ≤ 1 分鐘的有 110 / 110，和 box score 吻合的 0 / 110；這些比賽的球隊 box 總分鐘中位數少了 90 分鐘。
- 2006-07（沒有 BigDataBall，已註明）：243 筆中 237 筆 box 比較可能錯、2 筆和隊友互換、4 筆無法判斷。
- 1996-97：16 筆中 7 筆和隊友互換、6 筆 box 比較可能錯、3 筆 ramirobentes 陣容比較可能錯。
- BigDataBall 2005-06：1,313 場最終比分全部一致；事件對齊 99.999%；隊伍陣容 98.00% 一致；247 個「 (n).csv」副本都和原檔完全相同。
- pytest：128 passed、20 skipped。

**遇到的問題**：一個 SQL 聚合寫法錯誤（GROUP BY ALL 混用聚合欄位），已修正。

**預估剩餘時間**：約 3.5 小時。

## Plan 2026-10-18 Step 4 — 投籃 (0,0) 座標（完成時間 2026-10-17 23:54）

**做了什麼**
- 依你的說明，(0,0) 在 NBA shot chart 中是籃框位置。旗標 `xy_zero_placeholder` 改名為 `rim_location_imprecise`，新增 `rim_location_suspect`（(0,0) 卻是跳投、三分或距離 > 0）。
- 旗標改存在獨立的表 `core.shot_quality_flags`（以 game_id + event_num 為鍵），刪除 `core.shots.quality_flags` 欄位，重新載入不會消失。這也完成了步驟 7 的「獨立的表」那一項。
- 更新 `shot_quality.md`：新增「(0,0) 的意義」一節，以及 (0,0) 出手的類型分布表。資料字典也已更新。

**實際數字**
- (0,0) 出手中，上籃／灌籃／補籃佔 96–100%（每一季）；距離 > 0 的有 0 筆。
- 不合理的 (0,0)：1996-97 有 665 次跳投、448 次三分；之後逐年減少（例如 2009-10 是 57 次跳投、0 次三分）。
- 已載入投籃的旗標：`rim_location_imprecise` 569,850；`rim_location_suspect` 2,860；`early_season_location_suspect` 729,649；至少有一個旗標的投籃 1,103,099 / 4,991,890。
- pytest：130 passed、20 skipped。

**遇到的問題**：舊測試的資料缺 `SHOT_TYPE` 欄位，已補上。

**預估剩餘時間**：約 3 小時。

## Plan 2026-10-18 Step 5 — CTG 垃圾時間：對照官方定義（完成時間 2026-10-17 23:56）

**做了什麼**：逐條核對程式和你提供的官方定義。第四節、分差門檻、回溯認定都已經一致。先發條件原本用 ramirobentes 的 `total_starters_*`（定義不明），改成我們自己算「該場比賽的先發」（每場第一個事件的陣容）在回合開始時合計幾人在場。decisions.md 改為「已對照官方說明確認」；rules.yaml 更新註解，`rules_version` 升為 `2026-10-18.1`。

**實際數字**：我們算的先發人數和來源欄位在 2004-05 的 227,649 個回合中 100.00% 一致；垃圾時間比例維持 1.75%（3,983 個回合）。pytest 全部通過。

**遇到的問題**：定義沒有寫明剛好剩 9:00／6:00 時要歸哪一段，先歸到較低門檻那一段，標記 [待確認]。

**預估剩餘時間**：約 2.5 小時。

- 補充（2026-10-17 23:57）：步驟 5 的 commit 送出時，`tests/test_rules_and_prep.py` 有語法錯誤（pytest 回報 1 error）。我的檢查只擋 "failed"、沒有擋 "error"，所以沒攔下來。已修正測試並另外 commit，檢查也改成同時擋 failed 和 error；步驟 7 會加上 pre-commit hook。

## Plan 2026-10-18 Step 6 — 定義更新（完成時間 2026-10-18 00:02）

**做了什麼**
- (a) CLAUDE.md：換人列陣容改為「換人後」，每次換人開始新的 stint；decisions.md 註明推翻了審查者的定義，以及你給的原因。
- (b) CLAUDE.md：事件表是得分的唯一來源；possessions 拿掉 `scoring_team_id`，只留 `points`（進攻方得分、不含技術犯規罰球）；不設 `def_points`；陣容效率公式。
- (c) `validate/scoring_attribution.py` → `docs/validation/scoring_attribution.md`：用參考回合找「得分隊伍 ≠ 進攻方」的得分事件（2004-05、2024-25）。
- (d) `possession_rules.md` 加上注意事項、pbpstats 的 ≤ 2 秒刪除規則、pbpstats 混合做法（參考資訊）。
- (e) 「先複製，再偏離」寫進 CLAUDE.md 和 possession_rules.md；rules.yaml 加上 `pbpstats_compat` / `custom` 兩組設定檔；`load_rules(profile=…)`。

**實際數字（c）**
- 2004-05：得分事件 136,897 筆，其中 4,154 筆的得分隊伍不是當時的進攻方：
  - 技術犯規罰球 237 筆
  - and-1 加罰 3,915 筆
  - 節邊界的罰球 1 筆
  - 其他 1 筆
- 2024-25：得分事件 144,140 筆，其中 4,457 筆的得分隊伍不是當時的進攻方：
  - 技術犯規罰球 223 筆
  - and-1 加罰 4,231 筆
  - 節邊界的罰球 2 筆
  - 其他 1 筆
- 因為不是全部都是技術犯規罰球，所以依計畫不宣告設計成立、也不改設計，標記 [待確認]。and-1 推論是參考回合切法造成的現象。
- pytest：全部通過（由 pre-commit hook 檢查）。

**遇到的問題**：無。

**預估剩餘時間**：約 2 小時（步驟 7–11）。

## Plan 2026-10-18 Step 7 — pipeline 自動化（完成時間 2026-10-18 00:05）

**做了什麼**
- `pipeline --all` 跑完後自動執行投籃品質旗標和 BigDataBall 比對（`post_load`）；任何一步失敗都會印出並記錄，不會蓋掉載入結果。
- 投籃品質旗標在步驟 4 已經改存在 `core.shot_quality_flags`，重新載入不會消失。
- pre-commit hook：`scripts/git-hooks/pre-commit` 會跑整套 pytest，failed 或 error 都會擋下 commit；README 說明安裝方式（`git config core.hooksPath scripts/git-hooks`）。
- 為了避免步驟 5 那種錯誤再發生，hook 在步驟 6 之前就先裝上了；步驟 6 的 commit 已經經過 hook 檢查。

**實際數字**：用一個故意失敗的測試做探測 commit，hook 回報「pytest exited with 1 — commit blocked」，HEAD 沒有改變；探測檔已刪除。新增 2 個測試；pytest 133 passed、20 skipped。

**遇到的問題**：heredoc 會把 `\n` 轉成換行，改用 Edit 工具修改。

**預估剩餘時間**：約 1.5 小時（重跑約 30–40 分鐘）。

## Plan 2026-10-18 Step 8 — 重跑 --all，確認自動化（完成時間 2026-10-18 00:45）

**做了什麼**：套用步驟 1 的 8 筆重複列修正、步驟 2 的已知缺漏後，重跑 `pipeline --all`。跑完後自動執行投籃品質旗標和 BigDataBall 比對。

**實際數字**
- **60 / 60 個賽季檔案全部載入**（例行賽 30 / 30、季後賽 30 / 30），0 個硬失敗。
  - 之前沒載入的 7 季（2000-01、2002-03、2003-04、2011-12、2012-13、2017-18、2019-20）這次都載入了。
- 載入總量：37,986 場（例行賽 35,546、季後賽 2,440，其中 1 場 `pbp_missing`）、17,476,387 個事件、6,328,071 筆投籃。
- 自動化步驟都執行了：
  - 投籃品質旗標：`rim_location_imprecise` 703,971 筆、`rim_location_suspect` 3,191 筆、`early_season_location_suspect` 729,649 筆，至少有一個旗標的投籃 1,237,221 筆。
  - BigDataBall 比對：2005-06、2014-15 的第 11 項都已記錄。
  - post-load 錯誤 0 個。
- pytest：全部通過（由 pre-commit hook 檢查）。

**遇到的問題**：無。

**預估剩餘時間**：約 1 小時（步驟 9–11）。

## Plan 2026-10-18 Step 9 — BigDataBall 陣容分歧仲裁（只寫報告）（完成時間 2026-10-18 01:01）

**做了什麼**：`validate/bdb_arbitration.py`。每一段分歧都用兩種證據判斷：box score 分鐘數，以及官方 PBP 的換人紀錄。依「從換人開始／從節開始／其他」分類統計，結果加到 `bigdataball_crosscheck.md`。BigDataBall 現在有 7 季，全部比對完成並登記到 manifest。

**實際數字**（可判斷的段落／總段落 → ramirobentes 對：BigDataBall 對）
- 2004-05：76 / 97 → 76 : 0
- 2005-06：11 / 16 → 5 : 6
- 2007-08：183 / 205 → 183 : 0
- 2010-11：4 / 15 → 4 : 0
- 2012-13：23 / 26 → 23 : 0
- 2013-14：135 / 159 → 135 : 0
- 2014-15：215 / 216 → 215 : 0

各季陣容一致率在 96.4%–99.6% 之間；最終比分只有 2012-13、2013-14 各 1 場不同。

**遇到的問題**：仲裁加上新增的 5 季，比對跑了約 15 分鐘。

**預估剩餘時間**：步驟 10–11，約 20 分鐘。

## Plan 2026-10-18 Step 10 — 更新 research_summary.md（完成時間 2026-10-18 01:03）

**做了什麼**：更新資料基礎（60 / 60 季）、重複列和已知缺漏的處理、box score 分鐘大差異的調查、BigDataBall 7 季的比對和仲裁、(0,0) 投籃的意義和新旗標、得分設計檢查、先複製再偏離的策略，以及「尚未解決的問題」。標示方式維持「事實／來源數值／推論」。

**實際數字**：見文件；BigDataBall 7 季共 19 個名字沒有對到 ID。

**遇到的問題**：無。

**預估剩餘時間**：步驟 11，約 10 分鐘。

## Plan 2026-10-18 Step 11 — 報告（完成時間 2026-10-18 01:04）

**做了什麼**：撰寫 `docs/report_2026-10-18.md`。

**實際數字**：pytest 137 passed、20 skipped；`core/` 只有空的 `__init__.py`。

**預估剩餘時間**：計畫 2026-10-18 已完成。

## 整夜批次準備（完成時間 2026-10-18 01:13）

**做了什麼**
- NBA.com 介面測試：34 次請求，0 次失敗 → `docs/nba_api_endpoint_inventory.md`（已在前一個 commit）。
- `scripts/overnight_batch.py`：工作 A–H。
- 試跑（每個工作只跑一季或幾場，(A) 只做快照）：A–H 全部成功。
- 試跑時發現並修正兩個問題：
  - F 的參數撞名。
  - **team_xref 錯誤**：載入季後賽時會刪掉整季的對照，只留下季後賽球隊。主資料庫已經修復，從 480 列補到 892 列。

**試跑數字**
- D：2000-01，扣掉節末殘局後和 pbpstats 完全一致的球隊-比賽佔 96.8%，差距 ≤ 1 的佔 99.9%。
- G：2025-26，和 NBA 官方 POSS 完全一致的佔 89.3%，差距 ≤ 1 的佔 99.4%。
- E：2014-15 和之前一致。
- H：4 筆單場資料。
- C：matchups 2024-25 有 231,961 列、1,229 場。

**預估剩餘時間**：完整批次約 7 小時（H 會在 08:00 停止）。

## 整夜批次結果（完成時間 2026-10-18 03:05）

**做了什麼**：讀取批次摘要，撰寫 `docs/report_overnight_batch_2026-10-18.md`，更新 `research_summary.md`。

**實際數字**
- A 可重現性：11 / 11 張表完全相同。
- D（對 pbpstats）：差 0 佔 91.5%。
- G（對 NBA 官方）：差 0 佔 72.0%；2016-17 前後有明顯分界。
- F：完成 605 / 1,936 個請求，之後 NBA.com 連續逾時而停止；H 沒有新資料。

**遇到的問題**：NBA.com 約 600 次請求後開始限流（推論）。

## 整夜批次 v2 準備（完成時間 2026-10-18 23:48）

**做了什麼**：依你的決定修改 `overnight_batch.py`：請求間隔 7–8 秒、冷卻 45/90/90 分鐘、單場資料先抓季後賽再抓 2025-26/2024-25 例行賽、摘要每個工作最多 10 行。新增冷卻邏輯測試；試跑成功。

## 整夜批次 v2 結果（完成時間 2026-10-19 06:43）

- F：1,931 / 1,936 個請求完成（play type 只差 5 個）；H：抓了 842 個單場 box score，季後賽完成 5 季，停在 2020-21 季後賽 0042000112。
- 冷卻 2 次（45、90 分鐘）；第 3 次冷卻會超過截止時間而停止。
- 報告：docs/report_overnight_batch_2026-10-19.md。

## Dashboard 參考資料頁 + README 更新（完成時間 2026-10-19 09:44）

**做了什麼**
- `app/pages/1_Reference_data.py`：Dashboard 第二頁（唯讀、沒有球員指標）。內容有三部分：
  - 回合數基準：逐季列出和 pbpstats、NBA 官方的一致率，附表格和折線圖，並說明 2016-17 的分界。
  - NBA.com 各個 reference 表的涵蓋賽季和列數。
  - 單場 box score 原始檔的逐季數量。
- README：更新 Status、資料來源、驗證摘要（60 / 60 季、可重現、回合數基準、BigDataBall 7 季）、Dashboard 啟動說明和 Roadmap。

**實際數字**：新增 2 個測試（頁面 headless 執行、唯讀檢查）。BigDataBall 共 8,883 場，其中 2 場比分不同。

**遇到的問題**：唯讀檢查的測試原本會把 `df.insert` 誤判成 SQL 的 INSERT，改成只檢查 SQL 寫入語句。

## matchups 季後賽（完成時間 2026-10-19 09:48）

- `task_c` 同時下載例行賽和季後賽（matchups_po_2017–2024）；`reference.matchups` 共 1,886,689 列、10,076 場（季後賽每季 82–87 場），100% 的比賽在 core.games 找得到。

## 載入單場 box score（完成時間 2026-10-19 09:50）

- 新模組 `reference/boxscores.py`：把已下載的原始 JSON 載入 `reference.nba_box_tracking`（425 場、11,868 列）和 `reference.nba_box_hustle`（425 場、8,323 列），0 個空殼。批次腳本的 H 跑完後會自動載入；Dashboard 參考資料頁也會顯示已載入的場數。
- 驗證（`docs/validation/boxscore_reference.md`）：追蹤 box score 的上場時間精確到秒，和我們 PBP 算出的上場時間相比，**100% 的球員-比賽差距 ≤ 10 秒**，兩邊的球員名單也完全相同。

## 整理待決定事項（完成時間 2026-10-19 09:52）

- `docs/pending_decisions.md`：
  - 得分設計那 2 筆「其他」是同一種情況：回合在最後一罰投進時結束後，同一死球時間點又有另一次犯規（away-from-play / loose ball），由剛進攻完的那隊加罰 1 球。附 3 個選項。
  - BigDataBall 19 個名字：16 個建議以 manual 方式加入；3 組是同名的兩位球員（Marcus Williams、Chris Johnson、Tony Mitchell），需要用「名字 + 球隊」才能區分。
  - 其他 8 項 [待確認] 的勾選清單。
- 只寫報告，沒有修改任何資料。

## Dashboard 資料第一批：官方 box score + PBP box（進行中，暫停於 2026-10-19 16:27）

- 已完成（只有程式和測試，**還沒寫入 DuckDB**）：
  - `reference/player_box.py`：讀已下載的 LeagueGameLog（60 個季檔）→ `reference.nba_player_box`；重複的 (game_id, player_id) 或不在 core.games 的比賽 → 停止。
  - `marts/player_game_pbp.py`：用 core.events 算球員單場數據（得分、投籃、罰球、籃板、助攻、抄截、阻攻、失誤、犯規、上場秒數、+/-）。
- 試算（唯讀）：2004-05 例行賽與官方 box 相比，各項 ≥ 99.98% 球員-比賽完全相同（犯規加上「雙方犯規算兩人」後一致）；1996-97、2014-15 季後賽、2025-26 也都 ≥ 99.6%。2025-26 犯規多 80 次，原因待查（只報告，不改規則）。
- 下一步：比對報告 `docs/validation/box_vs_pbp.md`、展示用 `marts.player_game`、Dashboard「比賽」「球員」頁、文件。寫入 DuckDB 前要先關 Streamlit。

## 夜間批次 H：單場追蹤 / hustle box score（完成時間 2026-10-20 08:44）

- 2026-10-19 19:53 開始；00:38 第一個程式隨工作階段結束而中斷，01:08 改成獨立程式重新啟動，07:38 因下一次排定休息會超過 08:00 而停止。
- 兩段合計約 4,200 個請求，0 次冷卻；第一段有 6 次單次失敗，第二段一開始就全部補抓成功，第二段 0 次失敗。
- 季後賽 2013-14 → 2025-26 全部完成；2025-26 例行賽 1,230 / 1,230 場；2024-25 例行賽 447 場（到 `0022400446`）。
- 已載入 `reference.nba_box_tracking` 2,765 場、`reference.nba_box_hustle` 2,594 場。追蹤 box 的上場秒數與 PBP 相比，每一季 100% 的球員-比賽差距 ≤ 10 秒（`docs/validation/boxscore_reference.md`）。
- 下一步：2024-25 例行賽剩下約 783 場（約 1,570 個請求，約半個晚上）。

## 批次 H 手動補抓：2024-25 例行賽（完成時間 2026-10-20 12:10）

- 兩次手動執行（40 分鐘 + 62 分鐘），共約 780 個請求，0 次失敗、0 次冷卻。
- 2024-25 例行賽：追蹤與 hustle 各 836 / 1,230 場（到 `0022400836`）。已載入 `reference.nba_box_tracking` 3,154 場、`reference.nba_box_hustle` 2,984 場。
- 下一步：2024-25 例行賽剩約 394 場（約 790 個請求，約 1.5 小時）。

## 批次 H 手動補抓：2024-25 例行賽第三段（完成時間 2026-10-20 17:41）

- 15:46 → 17:27，311 個請求，1 次失敗（`0022400862` hustle，連線被遠端重設；下次執行會補抓）。15:52 到 16:53 之間沒有任何寫入，推測電腦睡眠（未直接確認）。
- 2024-25 例行賽：追蹤 992 / 1,230 場、hustle 991 場（到 `0022400992`）。已載入 `reference.nba_box_tracking` 3,310 場、`reference.nba_box_hustle` 3,139 場。
- 下一步：剩約 238 場（約 480 個請求，約 1 小時）。

## 批次 H 手動補抓：2024-25 例行賽第四段（暫停時間 2026-10-20 20:14）

- 17:42 與 18:22 兩次啟動，18:22 起改成 3 小時版本；20:1x 由使用者要求手動停止（程式被強制結束，所以事後手動執行 `python -m nba_platform.reference.boxscores` 載入）。
- 18:24 到 19:33 之間沒有寫入（推測電腦睡眠，未直接確認），和上一輪 15:52 到 16:53 相同。
- `scripts/overnight_batch.py` 新增 `--regular-years`（預設 2026,2025 不變），讓 H 可以擴到更早的例行賽；這次用 2026,2025,2024，但還沒抓到 2023-24。
- 2024-25 例行賽：追蹤 1,221 / 1,230 場、hustle 1,219 場。已載入 `reference.nba_box_tracking` 3,539 場、`reference.nba_box_hustle` 3,367 場。
- 下一步：2024-25 剩約 10 場（再跑一次會自動補完，包括之前失敗的 `0022400862` hustle），然後才是 2023-24 例行賽。

## 資料模型與 Dashboard 規格（完成時間 2026-10-20 22:05）

- `docs/data_model.md`：說明為什麼大表沒有 PK、全庫沒有 FK（逐季刪除重載、DuckDB FK 無 cascade、索引成本），列出每張表的邏輯主鍵、由哪個驗證檢查保護，附 Mermaid ER 圖與 DBeaver 虛擬外鍵設定方式。**沒有修改 schema**。
- `docs/dashboard_spec.md`：三層網站地圖（基本／進階／一體化）、每頁的來源表與前置條件、layer 2 對回合程式的欄位清單、要建的 marts 與主鍵、待你決定的 4 個問題。
- 下一步：載入官方 box score、PBP box 比對報告、`marts.player_game` 等（需先關閉 Streamlit / DBeaver）。

## 官方 box score 載入與 PBP box 比對（完成時間 2026-10-20 22:10）

- `reference.nba_player_box`：786,768 列、37,986 場，100% 的比賽和球員都在 core；`marts.player_game_pbp`：786,751 列（沒有 PBP 的比賽不含）。
- 比對報告 `docs/validation/box_vs_pbp.md`（60 個季檔）：幾乎所有季節每項數據 ≥ 99.9% 的球員-比賽完全相同。
- 比對時查出兩個「規則差異」，都是球員欄位依時代而不同，已寫進程式、文件和測試，**事件表沒有改**：抄截 2016-17 → 2024-25 在 player3（原本只看 player2，一致率只有約 53%）；2023-24 起新增的技術犯規子類型 32（假摔）不算個人犯規。
- 剩下的小差異（< 99.9%）：2016-17 例行賽 REB／PF、2025-26 例行賽 REB／BLK／PF、1996-97 與 1999-00 季後賽少數項目；最大差異的比賽列在報告末段，尚未逐場調查。
- 下一步：`marts.player_game`、`marts.player_season`、球隊 marts，再做 Games／Players 頁面。

## Layer 1 marts：player_game / player_season / team_game / team_season（完成時間 2026-10-20 22:58）

- `marts/box_marts.py`：四張表都有真正的 PRIMARY KEY，一次交易重建。列數：player_game 786,768、player_season 22,572、team_game 75,972、team_season 1,372。
- 抽查：Iverson 2004-05 場均 30.7 分／75 場、Curry 2015-16 場均 30.1 分／79 場、Celtics 2023-24 64 勝 18 敗，皆與已知紀錄一致。
- 一致性：球員得分加總與 core.games 比分不同的有 6 個 team-game（5 場，`docs/validation/box_marts.md`）：4 場是官方 box 本身與事件和比分都不一致、1 場（`0022500029`）是已知的來源比分衝突；只報告，不修改。
- 球隊節奏與評分暫時用 NBA 官方 POSS，欄位名稱標示 `official`，等自己的回合數做好再換。
- 下一步：Games、Players 頁面（Streamlit，只讀 marts）。

## Layer 1 頁面：Games 與 Players（完成時間 2026-10-20 23:00）

- `app/pages/2_Games.py`：選季別、球季、球隊、比賽 → 兩隊官方 box score（`marts.player_game`）+ 比分差走勢圖（來自 core.events）。
- `app/pages/3_Players.py`：球季排行榜（可選排序欄位、最少出賽場數）、球員各季數據、單季逐場紀錄與得分走勢（`marts.player_season`／`player_game`）。
- 兩頁都只用唯讀連線、只讀 marts（Games 的走勢圖讀該場的 events）；測試涵蓋可載入、切換季別、唯讀。順便把所有頁面的過時參數 `use_container_width` 改成 `width="stretch"`。
- 下一步：Teams 與 Shooting 頁面（投籃分區、聯盟百分位），再接 season-level 追蹤／hustle 頁。請你用 `streamlit run app/data_health.py` 實際看過版面。

## 2024-25 例行賽下載補完＋Teams／Shooting 頁面（完成時間 2026-10-20 23:12）

- 下載：2024-25 例行賽追蹤與 hustle 各 1,230 / 1,230 場（20 個請求、2.6 分鐘、0 失敗）。已載入 `reference.nba_box_tracking` 3,548 場、`reference.nba_box_hustle` 3,378 場。目前設定的下載範圍（季後賽 2013-14 → 2025-26、2025-26 與 2024-25 例行賽）全部完成。
- `marts/shot_zones.py`：`marts.shot_zones_league`（420）、`shot_zones_team`（18,950，含 offense／defense）、`shot_zones_player`（106,941，含聯盟百分位）。6,328,071 筆投籃全部只被計入一次；`config/rules.yaml` 新增 `dashboard:` 區塊（百分位的最少出手數 100／20）。
- 抽查：2024-25 聯盟禁區命中率 66.4%、中距離 41.7%、Curry 外線區在聯盟前 20%。
- 頁面：`4_Teams.py`（球隊賽季表含官方 ORTG／DRTG／節奏、名單、投籃分區、賽果）、`5_Shooting.py`（球員分區頻率與命中率、聯盟百分位、投籃圖）；測試涵蓋載入、切換季別、唯讀。
- 下一步：請你實際用瀏覽器看過版面；之後可以做整季追蹤／hustle 頁，或開始寫回合程式。

## Tracking 頁面（完成時間 2026-10-20 23:33）

- `marts/tracking.py`：`marts.player_tracking_season`（9,759 列，其中 7,941 列有 hustle），PRIMARY KEY，精選約 50 欄分 5 組；未知球員、重複鍵、缺少來源欄位都會停止建置，hustle 列不會遺失。
- 驗證 `docs/validation/tracking_vs_box.md`：追蹤表的 GP／AST／STL／BLK／REB 與官方 box（球員整季加總）比對——追蹤從不高於 box，找不到對應 box 的列為 0；例行賽追蹤有時偏低（來源少了一些比賽，2023-24 最明顯），季後賽幾乎完全一致。一開始按球隊比對結果很差，原因是例行賽的交易球員在追蹤表只有一列（最後球隊、整季加總），已改成按球員比對。
- 頁面 `app/pages/6_Tracking.py`：選季別、球季、類別（5 組）、尺度（總計／每場／每 36 分鐘）、最少出賽，下方可看球員歷年；表格不存在時顯示提示而不是錯誤。測試涵蓋所有類別與尺度。
- 抽查：2024-25 每場觸球 Jokić 98.8、Trae Young 85.8；每場干擾傳球 Dyson Daniels 5.9，與已知情況相符。
- 下一步：請你用瀏覽器實際看過所有頁面；之後可以開始寫回合程式（我審查），或處理 `docs/pending_decisions.md`。

## 整夜下載 H：2023-24 例行賽與 2022-23 例行賽前段（完成時間 2026-10-21 09:12）

- 2026-10-20 23:53 → 2026-10-21 08:00（486 分鐘），2,923 個請求，planned rest 4 次（每 600 個請求 30 分鐘），0 次冷卻、無中斷（程式啟用 keep-awake，沒有再出現睡眠造成的空窗）。
- 3 次單次逾時（`0022300390` hustle、`0022301082` 追蹤、`0022200213` hustle），下次執行會自動補抓。
- 2023-24 例行賽：追蹤 1,229 / 1,230 場、hustle 1,229 場；2022-23 例行賽：追蹤 233 場、hustle 232 場（到 `0022200233`）。已載入 `reference.nba_box_tracking` 5,010 場、`reference.nba_box_hustle` 4,839 場。
- 新增 `keep_awake()`（`scripts/overnight_batch.py`）：下載期間要求 Windows 不要閒置睡眠，結束自動恢復，不改系統設定；合上螢幕仍可能睡眠。
- 提醒：下載期間資料庫被佔用，pytest 的整合測試會因無法開啟資料庫而失敗，所以 commit 要等下載結束。
- 下一步：2022-23 例行賽剩約 997 場（約 2,000 個請求，約 1 晚）。

## 批次 H 手動補抓：2023-24 例行賽補完、2022-23 例行賽到 466 場（完成時間 2026-10-21 10:38）

- 09:34 → 10:36（61.6 分鐘），469 個請求，0 失敗；昨晚 3 個逾時的檔案已補回，2023-24 例行賽追蹤與 hustle 各 1,230 / 1,230 場。
- 2022-23 例行賽：追蹤與 hustle 各 466 / 1,230 場（到 `0022200466`）。已載入 `reference.nba_box_tracking` 5,244 場、`reference.nba_box_hustle` 5,074 場。
- 下一步：2022-23 例行賽剩約 764 場（約 1,530 個請求，約 3.2 小時）。

## 批次 H 手動補抓：2022-23 例行賽到 705 場（完成時間 2026-10-21 13:10）

- 11:10 → 12:11（61.3 分鐘），478 個請求，0 失敗、0 冷卻。
- 2022-23 例行賽：追蹤與 hustle 各 705 / 1,230 場（到 `0022200705`）。已載入 `reference.nba_box_tracking` 5,483 場、`reference.nba_box_hustle` 5,313 場。
- 下一步：2022-23 例行賽剩約 525 場（約 1,050 個請求，約 2.2 小時）。

## 回合規則決定＋實作指南（完成時間 2026-10-21 14:50）

- 你決定了 11 項（`docs/decisions.md` 2026-10-21）：罰球之間的球隊籃板忽略；跳球看下一個有球隊的事件；chance 只用進攻籃板；照來源順序、錯誤用 corrections；2 筆 between-possessions 罰球比照技術犯規（新事件旗標 `is_between_possessions_ft`）；2025-26 的新 msg 維持 other；is_after_timeout 的定義；CTG 邊界維持；custom 換人計分保持開放；pbpstats_compat 的技術罰球先查再設。
- 查 pbpstats 原始碼：技術罰球計入陣容 +/-（算給犯規當下的陣容），不結束回合（推論）→ `pbpstats_compat.technical_ft` 設為 false / lineup_at_foul。
- 更新：CLAUDE.md 規則表、`config/rules.yaml`（`rules_version 2026-10-21.1`）、`docs/possession_rules.md`、`format_diff` 報告、`pending_decisions.md`、`sql/schema.sql`（events 新增 `is_between_possessions_ft`）、規則測試。
- 新文件 `docs/possession_implementation_guide.md`：範圍、輸入輸出、7 個步驟的函式切分與對應測試、檢查數字、已知資料陷阱（不含任何回合邏輯）。
- 待你確認：`timeout_team_id` 欄位名稱。

## 回合程式步驟 1：stints（完成時間 2026-10-21 16:08，等待審查）

- 約定 1 依你的要求改成「Claude 寫 core/、你決定規則並審查」；stint 規則改為同一秒連續換人合併（中間有其他事件就不合併）、每節開新 stint、球員 ID 照來源順序（`rules_version 2026-10-21.2`）。
- `src/nba_platform/core/stints.py` + `tests/test_stints.py`（14 個測試，含真實的「罰球之間換人」fixture）。
- 一場（`0020400027`）：29 個 stint，兩隊 5×秒數 = 14,400，20 位球員上場秒數與已驗證數字差 0 秒。
- 2004-05 整季（只讀試跑，未寫入 DB）：1,230 場、38,723 個 stint、0 個錯誤、0 次「沒有換人列卻換陣容」；1,523 個 0 秒 stint（罰球之間換人）；每場兩隊秒數都等於比賽長度；24,955 個球員-比賽中 4 個不同，全在 `0020400152`（來源第 4 節從 11:39 開始，21 秒的歸屬不同），記錄不修改。
- 下一步（你審查後）：寫入 `core.stints` 與 `events.stint_id`，再做步驟 2（罰球與犯規的連結）。

## 回合程式步驟 1 寫入 DB＋步驟 2：罰球趟次與犯規連結（完成時間 2026-10-21 16:22，等待審查）

- `build_core --step stints`：2004-05 例行賽寫入 `core.stints`（38,723）與 `events.stint_id`（559,067 個事件全部連到），檢查全過；新表有 PRIMARY KEY 與 rules_version。
- `core/free_throws.py`：罰球種類（10–15 一般、16/21/22 技術、18–20/27–29 惡意、17/25/26 clear path、81 transition take，60 季代碼一致）；每一趟連到造成它的犯規（同一秒、對方、種類相符，先往前找再往後找，一個犯規只用一次，找不到留 NULL）。
- 試跑：2004-05 例行賽與季後賽 100% 連結；1996-97 剩 7 趟連不到（來源缺漏）。不完整的趟次都是罰球區違例（真實狀況，步驟 4 要正確處理）。
- 試跑抓到並修好 2 個問題：沒有球隊的技術犯規、一般罰球中間插入技術罰球。
- 測試：`test_free_throws.py`（17）、`test_build_core.py`（2）。
- 待你決定（步驟 4 用）：罰球後保留球權的情況（transition take、away-from-play、inbound）在 custom 裡要算 1 個還是 2 個回合；pbpstats_compat 照 pbpstats。

## 回合程式步驟 3：籃板分類（完成時間 2026-10-21 16:30，等待審查）

- 你決定：罰球後保留球權的情況，custom 跟 pbpstats 一樣（`rules_version 2026-10-21.3`）。
- `core/rebounds.py`：每個籃板對到之前最近的未進球；只有投籃沒進、或非技術罰球的最後一罰沒進之後才是「真的籃板」；同隊 = 進攻籃板。
- 2004-05 試跑：124,824 個籃板列，真的 116,914；忽略 7,559（非最後一罰後）與 350（技術罰球後）。球員的進攻／防守籃板和官方 box score 一致率 99.980% / 99.988%。
- 再查 pbpstats：away-from-play／inbound／transition take 的最後一罰投進時一律不結束回合，沒有「最後 2 分鐘」的條件；2004-05 有 15 次 away-from-play 最後一罰沒進後是球員搶到籃板（活球）。pbpstats_compat 照抄；custom 要你決定。
- 測試：`test_rebounds.py`（9）。

## 回合程式步驟 4–7：回合本體（完成時間 2026-10-21 17:06，等待你決定 2 件事）

- `core/possessions.py`：回合結束判斷、possession_id / chance_id、每回合一列（起訖、起始／結束類型、得分、chance 數、情境欄位、節末殘局、CTG 垃圾時間、暫停後）、跨 stint 片段。`tests/test_possession_rules.py` 的 TODO 全部填完（31 個測試）。
- 2004-05 整季（只讀試跑）：1,230 場、229,403 回合、得分全部守恆；和 pbpstats 每隊回合數**完全相同 94.02%**、差 ≤1 為 99.92%。
- 比對抓到並修好 and-1 判斷（罰球被違例取消時）。
- 剩下的差異七成來自惡意犯規與 clear path：pbpstats 實際算 1 個回合，我們依 CLAUDE.md 算 2 個。試算改成 1 個：**98.37%**。等你決定。
- 速度：改寫成一般 Python 列表後，一季約 2 分鐘。

## 回合程式：依你的 3 個決定修改，2004-05 和 pbpstats 一致 98.37%（完成時間 2026-10-21 18:33）

- 惡意犯規、clear path：兩個設定檔都算 1 個回合（pbpstats 實際資料就是這樣，CLAUDE.md 原本括號寫的 pbpstats 是錯的，已更正）。
- 回合之間的罰球：兩個設定檔都用 (a)；在這點上 pbpstats_compat 刻意和 pbpstats 不同（2004-05 共 3 筆）。
- after_jump_ball 成為第 7 種起始類型；跳球後判斷球權時排除犯規。
- `rules_version 2026-10-21.4`；新增 2 個測試（回合之間的罰球、跳球後的起始類型），回合規則測試共 34 個全過。
- 2004-05 整季（只讀）：229,292 回合，得分全部守恆；和 pbpstats 每隊回合數**完全相同 98.37%**、差 ≤1 為 99.96%（ramirobentes 為 98.9%）。剩 36 場不同，下一步逐場調查。
- 還沒寫入資料庫（core.possessions 等），等你審查。

## 回合程式：No Turnover 修正（完成時間 2026-10-21 19:32）

- 查剩下的差異時發現：來源裡 action type 0（文字 "No Turnover"，2004-05 共 606 筆）其實記錄了抄截，pbpstats 也算失誤。改成結束回合後，和 pbpstats 的每隊回合數**完全相同 98.54%**、差 ≤1 為 **100%**（`rules_version 2026-10-21.5`，標 [待確認]）。
- 剩 36 個 team-game 不同，約一半發生在節末最後幾秒（和 pbpstats 對「剩 ≤2 秒的回合」的細節不同），其餘是零星的特殊序列；尚未調整，等逐場調查。

## 回合寫入資料庫＋檢查 7、8、111（完成時間 2026-10-21 19:40，等待審查）

- `build_core --step possessions`：2004-05 例行賽寫入 `core.possessions`（229,296）、`core.possession_stint_segments`（257,662）與 events 的 possession_id／chance_id／foul_event_seq／is_technical_ft／is_between_possessions_ft；新表都有 PRIMARY KEY；`rules_profile` 與 `rules_version` 一起記錄。
- 檢查（`docs/validation/possession_check_2005_regular.md`）：111（硬性）通過——每場每隊得分都守恆；7：4 場差 3（pbpstats 自己在其中 3 場也差 3）；8：和 pbpstats 完全一致 98.54%、差 ≤1 為 100%。
- 用真實資料抓到一個程式錯誤並修正：來源重複的 period_start 列會產生沒有進攻方的空回合。
- 下一步：調查節末的差異；擴到其他季（先 pbpstats_compat 全部季，再做 custom）。

## 回合：全部 50 個季節（完成時間 2026-10-21 21:37，等待你決定 1 件事）

- `build_core --all --step possessions`：2000-01 → 2024-25 的例行賽與季後賽（外加 2025-26 例行賽）全部寫入；硬性檢查 111 全部通過；總表 `docs/validation/possession_summary.md`。
- 修了兩個用全部季節才抓到的錯誤：技術罰球排在 period_end 列之後（漏掉 1 分）、技術犯規排在 period_start 列之前（產生空回合）。檢查 111 現在會把 `core.known_gaps` 登記的比分衝突列為已知；沒有 pbpstats 資料的季節，檢查 8 略過。
- 和 pbpstats 完全一致：2000-01 → 2015-16 為 97.2–99.3%；**2016-17 起掉到 70–82%**（差 ≤1 仍有 94–98%）。原因主要是「節末空回合」：2016-17 起 pbpstats 不算其中約 515 個（影響約 0.2% 的回合）。我沒有為了數字去改規則，記在 decisions.md，標 [待確認]。

## 2016-17 之後一致率下降的原因（Opus 調查，完成時間 2026-10-21 21:59，等待你決定 1 件事）

- 前一輪的解釋（pbpstats 不算約 515 個空回合）是錯的：原始檔和參考表都有那些回合，是我用「結束時間 + 防守隊」配對時配錯了。改成整場逐一並排對照後找到真正原因。
- **主因：時間精度。**2015-16 以前所有回合的開始時間都是整數秒；2016-17 起來源時間精確到 0.1 秒。我們的節末規則用精確秒數判斷「≤ 2 秒」，剩 2.4 秒開始的 0 分回合會被算進去；pbpstats 用整數秒（2.4 → 2）會排除。每季約 500–560 個。改用整數秒判斷：2016-17 80.3% → 98.2%，2018-19 → 97.9%，2022-23 → 97.3%，2024-25 → 98.6%，2015-16 以前完全不變。這是規則語意，等你決定。
- **修好：**2022-23 → 2024-25 的 transition take 罰球用一般「1 of 1」代碼，只有犯規代碼 31 看得出來，之前連不到犯規，回合被切開。
- **修好：**檢查 8 只比對兩邊都有的比賽，pbpstats 缺的比賽另外列出。
- 試過但撤回：防守方被記失誤時不另開回合（對 2004-05 反而變差）。

## 節末規則維持精確秒數（完成時間 2026-10-21 22:09）

- 你決定維持精確秒數：`rules.yaml` 加上 `end_of_period.clock_precision: exact`（`rules_version 2026-10-21.6`），程式會檢查這個設定；CLAUDE.md 節末規則註明「2016-17 起與 pbpstats 刻意不同（每季約 500–560 個回合）」。
- 全部季節的重建延後，等你說可以再跑（資料庫目前是舊版規則建的；2004-05、2018-19、2022-23、2024-25 是試驗版本）。

## 完整重建完成（2026-10-22 00:17）

- `python -m nba_platform.rebuild`：9 個步驟全部成功、60 個季節 0 個錯誤，共約 2 小時 40 分。`core.stints` 1,161,854、`core.possessions` 7,275,201、`core.possession_stint_segments` 8,128,672；`rules_version 2026-10-21.6`，profile `pbpstats_compat`。
- 檢查 111（硬性）60 個季節全部通過。檢查 8：2000-01 → 2015-16 為 97.2–99.3% 完全一致；2016-17 起 70–83%（精確秒數的刻意差異，差 ≤1 為 94–99%）。transition take 的修正讓 2022-23 → 2024-25 各提高約 5 個百分點。
- 2025-26 例行賽與季後賽、1996-97 → 1999-00 沒有 pbpstats 對照，檢查 8 略過。
- 更新過期文件：CLAUDE.md 目錄圖與 Roadmap（Phase 0–3、5 打勾）、README 狀態與 Roadmap、資料字典與資料模型的列數。
- 待處理：2017-18 例行賽是離群值（70.4%、21 場兩隊差 > 2、159 個 implied 回合），還沒調查；第二層（on/off、陣容）可以開始。

## 2017-18 離群值：部分調查並記錄（2026-10-22 00:32）

- 2017-18 例行賽（70.4% 完全一致、159 個 implied 回合）的原因，約一半可歸因於來源把「事後補登的事件」依時間插進序列，造成事件順序錯亂；證據：53% 的 implied 回合靠近補登事件（一般回合 23%），2017-18 靠近補登事件的回合高達 23%（其他年份 5–18%）。
- 另一半尚未分析；是否為補登事件加入重排規則（會改變「照來源順序」的決定），留待下次你決定。細節在 `docs/decisions.md`。

## 發布到 GitHub（私人儲存庫）（2026-10-22 00:44）

- `mingchen-analytics/nba-analytics-platform`（Private），遠端只有 `main`，一個全新起點 commit（216 個檔案），作者信箱為 GitHub noreply。
- 舊的 75 個 commit 留在本機分支 `main-old-history`，另備份成 `nba-analytics-platform_full_history_2026-10-22.bundle`（專案資料夾旁），都不上傳。
- 購買的 BigDataBall 檔案清單改放本機 `data/raw/manifest_local.csv`（git 忽略），公開的 manifest 只留可下載的來源；加 MIT LICENSE 與 README 的資料說明。
- 發布前掃描：沒有信箱、本機路徑、token、資料檔、來源原文；新歷史裡沒有任何 details 檔。
- 還沒決定：要不要改成公開、Dashboard 要不要公開部署（資料條款）。

## Dashboard 人工檢查發現的資料問題：2025-26 追蹤速度不合理（2026-10-22 01:00）

- 你的截圖顯示 Cooper Flagg 平均速度 12.1 mph、Shaedon Sharpe 15.4 mph。查證：2025-26 例行賽有 44 位球員的 NBA.com 速度／距離異常（最高 22.6 mph，距離約為正常值 2.7 倍），集中在 MIL、DAL、NYK、POR；其他賽季最大值為 5.08 mph。是來源的問題。
- 處理（標記、不刪除）：`marts.player_tracking_season.movement_suspect`（速度 > 5.5 mph 且上場 ≥ 100 分鐘）；新報告 `docs/validation/tracking_quality.md`（各季中位數與標記）；Tracking 頁在 Movement 類別顯示警告並預設隱藏被標記的列。
- 同一份報告也看出：2024-25 起持球時間與觸球的測量尺度改變（來源換了追蹤測量），跨 2023-24 → 2024-25 不可直接比較。
- 教訓：我們的驗證沒有檢查追蹤測量本身的合理範圍，是人工看頁面才發現；已補上。

## 儲存庫改為公開（2026-10-22 01:11）

- `mingchen-analytics/nba-analytics-platform` 改為 Public；公開前再掃描一次（只有 noreply 信箱、5 個 commit、沒有 details 檔／BigDataBall 清單／敏感字串／資料檔）；已設定 description 與 8 個 topics，關閉 wiki 與 projects；匿名連線確認 README 與圖片可讀取。
- Dashboard 的公開部署（資料條款）仍未決定。

## 隔夜：on/off 與陣容 mart（分支 overnight-dev-2026-10-22，2026-10-22 03:26）

- 新增 `marts/onoff.py`：`marts.player_onoff_season`（22,571 列）與 `marts.lineup_stats`（420,946 列），在資料庫快照副本上建置約 15 秒；歸屬方式用 `pbpstats_compat` 混合法（回合算給結束時的陣容，罰球得分算給犯規當下的陣容），A/B/C 仍待你決定。
- 硬檢查全部通過（每個回合有結束 stint、得分守恆、球員回合/得分/秒數 = 5 × 陣容）；報告 `docs/validation/onoff_checks.md`；12 個新測試，全部 276 個測試通過。
- 這是新增資料表（schema 變更），**等你核准才會合併進 main**；還沒有頁面。
- 下載程式同時在主資料庫執行，我只動快照副本。

## 隔夜：2017-18 離群值第二部分（分析，沒有改規則；2026-10-22 03:30）

- 159 個 implied 回合分成 6 類：92 個（58%）靠近來源「事後插入」的事件；其餘 67 個是來源缺事件或事件不在該有的位置（缺籃板列 15、有籃板列但沒結束回合 35、罰球組結尾沒出現 15、其他 2）。
- 用官方 NBA.com 逐筆（shufinskiy nbastats_2017，只看事件類型）核對缺籃板的 15 個：14 個官方檔在同一次不進之後確實有籃板列。
- 結論：第 2–6 類比較像是該寫進 corrections 的來源錯誤，不是重排規則；是否寫入、是否在 custom 加重排規則，等你決定。詳見 docs/decisions.md。

## 隔夜：兩人組合表、A/B 比較、清警告（2026-10-22 03:46）

- 你核准了 on/off、陣容表，以及新的兩人組合表 `marts.pair_stats`（151,672 列；守恆檢查：兩人組合 = 10 × 陣容）。
- A/B 比較（`docs/validation/onoff_credit_methods.md`）：回合數兩種方式相同，只有罰球得分會移動。NBA 換人多半發生在犯規後、罰球前的死球時間，所以有 **548,053 分（7.1%）**會換陣容；球員的 on-off 淨值平均差 1.19（每 100 回合），約四成球員差超過 1 分。**這個選擇影響不小**，仍由你決定（問卷第 4 項）。
- 清掉 dashboard 測試的 120 個 pandas 警告（`data_health.py` 的型別問題）。
