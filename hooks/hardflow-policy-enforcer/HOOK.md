---
name: hardflow-policy-enforcer
description: Hard-block workflow start/stop when policy checks fail.
metadata: { "openclaw": { "emoji": "⛔", "events": ["command:new", "command:reset", "command:stop"] } }
---

# HardFlow Policy Enforcer

Fail-close policy guard:

1. Verify policy runtime files exist.
2. Initialize task-center schema.
3. On `command:new/reset`, enforce entry agent allowlist.
4. On `command:stop`, block if unresolved tasks exist.
5. Throw errors in strict mode to stop command flow.
