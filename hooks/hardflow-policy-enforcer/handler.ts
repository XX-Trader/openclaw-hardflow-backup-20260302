import { spawnSync } from "node:child_process";
import { access } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

async function ensureFile(filePath: string): Promise<void> {
  try {
    await access(filePath);
  } catch {
    throw new Error(`missing policy runtime file: ${filePath}`);
  }
}

type RuntimeFiles = {
  policyPy: string;
  dbPath: string;
  policyFile: string;
  routingFile: string;
  pricingFile: string;
};

function resolveEntryAgent(event: any): string {
  const candidates = [
    event?.context?.agentId,
    event?.context?.targetAgentId,
    event?.context?.receiverAgentId,
    event?.context?.bindingAgentId,
    event?.agentId,
    process.env.POLICY_ENTRY_AGENT,
  ];
  for (const item of candidates) {
    const value = String(item || "").trim();
    if (value) {
      return value;
    }
  }
  return "coordinator";
}

function runPolicy(cwd: string, runtime: RuntimeFiles, commandArgs: string[]): string {
  const policyPy = runtime.policyPy;
  const dbPath = runtime.dbPath;
  const policyFile = runtime.policyFile;
  const routingFile = runtime.routingFile;
  const pricingFile = runtime.pricingFile;

  const args = [
    policyPy,
    "--db",
    dbPath,
    "--policy-file",
    policyFile,
    "--routing-file",
    routingFile,
    "--pricing-file",
    pricingFile,
    ...commandArgs,
  ];

  const pythonCandidates = [process.env.POLICY_PYTHON_BIN || "python3", "python"];
  let lastDetail = "unknown error";

  for (const bin of pythonCandidates) {
    const result = spawnSync(bin, args, {
      cwd,
      encoding: "utf8",
    });

    if (result.status === 0) {
      return (result.stdout || "").trim();
    }

    const stderr = (result.stderr || "").trim();
    const stdout = (result.stdout || "").trim();
    const spawnErr = result.error ? String(result.error.message || result.error) : "";
    lastDetail = stderr || stdout || spawnErr || `status=${result.status}`;

    // If interpreter exists but command failed, do not continue to hide the actual policy error.
    if (!spawnErr) {
      throw new Error(`policy command failed: ${bin} ${args.join(" ")} | ${lastDetail}`);
    }
  }

  throw new Error(`policy command failed: ${pythonCandidates[0]} ${args.join(" ")} | ${lastDetail}`);
}

export default async function hardflowPolicyEnforcer(event: any): Promise<void> {
  if (event?.type !== "command") {
    return;
  }

  const action = String(event?.action || "");
  if (action !== "new" && action !== "reset" && action !== "stop") {
    return;
  }

  const workspaceDir = event?.context?.workspaceDir || process.cwd();
  const strict = (process.env.POLICY_HOOK_STRICT || "1") !== "0";

  const homeDir = process.env.HOME || "";
  const openclawHome = process.env.OPENCLAW_HOME || path.join(homeDir, ".openclaw");
  const taskCenterDir = process.env.TASK_CENTER_DIR || path.join(openclawHome, "ops", "task-center");
  const sharedPolicyDir = process.env.OPENCLAW_POLICY_ROOT || path.join(openclawHome, "ops", "policy");
  const workspacePolicyDir = path.join(workspaceDir, "scripts", "openclaw-ops", "policy");

  const runtime: RuntimeFiles = {
    policyPy:
      process.env.POLICY_ENFORCER_PY ||
      (existsSync(path.join(workspacePolicyDir, "policy_enforcer.py"))
        ? path.join(workspacePolicyDir, "policy_enforcer.py")
        : path.join(sharedPolicyDir, "policy_enforcer.py")),
    dbPath: process.env.POLICY_DB_FILE || path.join(taskCenterDir, "task_center.db"),
    policyFile:
      process.env.POLICY_FILE ||
      (existsSync(path.join(workspacePolicyDir, "policy-config.json"))
        ? path.join(workspacePolicyDir, "policy-config.json")
        : path.join(sharedPolicyDir, "policy-config.json")),
    routingFile:
      process.env.POLICY_ROUTING_FILE ||
      (existsSync(path.join(workspacePolicyDir, "routing-rules.json"))
        ? path.join(workspacePolicyDir, "routing-rules.json")
        : path.join(sharedPolicyDir, "routing-rules.json")),
    pricingFile:
      process.env.POLICY_PRICING_FILE ||
      process.env.TOKEN_PRICING_FILE ||
      (existsSync(path.join(workspacePolicyDir, "token-pricing.json"))
        ? path.join(workspacePolicyDir, "token-pricing.json")
        : path.join(sharedPolicyDir, "token-pricing.json")),
  };

  try {
    await ensureFile(runtime.policyPy);
    await ensureFile(runtime.policyFile);
    await ensureFile(runtime.routingFile);
    await ensureFile(runtime.pricingFile);

    runPolicy(workspaceDir, runtime, ["init"]);
    runPolicy(workspaceDir, runtime, ["validate-runtime"]);

    if (action === "new" || action === "reset") {
      const entryAgent = resolveEntryAgent(event);
      runPolicy(workspaceDir, runtime, ["assert-entry", "--entry-agent", entryAgent]);
      if (Array.isArray(event.messages)) {
        event.messages.push(`[Policy Enforcer] entry_agent=${entryAgent} passed`);
      }
    }

    if (action === "stop") {
      runPolicy(workspaceDir, runtime, ["assert-stop-safe"]);
    }

    if (Array.isArray(event.messages)) {
      event.messages.push(`[Policy Enforcer] action=${action} passed`);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (Array.isArray(event.messages)) {
      event.messages.push(`[Policy Enforcer] blocked: ${message}`);
    }
    if (strict) {
      throw err;
    }
  }
}
