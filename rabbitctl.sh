#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/home/jh-pi/.openclaw/workspace/voiceassist"
PY="$BASE_DIR/.venv/bin/python"
CONFIG_PATH="${RABBIT_CONFIG:-$BASE_DIR/config.yaml}"

readarray -t CONFIG_DEFAULTS < <("$PY" - <<'PY' "$CONFIG_PATH"
import sys
from pathlib import Path
import yaml

config_path = Path(sys.argv[1])
cfg = {}
if config_path.exists():
  cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
voice = cfg.get("voiceBridge", {})
audio = voice.get("audio", {})
wake = voice.get("wake", {})
print(wake.get("primary", "兔兔助理"))
print(audio.get("playback_device", "plughw:2,0"))
input_device = audio.get("input_device")
print("" if input_device is None else input_device)
PY
)

WAKE="${RABBIT_WAKE:-${CONFIG_DEFAULTS[0]:-兔兔助理}}"
PLAYBACK="${RABBIT_PLAYBACK:-${CONFIG_DEFAULTS[1]:-plughw:2,0}}"
INPUT_DEVICE="${RABBIT_INPUT_DEVICE:-${CONFIG_DEFAULTS[2]:-}}"

# Auto-detect pulse device index if not manually set
if [[ -z "$INPUT_DEVICE" ]]; then
  INPUT_DEVICE="$("$PY" -c "
import sounddevice as sd
for i, d in enumerate(sd.query_devices()):
    if d['max_input_channels'] > 0 and 'pulse' in d['name'].lower():
        try:
            sd.check_input_settings(device=i, samplerate=16000, channels=1, dtype='int16')
            print(i); break
        except: pass
" 2>/dev/null)"
  INPUT_DEVICE="${INPUT_DEVICE:-1}"  # fallback to 1 if detection fails
fi
OPENAI_API_KEY_VALUE="${OPENAI_API_KEY:-}"

if [[ -z "$OPENAI_API_KEY_VALUE" && -f "$HOME/.bashrc" ]]; then
  # best-effort read from bashrc export line
  OPENAI_API_KEY_VALUE="$(grep -E 'OPENAI_API_KEY\s*=\s*"' "$HOME/.bashrc" | sed -E 's/.*OPENAI_API_KEY\s*=\s*"([^"]+)".*/\1/' | tail -n1 || true)"
fi

kill_all() {
  pkill -9 -f "python src/ui/assistant_ui.py" || true
  pkill -9 -f "src.bridge.voice_bridge" || true
  pkill -9 -f "uvicorn src.api.app" || true
  pkill -9 -f "/home/jh-pi/workspace/photoframe/main.py" || true
  pkill -9 -f "run_photoframe.sh" || true
}

status() {
  echo "=== rabbit status ==="
  pgrep -af "uvicorn src.api.app" || echo "api: stopped"
  pgrep -af "python src/ui/assistant_ui.py" || echo "bunny_ui: stopped"
  pgrep -af "src.bridge.voice_bridge" || echo "voice_bridge: stopped"
  pgrep -af "/home/jh-pi/workspace/photoframe/main.py" || echo "photoframe: stopped"
}

start() {
  if [[ -z "$OPENAI_API_KEY_VALUE" ]]; then
    echo "ERROR: OPENAI_API_KEY not found (env or ~/.bashrc)"
    exit 1
  fi

  kill_all
  cd "$BASE_DIR"
  export PYTHONPATH="$BASE_DIR"

  voice_args=(--config "$CONFIG_PATH" --playback-device "$PLAYBACK" --wake "$WAKE")
  if [[ -n "$INPUT_DEVICE" ]]; then
    voice_args+=(--input-device "$INPUT_DEVICE")
  fi

  OPENAI_API_KEY="$OPENAI_API_KEY_VALUE" ZERO_USE_OPENCLAW_AGENT=1 nohup "$PY" -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --log-level warning >/tmp/assistant_bridge.log 2>&1 &
  DISPLAY=:0 nohup "$PY" src/ui/assistant_ui.py "$BASE_DIR/config.yaml" >/tmp/bunny_ui.log 2>&1 &
  OPENAI_API_KEY="$OPENAI_API_KEY_VALUE" nohup "$PY" -u -m src.bridge.voice_bridge "${voice_args[@]}" >/tmp/voice_bridge.log 2>&1 &

  sleep 1
  echo "Rabbit started."
  status
}

stop() {
  kill_all
  echo "Rabbit stopped."
  status
}

restart() {
  stop
  start
}

cmd="${1:-}"
case "$cmd" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  status) status ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    echo "Optional env: RABBIT_CONFIG, RABBIT_WAKE, RABBIT_PLAYBACK, RABBIT_INPUT_DEVICE, OPENAI_API_KEY"
    exit 1
    ;;
esac
