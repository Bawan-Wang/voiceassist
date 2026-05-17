# 測試清單（Smoke / Manual 测试）

目的：
- 提供一組簡短、可人工驗證的範例 utterances，讓 QA/PM/開發能快速確認 routing、local-skill、time-query、以及 chat 行為是否如預期。
- 同時列出常見的 false-positive cases（負例），方便在迭代時檢查回歸。

使用說明：
- 每個案例包含：User Utterance → 預期 Route / Action → 驗證要點 → 自動化測試建議（若適用）。
- 優先以語意自然的說法為主，並包含幾個 command-style 的短句以覆蓋邊界情況。

---

1) 兔兔助理請說笑話
- 範例 utterances：
  - 「兔兔助理，請說個笑話」
  - 「兔兔，講個笑話」
- 預期 route/action：CHAT → assistant 以對話內容回覆笑話（非 local skill）
- 驗證要點：回應為笑話、非啟動任何 UI、且不觸發 open_bunny
- 自動化測試建議：unit test 對 routing_policy 輸入文本應回 CHAT

2) 兔兔助理幫我查今天的天氣
- 範例 utterances：
  - 「兔兔助理，幫我查今天的天氣」
  - 「兔兔，今天會下雨嗎？」
- 預期 route/action：CHAT → 透過 weather skill/API 回應（非 local skill）
- 驗證要點：回應包含當地天氣資訊或明確的 API 呼叫結果，且無 UI 切換
- 自動化測試建議：mock weather provider，確認 routing 決策為 CHAT

3) 兔兔助理請切換相簿
- 範例 utterances：
  - 「兔兔，請切換相簿」
  - 「打開相框」
  - 指令風格："打開相簿" / "切換到相簿模式"
- 預期 route/action：LOCAL_SKILL → open_photoframe
- 驗證要點：觸發相簿相關 action, UI 收到 open_photoframe，assistant 可回覆簡短確認（例如：已打開相簿）
- 自動化測試建議：測試 tokens.matchers 對 command-style phrasing 回傳 true，並測試 negative cases（見下方）

4) 兔兔助理切回兔兔
- 範例 utterances：
  - 「切回兔兔」
  - "切換到兔兔模式" / "回到兔兔畫面"
- 預期 route/action：LOCAL_SKILL → open_bunny
- 驗證要點：執行 open_bunny action，前端或 bridge 接到相應 event
- 自動化測試建議：同上，重點是 command-style phrasing

5) 兔兔助理請問現在幾點
- 範例 utterances：
  - 「兔兔助理，現在幾點？」
  - 「請問現在幾點」
- 預期 route/action：TIME_QUERY → assistant 回傳當前時間（或時區澄清流程）
- 驗證要點：若時區不明確，應啟動澄清；否則直接回時間
- 自動化測試建議：測試 time_query parser 在不同地點/語句下的決策

---

False-positive（要作為 Regression test 的負例）
- 目的：確保一般對話不會被誤判成 local-skill / time-query

A) LOCAL_SKILL false-positive（不應觸發 open_bunny / open_photoframe）
- 測試 utterances：
  - 「你喜歡兔兔嗎？」  → 預期 CHAT（不要 open_bunny）
  - 「兔兔好可愛」       → 預期 CHAT
  - 「相框是什麼？」     → 預期 CHAT（解釋什麼是相框，而不是打開相簿）
  - 「我想看照片展」     → 預期 CHAT（可以延伸成建議，但不要立刻 open_photoframe）
- 驗證要點：tokens matcher 在這些句子上回 false，routing_policy 返回 CHAT

B) TIME_QUERY false-positive（「有沒有空/有時間嗎」語意）
- 測試 utterances：
  - 「我有時間嗎？」     → 預期 CHAT（在台灣中文語境裡通常是詢問 "有沒有空"，而非詢問現在時間）
  - 「請問我有時間嗎？」 → 預期 CHAT
  - 「你有時間嗎？」     → 預期 CHAT
- 驗證要點：time_query parser 不應把這類問句當作 clock/timezone query；如需特殊處理，應先澄清語意

C) 邊界 / 含糊語句
- 測試 utterances：
  - 「時間到了嗎？」     → 可能為 REMINDER 或 TIME_QUERY，視上下文而定（應觸發 disambiguation）
  - 「幫我安排明天早上九點提醒」 → 預期 REMINDER
- 驗證要點：明確命令或帶時間資訊的句子進入 REMINDER，含糊的句子要進一步澄清而非直接執行錯誤路徑

---

Acceptance criteria（驗收準則）
- 上述正向例子皆走到預期 route，並完成對應 action；local-skill 的 command-style phrasing 要能被辨識。
- 上述負例（false-positive）皆不會被誤判成 local-skill 或 time-query，應回 CHAT 或請求澄清。
- 自動化測試覆蓋：在 tests/ 中新增或驗證至少一組正向 + 一組負向測試，並且 CI 維持綠燈。

建議的自動化測試映射
- routing_policy unit tests: 針對每個 utterance 檢查 route （CHAT / LOCAL_SKILL / TIME_QUERY / REMINDER）
- tokens matcher tests: 專注檢查 command-style phrasing（positive）與自然語句（negative）
- end-to-end integration: 在 voice_bridge 的 local routing 測試中，確保 UI action 被正確發出（mock bridge）

---

後續建議
- 當新增 local commands 時，同步把正/負例加到本檔案並在 tests/ 裡新增對應測試。
- 每個 release 前跑一次 smoke list（人工或自動化）以降低回歸風險。


