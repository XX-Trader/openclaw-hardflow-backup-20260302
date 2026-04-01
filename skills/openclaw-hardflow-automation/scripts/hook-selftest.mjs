#!/usr/bin/env node
import { mkdtemp, mkdir, writeFile, readFile, access } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

function parseArgs() {
  const args = process.argv.slice(2);
  const out = {
    hooksDir: path.join(os.homedir(), ".claude", "hooks"),
    workspace: "",
  };

  for (let i = 0; i < args.length; i += 1) {
    if (args[i] === "--hooks-dir") {
      out.hooksDir = args[i + 1] || out.hooksDir;
      i += 1;
      continue;
    }
    if (args[i] === "--workspace") {
      out.workspace = args[i + 1] || out.workspace;
      i += 1;
    }
  }

  return out;
}

async function mustExist(file) {
  try {
    await access(file, fsConstants.F_OK);
  } catch {
    throw new Error(`required file missing: ${file}`);
  }
}

async function importHandler(hooksDir, hookName) {
  const candidateFiles = ["handler.js", "index.js", "handler.ts", "index.ts"];
  let file = "";
  for (const candidate of candidateFiles) {
    const candidatePath = path.join(hooksDir, hookName, candidate);
    try {
      await mustExist(candidatePath);
      file = candidatePath;
      break;
    } catch {
      continue;
    }
  }
  if (!file) {
    throw new Error(`required handler file missing: ${path.join(hooksDir, hookName)}`);
  }
  const mod = await import(pathToFileURL(file).href);
  if (typeof mod.default !== "function") {
    throw new Error(`invalid handler export: ${file}`);
  }
  return mod.default;
}

async function main() {
  const { hooksDir, workspace } = parseArgs();
  const hardflowDir = path.dirname(fileURLToPath(import.meta.url));
  const policyScriptPath = path.resolve(
    hardflowDir,
    "..",
    "openclaw-ops",
    "policy",
    "policy_enforcer.py",
  );
  const testWorkspace =
    workspace && workspace.trim().length > 0
      ? workspace
      : await mkdtemp(path.join(os.tmpdir(), "hardflow-hook-selftest-"));

  await mkdir(path.join(testWorkspace, "scripts", "hardflow"), { recursive: true });
  await writeFile(path.join(testWorkspace, "todo.md"), "# todo\n", "utf8");
  await writeFile(path.join(testWorkspace, "done.md"), "# done\n", "utf8");
  await writeFile(
    path.join(testWorkspace, "scripts", "hardflow", "hardflow-v1.lobster.yaml"),
    "name: test\n",
    "utf8",
  );
  await writeFile(
    path.join(testWorkspace, "scripts", "hardflow", "score-policy.json"),
    "{\"version\":\"2.0.0\"}\n",
    "utf8",
  );
  await writeFile(
    path.join(testWorkspace, "scripts", "hardflow", "check-score-gate.mjs"),
    "console.log('ok');\n",
    "utf8",
  );
  await mkdir(path.join(testWorkspace, "scripts", "openclaw-ops", "policy"), { recursive: true });
  await writeFile(
    path.join(testWorkspace, "scripts", "openclaw-ops", "policy", "policy-config.json"),
    JSON.stringify(
      {
        primary_model: "kimicode/Doubao-Seed-2.0-Code",
        allowed_models: ["kimicode/Doubao-Seed-2.0-Code", "glmcode/glm-5", "glmcode/glm-4.7"],
        status_flow: {
          pending: ["running", "cancelled", "escalated"],
          running: ["running", "passed", "failed", "escalated", "cancelled"],
          failed: ["running", "escalated", "cancelled"],
          escalated: ["running", "cancelled", "passed"],
          passed: [],
          cancelled: [],
        },
      },
      null,
      2,
    ) + "\n",
    "utf8",
  );
  await writeFile(
    path.join(testWorkspace, "scripts", "openclaw-ops", "policy", "routing-rules.json"),
    JSON.stringify({ version: "test", high_risk_keywords: [], low_risk_keywords: [] }, null, 2) + "\n",
    "utf8",
  );
  await writeFile(
    path.join(testWorkspace, "scripts", "openclaw-ops", "policy", "token-pricing.json"),
    JSON.stringify(
      {
        models: {
          "glmcode/glm-5": { input: 0, output: 0 },
          "kimicode/Doubao-Seed-2.0-Code": { input: 0, output: 0 },
          "glmcode/glm-4.7": { input: 0, output: 0 },
        },
      },
      null,
      2,
    ) + "\n",
    "utf8",
  );

  const guard = await importHandler(hooksDir, "hardflow-command-guard");
  const audit = await importHandler(hooksDir, "hardflow-audit");
  const stopReminder = await importHandler(hooksDir, "hardflow-stop-gate-reminder");
  const policyEnforcer = await importHandler(hooksDir, "hardflow-policy-enforcer");

  const guardEvent = {
    type: "command",
    action: "new",
    sessionKey: "selftest-session",
    timestamp: new Date(),
    messages: [],
    context: { workspaceDir: testWorkspace },
  };
  await guard(guardEvent);
  if (!guardEvent.messages.join("\n").includes("HardFlow Guard")) {
    throw new Error("hardflow-command-guard did not produce expected message");
  }

  const auditEvent = {
    type: "command",
    action: "reset",
    sessionKey: "selftest-session",
    timestamp: new Date(),
    messages: [],
    context: { workspaceDir: testWorkspace, commandSource: "selftest", senderId: "tester" },
  };
  await audit(auditEvent);

  const auditLog = path.join(testWorkspace, ".workflow", "hook-audit", "commands.log");
  const auditRaw = await readFile(auditLog, "utf8");
  if (!auditRaw.includes('"action":"reset"')) {
    throw new Error("hardflow-audit did not write expected command log");
  }

  const gateDir = path.join(testWorkspace, ".workflow", "gates");
  await mkdir(gateDir, { recursive: true });
  const gatePassed = '{"passed":true}';
  await writeFile(path.join(gateDir, "tester.json"), gatePassed, "utf8");
  await writeFile(path.join(gateDir, "reviewer.json"), '{"passed":false}', "utf8");
  await writeFile(path.join(gateDir, "api_doc.json"), gatePassed, "utf8");
  await writeFile(path.join(gateDir, "score_requirements.json"), gatePassed, "utf8");
  await writeFile(path.join(gateDir, "score_solution.json"), gatePassed, "utf8");
  await writeFile(path.join(gateDir, "score_frontend.json"), gatePassed, "utf8");
  await writeFile(path.join(gateDir, "score_backend.json"), gatePassed, "utf8");
  await writeFile(path.join(gateDir, "score_security.json"), gatePassed, "utf8");
  await writeFile(path.join(gateDir, "quality_gate_predeploy.json"), gatePassed, "utf8");

  const stopEventBlocked = {
    type: "command",
    action: "stop",
    sessionKey: "selftest-session",
    timestamp: new Date(),
    messages: [],
    context: { workspaceDir: testWorkspace },
  };
  await stopReminder(stopEventBlocked);
  if (!stopEventBlocked.messages.join("\n").includes("unresolved gate constraints")) {
    throw new Error("hardflow-stop-gate-reminder missing unresolved message");
  }

  await writeFile(path.join(gateDir, "reviewer.json"), '{"passed":true}', "utf8");
  const stopEventPassed = {
    type: "command",
    action: "stop",
    sessionKey: "selftest-session",
    timestamp: new Date(),
    messages: [],
    context: { workspaceDir: testWorkspace },
  };
  await stopReminder(stopEventPassed);
  if (!stopEventPassed.messages.join("\n").includes("all required gates are passed")) {
    throw new Error("hardflow-stop-gate-reminder missing passed message");
  }

  const policyEvent = {
    type: "command",
    action: "new",
    sessionKey: "selftest-session",
    timestamp: new Date(),
    messages: [],
    context: { workspaceDir: testWorkspace },
  };
  process.env.POLICY_ENFORCER_PY = policyScriptPath;
  await policyEnforcer(policyEvent);
  if (!policyEvent.messages.join("\n").includes("Policy Enforcer")) {
    throw new Error("hardflow-policy-enforcer did not produce expected message");
  }

  console.log("[hook-selftest] ok");
  console.log(`[hook-selftest] workspace=${testWorkspace}`);
  console.log(`[hook-selftest] hooksDir=${hooksDir}`);
}

main().catch((err) => {
  const message = err instanceof Error ? err.stack || err.message : String(err);
  console.error("[hook-selftest] failed");
  console.error(message);
  process.exit(1);
});
