#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/home/jh-pi/.openclaw/workspace/voiceassist"
PY="$BASE_DIR/.venv/bin/python"
WAKE="${RABBIT_WAKE:-兔兔助理}"
PLAYBACK="${RABBIT_PLAYBACK:-plughw:2,0}"
INPUT_DEVICE="${RABBIT_INPUT_DEVICE:-}"

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
  pkill -9 -f "python ui/assistant_ui.py" || true
  pkill -9 -f "bridge/voice_bridge.py" || true
  pkill -9 -f "uvicorn api.app" || true
  pkill -9 -f "/home/jh-pi/workspace/photoframe/main.py" || true
  pkill -9 -f "run_photoframe.sh" || true
}

status() {
  echo "=== rabbit status ==="
  pgrep -af "uvicorn api.app" || echo "api: stopped"
  pgrep -af "python ui/assistant_ui.py" || echo "bunny_ui: stopped"
  pgrep -af "bridge/voice_bridge.py" || echo "voice_bridge: stopped"
  pgrep -af "/home/jh-pi/workspace/photoframe/main.py" || echo "photoframe: stopped"
}

start() {
  if [[ -z "$OPENAI_API_KEY_VALUE" ]]; then
    echo "ERROR: OPENAI_API_KEY not found (env or ~/.bashrc)"
    exit 1
  fi

  kill_all
  cd "$BASE_DIR"

  OPENAI_API_KEY="$OPENAI_API_KEY_VALUE" ZERO_USE_OPENCLAW_AGENT=1 nohup "$PY" -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --log-level warning >/tmp/assistant_bridge.log 2>&1 &
  DISPLAY=:0 nohup "$PY" ui/assistant_ui.py "$BASE_DIR/config.yaml" >/tmp/bunny_ui.log 2>&1 &
  OPENAI_API_KEY="$OPENAI_API_KEY_VALUE" nohup "$PY" -u bridge/voice_bridge.py --input-device "$INPUT_DEVICE" --playback-device "$PLAYBACK" --wake "$WAKE" >/tmp/voice_bridge.log 2>&1 &

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
    echo "Optional env: RABBIT_WAKE, RABBIT_PLAYBACK, RABBIT_INPUT_DEVICE, OPENAI_API_KEY"
    exit 1
    ;;
esac
