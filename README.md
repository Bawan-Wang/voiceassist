# Zero Voice Display + Audio Bridge

這個專案包含兩個部分：

1. **PyGame 兔兔 UI (`main.py`)**：顯示 Zero 的臉、phase 動畫（傾聽時耳朵豎起、說話時嘴巴律動）以及最新一輪對話文字。
2. **語音橋接程式 (`voice_bridge.py`)**：接上麥克風/喇叭，使用 OpenAI Whisper + GPT-4o + TTS 讓 Zero 真的能「聽你說→想→講」。

`data/demo_state.json` 是兩者之間的共享狀態。任何寫入這個 JSON 的程式都能驅動 UI。

## 1. 安裝依賴

```bash
cd /home/jh-pi/.openclaw/workspace/voice_display
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> 第一次使用麥克風可能需要 `sudo apt install portaudio19-dev libportaudio2`。

建立 `.env` 或 `export OPENAI_API_KEY=...` 以便語音橋接程式打 OpenAI API。

## 2. 啟動兔兔 UI

```bash
source .venv/bin/activate
python main.py  # or DISPLAY=:0 python main.py on the Pi display
```

可在 `config.yaml` 調整解析度、顏色、全螢幕。`data/demo_state.json` 結構：

```json
{
  "phase": "speaking",
  "userText": "Hi Zero",
  "assistantText": "嗨，我在這裡。",
  "lastUpdate": "2026-03-17T23:00:00+08:00"
}
```

## 3. 語音橋接 (`voice_bridge.py`)

功能：
- 以 WebRTC VAD 偵測語音，呼叫 OpenAI Whisper (`gpt-4o-transcribe`).
- 強制喚醒詞「兔兔助理」（可改）；若同一句包含指令，會把喚醒詞之後的文字當成命令。
- 使用 `gpt-4o-mini` 生成人性化回應，並用 `gpt-4o-mini-tts` 女聲（`voice=verse`）。
- 同步更新 `data/demo_state.json`，讓 UI 顯示傾聽/思考/說話 phase 與文字。

啟動：

```bash
source .venv/bin/activate
OPENAI_API_KEY=sk-... \
python voice_bridge.py \
  --input-device 2 \            # arecord -l 查看 USB speakerphone 的卡號
  --playback-device plughw:2,0 \ # aplay -l 對應輸出裝置
  --wake "兔兔助理" \             # 可改成別的喚醒詞
  --voice verse                  # OpenAI TTS 聲線，可換 coral / lily / etc.
```

程式啟動後的流程：
1. 閒置時 phase=idle，兔兔臉保持平靜。
2. 聽到說話 → phase=listening，耳朵豎起、文字顯示「Zero 正在傾聽中」。
3. 偵測到喚醒詞 + 指令 → phase=thinking，顯示你說的內容。
4. LLM 出結果 → phase=speaking，嘴巴動畫 + 女聲播放。
5. 播放結束 → phase=idle 等下一次喚醒。

## 4. 後續擴充點子

- **自訂指令**：在 `voice_bridge.py` 裡面攔截特定關鍵字（例：天氣）去呼叫其他腳本 (`/home/jh-pi/workspace/weather/weather.py`) 再把結果餵進 LLM。
- **systemd 自動啟動**：分別為 UI、語音橋接建立 `systemd --user` 服務，登入後自動開機。
- **多語提示**：目前系統提示鼓勵中英雙語，若要固定英文/中文可修改 `generate_reply()` 的 system prompt。
- **嘴巴動畫**：在 `main.py` 可調整正弦頻率或張嘴幅度，讓說話更活潑。

有需要我可以再幫你把語音橋接包成服務或加上調試工具。💬🎙️🐇
