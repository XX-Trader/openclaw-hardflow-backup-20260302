#!/usr/bin/env node
import { mkdtemp, mkdir, writeFile, readFile, access } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
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
  const file = path.join(hooksDir, hookName, "handler.ts");
  await mustExist(file);
  const mod = await import(pathToFileURL(file).href);
  if (typeof mod.default !== "function") {
    throw new Error(`invalid handler export: ${file}`);
  }
  return mod.default;
}

async function runNodeScript(scriptFile, args) {
  await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [scriptFile, ...args], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stderr = "";
    child.stderr.on("data", (buf) => {
      stderr += String(buf);
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`script failed(${code}): ${scriptFile}\n${stderr}`));
    });
  });
}

async function main() {
  const { hooksDir, workspace } = parseArgs();
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

  const guard = await importHandler(hooksDir, "hardflow-command-guard");
  const audit = await importHandler(hooksDir, "hardflow-audit");
  const stopReminder = await importHandler(hooksDir, "hardflow-stop-gate-reminder");
  const experienceCapture = await importHandler(hooksDir, "hardflow-experience-capture");
  const experienceRecall = await importHandler(hooksDir, "hardflow-experience-recall");
  const experienceEvolve = await importHandler(hooksDir, "hardflow-experience-evolve");

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

  const sessionFile = path.join(testWorkspace, ".workflow", "sessions", "selftest.jsonl");
  await mkdir(path.dirname(sessionFile), { recursive: true });
  const sessionRows = [
    {
      type: "message",
      message: {
        role: "user",
        content: [{ type: "text", text: "OpenClaw hooks 加载失败，怎么修复？" }],
      },
    },
    {
      type: "message",
      message: {
        role: "assistant",
        content: [
          {
            type: "text",
            text: "根因是 hooks.internal.load.extraDirs 未配置。修复步骤：\n1. 添加 extraDirs\n2. enable hooks\n3. config reload\n验证：openclaw hooks check 通过。",
          },
        ],
      },
    },
  ];
  await writeFile(
    sessionFile,
    `${sessionRows.map((x) => JSON.stringify(x)).join("\n")}\n`,
    "utf8",
  );

  const captureEvent = {
    type: "command",
    action: "stop",
    sessionKey: "selftest-main",
    timestamp: new Date(),
    messages: [],
    context: {
      workspaceDir: testWorkspace,
      sessionEntry: {
        sessionId: "sess-1",
        sessionFile,
      },
      cfg: {
        hooks: {
          internal: {
            entries: {
              "hardflow-experience-capture": {
                enabled: true,
                minMessages: 2,
                messages: 20,
              },
            },
          },
        },
      },
    },
  };
  await experienceCapture(captureEvent);
  const cardsFile = path.join(testWorkspace, ".workflow", "experience", "cards.ndjson");
  await mustExist(cardsFile);
  const cardsRaw = await readFile(cardsFile, "utf8");
  if (!cardsRaw.includes('"sourceAction":"stop"')) {
    throw new Error("hardflow-experience-capture did not persist card");
  }

  await writeFile(
    path.join(testWorkspace, "todo.md"),
    "# todo\n修复 OpenClaw hooks 自动加载与配置重载\n",
    "utf8",
  );
  const bootstrapEvent = {
    type: "agent",
    action: "bootstrap",
    sessionKey: "selftest-main",
    timestamp: new Date(),
    messages: [],
    context: {
      workspaceDir: testWorkspace,
      bootstrapFiles: [],
      cfg: {
        hooks: {
          internal: {
            entries: {
              "hardflow-experience-recall": { enabled: true, topK: 3 },
            },
          },
        },
      },
    },
  };
  await experienceRecall(bootstrapEvent);
  const injected = (bootstrapEvent.context.bootstrapFiles || []).find((x) =>
    String(x.path || "").includes("EXPERIENCE_RECALL.md"),
  );
  if (!injected) {
    throw new Error("hardflow-experience-recall did not inject bootstrap memory");
  }

  const evolveEvent = {
    type: "command",
    action: "stop",
    sessionKey: "selftest-main",
    timestamp: new Date(),
    messages: [],
    context: {
      workspaceDir: testWorkspace,
      sessionEntry: {
        sessionId: "sess-1",
        sessionFile,
      },
    },
  };
  await experienceEvolve(evolveEvent);
  const statsFile = path.join(testWorkspace, ".workflow", "experience", "stats.json");
  const statsRaw = await readFile(statsFile, "utf8");
  const stats = JSON.parse(statsRaw);
  const hasSuccess = Object.values(stats?.cards || {}).some(
    (x) => Number(x?.successCount || 0) >= 1,
  );
  if (!hasSuccess) {
    throw new Error("hardflow-experience-evolve did not update successCount");
  }

  const maintainScript = fileURLToPath(new URL("./experience-maintain.mjs", import.meta.url));
  await runNodeScript(maintainScript, ["--workspace", testWorkspace, "--mode", "daily"]);

  const maintainedCardsRaw = await readFile(cardsFile, "utf8");
  if (!maintainedCardsRaw.includes('"lifecycle":"')) {
    throw new Error("experience-maintain did not write lifecycle metadata");
  }
  const reportFile = path.join(
    testWorkspace,
    ".workflow",
    "experience",
    "maintenance",
    "latest-report.json",
  );
  await mustExist(reportFile);

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
