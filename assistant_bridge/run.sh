#!/bin/bash
# Simple runner for the assistant bridge
cd "$(dirname "$0")"
. .venv/bin/activate 2>/dev/null || true
exec uvicorn assistant_bridge.app:app --host 127.0.0.1 --port 8000 --log-level warning
