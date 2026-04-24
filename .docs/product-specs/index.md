# Product Specs Index

This folder contains feature specifications for voiceassist.

When requesting a new feature from an AI agent, create a file here first,
then tell the agent: "請實作 docs/product-specs/xxx.md"

---

## Active Specs

| File | Description |
|------|-------------|
| [`wake-word.md`](wake-word.md) | Wake word variants, 3-tier matching, two-step wake flow, auto-route cooldown |
| [`intent-routing.md`](intent-routing.md) | Routing decision tree, search token list, OpenClaw / GPT-4o-mini behaviour, feature flags |
| [`voice-pipeline.md`](voice-pipeline.md) | STT (SenseVoice), VAD (Silero/WebRTC), TTS (Piper zh-CN), audio config, language support |
| [`ui-states.md`](ui-states.md) | idle/listening/thinking/speaking — triggers, colors, `demo_state.json` contract |
| [`local-commands.md`](local-commands.md) | Photoframe and bunny UI switch — trigger phrases, actions, debounce behaviour |

## How to Write a Spec

Copy this template and fill it in:

```markdown
# Feature: [Name]

## Summary
One sentence describing what this feature does.

## Trigger
What does the user say to activate it?
Example: 「關燈」、「把燈關掉」

## Expected Behaviour
- What should the system do?
- What should the reply_text be?
- Any side effects (GPIO, file write, etc.)?

## Expected API Response
{
  "reply_text": "好的，已幫你關燈。",
  "meta": { "source": "local-command", "action": "gpio_light_off" }
}

## Out of Scope
What this spec does NOT cover.
```
