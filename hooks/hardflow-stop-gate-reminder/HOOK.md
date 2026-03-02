---
name: hardflow-stop-gate-reminder
description: Check unresolved HardFlow gates when /stop is triggered.
metadata: { "openclaw": { "emoji": "🔍", "events": ["command:stop"] } }
---

# HardFlow Stop Gate Reminder

Reads `.workflow/gates/*.json` and warns if required score/quality gates are missing or failed.
