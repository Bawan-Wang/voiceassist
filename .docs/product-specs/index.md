# Product Specs Index

This folder contains feature specifications for voiceassist.

When requesting a new feature from an AI agent, create a file here first,
then tell the agent: "請實作 docs/product-specs/xxx.md"

---

## Active Specs

*(none yet — add a .md file here when you have a new feature in mind)*

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
