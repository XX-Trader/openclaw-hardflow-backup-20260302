import { access } from "node:fs/promises";
import path from "node:path";

async function fileExists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

/**
 * Validate the HardFlow workspace files before /new or /reset commands run.
 *
 * @param {any} event OpenClaw command hook event. `event.messages` should be an array when present.
 * @returns {Promise<void>} Resolves after appending a readiness or block message.
 * @throws {Error} Propagates filesystem errors only when the guard cannot read required files.
 */
export default async function hardflowCommandGuard(event) {
  if (event?.type !== "command") {
    return;
  }
  if (event?.action !== "new" && event?.action !== "reset") {
    return;
  }

  const messages = Array.isArray(event?.messages) ? event.messages : [];
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
      local: "skills/library/control-plane-ops/scripts/policy/policy_enforcer.py",
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

  const missing = [];
  for (const relPath of required) {
    if (!(await fileExists(path.join(workspaceDir, relPath)))) {
      missing.push(relPath);
    }
  }

  for (const item of requiredPolicyFallback) {
    const workspacePolicyPath = path.join(workspaceDir, item.local);
    if (await fileExists(workspacePolicyPath)) {
      continue;
    }
    if (await fileExists(item.shared)) {
      continue;
    }
    missing.push(`${item.local} (or ${item.shared})`);
  }

  if (missing.length === 0) {
    messages.push("[HardFlow Guard] workflow core files are ready.");
    return;
  }

  messages.push(
    [
      "[HardFlow Guard] required files are missing.",
      `missing: ${missing.join(", ")}`,
      "Please restore these files before starting the hardflow pipeline.",
    ].join("\n"),
  );
}
