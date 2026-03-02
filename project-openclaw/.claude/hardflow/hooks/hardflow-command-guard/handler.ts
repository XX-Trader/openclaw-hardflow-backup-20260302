import { access } from "node:fs/promises";
import path from "node:path";

export default async function hardflowCommandGuard(event: any): Promise<void> {
  if (event?.type !== "command") {
    return;
  }
  if (event?.action !== "new" && event?.action !== "reset") {
    return;
  }

  const workspaceDir = event?.context?.workspaceDir || process.cwd();
  const homeDir = process.env.HOME || "";
  const sharedPolicyDir = process.env.OPENCLAW_POLICY_ROOT || path.join(homeDir, ".openclaw", "ops", "policy");
  const required = [
    "todo.md",
    "done.md",
    "scripts/hardflow/hardflow-v1.lobster.yaml",
    "scripts/hardflow/score-policy.json",
    "scripts/hardflow/check-score-gate.mjs",
  ];
  const requiredPolicyFallback = [
    {
      local: "scripts/openclaw-ops/policy/policy_enforcer.py",
      shared: path.join(sharedPolicyDir, "policy_enforcer.py"),
    },
    {
      local: "scripts/openclaw-ops/policy/policy-config.json",
      shared: path.join(sharedPolicyDir, "policy-config.json"),
    },
    {
      local: "scripts/openclaw-ops/policy/routing-rules.json",
      shared: path.join(sharedPolicyDir, "routing-rules.json"),
    },
    {
      local: "scripts/openclaw-ops/policy/token-pricing.json",
      shared: path.join(sharedPolicyDir, "token-pricing.json"),
    },
  ];

  const missing: string[] = [];
  for (const rel of required) {
    try {
      await access(path.join(workspaceDir, rel));
    } catch {
      missing.push(rel);
    }
  }

  for (const item of requiredPolicyFallback) {
    const workspacePolicy = path.join(workspaceDir, item.local);
    try {
      await access(workspacePolicy);
      continue;
    } catch {}
    try {
      await access(item.shared);
      continue;
    } catch {}
    missing.push(`${item.local} (or ${item.shared})`);
  }

  if (missing.length === 0) {
    event.messages.push("[HardFlow Guard] workflow core files are ready.");
    return;
  }

  event.messages.push(
    [
      "[HardFlow Guard] required files are missing.",
      `missing: ${missing.join(", ")}`,
      "Please restore these files before starting the hardflow pipeline.",
    ].join("\n"),
  );
}
