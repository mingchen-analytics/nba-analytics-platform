# 待你決定的事項（2026-10-19 整理）

每一項都附上目前採用的保守做法。決定後我會更新 `docs/decisions.md`，並把 [待確認] 改掉。

## 1. 得分設計：那 2 筆「其他」

兩筆是同一種情況，只用代碼和 ID 描述如下：

| 比賽 | 時間 | 經過 |
|---|---|---|
| `0020400278`（2004-05） | 第 2 節 00:44 | 主隊 NJN 犯規 → 客隊 NOH 兩罰：1 of 2 中、2 of 2 中，NOH 回合結束 → NJN 再犯一次 **away-from-play 犯規**（act 6）→ NOH **加罰 1 球**（event 200）投進 → 下一個動作是 NJN 進攻 |
| `0022400105`（2024-25） | 第 4 節 11:48 | 客隊 DET 犯規 → 主隊 MIA 兩罰：1 of 2 不中、球隊籃板、2 of 2 中，MIA 回合結束 → DET 再犯一次 **loose ball 犯規**（act 3）→ MIA **加罰 1 球**（event 501）投進 → 下一個動作是 DET 進攻 |

**共同點**：回合在最後一罰投進時已經結束，接著在同一個死球時間點又有另一次犯規，讓剛進攻完的那一隊再罰 1 球，之後球權歸對手。這不是技術犯規，但性質很像：發生在兩個回合之間。

**選項**
- **(a) 比照技術犯規**：不開始也不結束回合，得分計入球隊總分，事件加上旗標；陣容效率和 RAPM 預設排除。
- **(b) 算成一個只有罰球的小回合**：這樣罰球得分就歸進攻方，但每隊的回合數會多 1。
- **(c) 併入前一個回合**：剛進攻完的那一隊的回合多 1 分。

**已決定（2026-10-21）：選 (a)**，比照技術犯規，事件旗標 `is_between_possessions_ft`（見 `docs/decisions.md`）。

## 2. BigDataBall 19 個沒對到的名字

不唯一票數 = 那段陣容裡同時有不只一個名字對不上，所以那幾票無法用來判斷。

| 季 | BigDataBall 名字 | 候選 player_id | 我們資料庫的名字 | 支持票數 | 不唯一票數 | 建議 |
|---|---|---|---|---|---|---|
| 2004-05 | Ha Seung-Jin | 2775 | Ha Ha | 590（另 1 票給 2216） | 0 | manual 加入（同一人，寫法不同） |
| 2005-06 | Ronald Murray | 2436 | Flip Murray | 23,689（另 1 票） | 0 | manual 加入 |
| 2007-08 | Charles Hayes | 101236 | Chuck Hayes | 13,899 | 968 | manual 加入 |
| 2010-11 | Charles Hayes | 101236 | Chuck Hayes | 18,602 | 81 | manual 加入 |
| 2007-08 | Michael Harris | 200839 | Mike Harris | 611 | 968 | manual 加入 |
| 2010-11 | Michael Harris | 200839 | Mike Harris | 77 | 81 | manual 加入（票數少，先人工確認） |
| 2013-14 | Michael Harris | 200839 | Mike Harris | 1,227 | 1,006 | manual 加入 |
| 2012-13 | Jose Juan Barea | 200826 | J.J. Barea | 14,614 | 1,784 | manual 加入 |
| 2013-14 | Enes Kanter | 202683 | Enes Freedom | 18,378 | 1,006 | manual 加入（2021 年改名） |
| 2014-15 | Enes Kanter | 202683 | Enes Freedom | 19,427 | 110 | manual 加入 |
| 2013-14 | Glen Rice Jr. | 203318 | Glen Rice | 843 | 199 | manual 加入 |
| 2014-15 | Glen Rice Jr. | 203318 | Glen Rice | 59 | 368 | manual 加入（票數少，先人工確認） |
| 2013-14 | Otto Porter | 203490 | Otto Porter Jr. | 2,970 | 199 | manual 加入 |
| 2014-15 | Otto Porter | 203490 | Otto Porter Jr. | 16,626 | 368 | manual 加入 |
| 2013-14 | Perry Jones | 203103 | Perry Jones III | 7,717（另 1 票） | 0 | manual 加入 |
| 2014-15 | Perry Jones | 203103 | Perry Jones III | 6,032 | 110 | manual 加入 |
| 2007-08 | **Marcus Williams** | 200766 / **201173** | 兩位都叫 Marcus Williams | 8,171 / 380 | 0 | **同名的兩位球員**：只靠名字無法對應，需要「名字 + 球隊」 |
| 2012-13 | **Chris Johnson** | 203187 / **202419** | 兩位都叫 Chris Johnson | 952 / 871 | 1,784 | **同名的兩位球員**：同上 |
| 2013-14 | **Tony Mitchell** | 203502 / **203183** | 兩位都叫 Tony Mitchell | 781 / 81 | 0 | **同名的兩位球員**：同上 |

**建議**：
- 前 16 列以 `manual` 方式加入 `core.player_xref`。
- 最後 3 組同名球員，請我把 BigDataBall 的對照改成「名字 + 球隊 + 季」為鍵，自動區分。

目前什麼都沒有寫入，等你決定。

## 3. 其他 [待確認] 項目

| 項目 | 目前的保守做法 | 要不要改？ |
|---|---|---|
| CTG 垃圾時間：剛好剩 9:00／6:00 | 歸到較低門檻那一段（≥ 20 分／≥ 10 分） | ☑ 維持（2026-10-21） |
| `pbpstats_compat` 的技術犯規罰球 | 已查 pbpstats 原始碼：計入陣容 +/-，算給犯規當下的陣容 | ☑ 設為 false / lineup_at_foul（2026-10-21） |
| `RB_DERIVED_COLUMNS`（ramirobentes 推算欄位清單） | 18 個欄位；`shot_pts` 當成 NBA 原始欄位 | ☐ |
| 每 600 個 NBA.com 請求主動休息的時間 | 30 分鐘 | ☐ |
| matchups 2025-26（`matchups_2025` / `matchups_po_2025`） | 沒抓，範圍維持 2017-18 → 2024-25 | ☐ |
| 投籃品質旗標在之後 marts 的用法 | 只加旗標，沒有排除任何資料 | ☐ |
| 舊 commit 歷史裡的來源原文 | 沒有改寫 git 歷史；push 前要決定 | ☐ |
| 已知缺漏 `0042400231`（2024-25 季後賽） | 比賽列來自 box score，沒有 PBP | ☐ 要不要用其他來源補 PBP？ |
