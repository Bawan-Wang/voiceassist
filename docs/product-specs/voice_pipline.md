# Voice Pipeline — Routing Logic

## Routing Logic (LLM Agent)

Text from STT is routed as follows:

| Input | Route | Timeout |
|-------|-------|---------|
| `"打開相框"` / `"開啟photoframe"` | `open_photoframe()` (local) | — |
| `"打開兔兔"` / `"切回bunny"` | `open_bunny_ui()` (local) | — |
| Contains search tokens (`查`, `搜尋`, `找`, `天氣`, `最新`, `新聞` …) | OpenClaw Agent | 90 s |
| Everything else (General Q&A) | OpenAI GPT-4o-mini | — |
