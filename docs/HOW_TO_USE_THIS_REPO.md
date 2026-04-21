# 如何使用這個 Repo 框架

這份文件教你如何維護和擴充 voiceassist 專案，
包含每個文件的用途，以及如何跟 AI agent 協作。

---

## 📁 重要檔案一覽

| 檔案 / 資料夾 | 用途 | 誰會讀它 |
|--------------|------|---------|
| `AGENTS.md` | AI agent 的工作規則（不要自己 commit、要跑測試等）| AI |
| `ARCHITECTURE.md` | 系統架構圖和元件說明 | AI + 你 |
| `docs/tech-debt.md` | 已知問題和待改清單 | AI + 你 |
| `docs/product-specs/` | 新功能規格書 | AI + 你 |
| `tests/` | 自動化測試（pytest） | AI + CI |
| `tests/fixtures/cases.json` | 測試案例清單 | AI |

---

## 🚀 你想加新功能時，這樣做

### 步驟 1：寫 spec

在 `docs/product-specs/` 新增一個 `.md` 檔案，參考這個範本：

```markdown
# Feature: 關燈控制

## Summary
說「關燈」，系統透過 GPIO 關閉燈，並語音回覆確認。

## Trigger
使用者說：「關燈」、「把燈關掉」、「燈關掉」

## Expected Behaviour
- 呼叫 GPIO 關閉 pin 18
- reply_text 回傳「好的，已幫你關燈。」

## Expected API Response
{
  "reply_text": "好的，已幫你關燈。",
  "meta": { "source": "local-command", "action": "gpio_light_off" }
}
```

### 步驟 2：跟 AI 說

```
請實作 docs/product-specs/gpio-light.md
```

AI 會：
1. 讀 spec
2. 讀 `ARCHITECTURE.md` 了解現有架構
3. 寫 code
4. 寫測試
5. 跑 `pytest` 給你看結果
6. **等你說「commit」才會 commit**

---

## 🧪 跑測試

```bash
cd /home/jh-pi/.openclaw/workspace/voiceassist

# 安裝測試套件（只需要做一次）
.venv/bin/python -m pip install -r requirements-dev.txt

# 跑全部測試
.venv/bin/python -m pytest tests/ -v

# 只跑 API 測試
.venv/bin/python -m pytest tests/test_api.py -v

# 看覆蓋率
.venv/bin/python -m pytest tests/ --cov=api --cov=bridge --cov-report=term-missing
```

測試輸出長這樣：
```
tests/test_api.py::TestLocalCommands::test_open_photoframe   PASSED
tests/test_api.py::TestLocalCommands::test_empty_input_returns_400  PASSED
tests/test_intent.py::TestIsSearchIntent::test_search_tokens[你好-False]  PASSED
...
5 passed in 1.2s
```

---

## 🐛 發現 Bug 時，這樣做

### 方式 A：直接跟 AI 說

```
api/app.py 裡面有個 bug，說「新竹天氣」的時候回的是台北的天氣
```

### 方式 B：先記錄在 tech-debt，之後再修

編輯 `docs/tech-debt.md`，加一行到 **Active** 區塊：

```markdown
### LOW — 新竹天氣查到台北
- **File:** `api/app.py`
- **Issue:** city_map 沒有新竹
- **Fix:** 改成用 openclaw agent 查
```

然後跟 AI 說：「去修 tech-debt.md 裡面的新竹天氣問題」

---

## 📋 新增測試案例

編輯 `tests/fixtures/cases.json`，加一個 JSON 物件：

```json
{
  "id": "weather_hsinchu",
  "input": "新竹今天天氣",
  "expected_source": "openclaw-agent",
  "expected_search": true,
  "description": "新竹天氣應該走 openclaw-agent"
}
```

然後跟 AI 說：「幫我把 cases.json 裡的測試案例都補進 test_api.py」

---

## 🔄 一般工作流程總覽

```
你想加功能
  → 寫 docs/product-specs/xxx.md
  → 跟 AI 說「實作這個 spec」
  → AI 寫 code + 寫測試
  → AI 跑 pytest，給你看結果
  → 你確認沒問題
  → 你說「重啟測試」→ AI 重啟服務
  → 你實際測試
  → 你說「commit」→ AI commit
  → 你說「push」→ AI push
```

---

## ❓ 常見問題

**Q: 我不用寫 spec 也可以嗎？**  
A: 可以，直接跟 AI 說需求也行。Spec 的好處是讓你自己思考清楚「我要什麼」，減少來回修改。

**Q: 測試會不會真的呼叫 openclaw 消耗 quota？**  
A: 不會。`conftest.py` 已經把 `subprocess.run` 和 `OpenAI` 都 mock 掉了，測試完全離線執行。

**Q: AI 說「測試 pass」就一定沒問題嗎？**  
A: 測試只驗證已定義的行為。新功能的邊界情況還是要你實際說話測試一次。

**Q: `Silero VAD` 模型是不是要放進 repo？**  
A: 不用。現在第一次執行 `voice_bridge.py` 會自動下載到 `models/silero_vad.onnx`，`models/` 已被 gitignore。
