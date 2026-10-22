# 整夜執行計畫

## 步驟
0. Phase 0：照你剛才提出的計畫執行（加上 commit 和 pyproject.toml）。
1. Phase 1（只做 2004-05 季）：寫 ramirobentes 的 staging adapter，把 games、teams、players、events 載入 DuckDB。執行 CLAUDE.md 驗證清單的第 1、2、3、4、6 項（第 5 項需要 box score，先跳過並註記）。為 adapter 寫 pytest 測試。
   - 檢查點（整季之前）：先只用比賽 0020400027 完整跑過 events、陣容和得分驗證，通過才做整季。
2. Phase 2（只做 2004-05 季）：從 shufinskiy 的 shotdetail 建立 shots 表，執行驗證第 10 項。
3. 擴充到所有賽季：把步驟 1、2 擴充到 1996-97 到 2025-26 的例行賽和季後賽。CLAUDE.md 第 3 條約定在這一步例外，我授權擴充匯入，但不包括回合和 stint。
   - 擴充之前：先檢查 2025-26 季的欄位格式和 2004-05 有什麼不同，把差異寫進報告。
   - 投籃座標：shufinskiy 有的賽季用它；沒有的賽季用 ramirobentes 的 locX/locY
   - 季後賽檔案的命名方式，請先查清楚再下載
   - 每一季的驗證結果整理成 docs/validation/season_report.md（一季一列的表格）
   - 驗證失敗的賽季不要改資料硬讓它通過，列在報告裡就好
4. Phase 3 的準備工作（不寫程式邏輯）：用 2004-05 季的資料，針對 CLAUDE.md 回合規則表的每一種情況：
   - 找出 2–3 個真實的事件序列當範例
   - 統計這種情況整季發生幾次
   - 特別統計「罰球之間換人」的次數和佔比
   - 比較 ramirobentes 的回合數和 shufinskiy 的 pbpstats_2004 回合數，逐場列出差異
   - 統計節末殘局門檻設 2、3、5 秒時，各會排除多少回合
   - 統計 Cleaning the Glass 定義下，垃圾時間的回合佔比
   - 結果寫成 docs/possession_rules.md 的草稿，所有規則維持 proposed，不要替我做決定
5. 寫 docs/overnight_report.md（用中文）：整夜做了什麼、驗證結果、遇到的問題、有哪些需要我決定的事、建議的下一步。

## 每完成一個步驟都要
- 執行 pytest，全部通過才算完成
- git commit，訊息寫清楚做了什麼
- 在 docs/progress_log.md 加一筆紀錄（用中文）：完成時間、做了什麼、新增或修改的檔案、驗證的實際數字、遇到的問題、下一步、預估剩餘時間

## 規則
- 不要問我問題。需要決定時選比較保守的做法，記在 docs/decisions.md 並標記 [待確認]
- 同一個問題試了 3 次還解決不了，就記錄下來，跳到下一個不受影響的步驟
- 絕對不要在 src/nba_platform/core/ 寫任何程式碼
- 不要加 git remote，不要 push
- 不要刪除或修改 data/raw/ 裡的任何檔案
- 不要碰 Basketball Reference
- 除了改名，不要修改 CLAUDE.md 的規則
