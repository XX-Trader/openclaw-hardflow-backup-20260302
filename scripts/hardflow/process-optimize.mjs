#!/usr/bin/env node
import { spawn } from "node:child_process";
import { constants as fsConstants } from "node:fs";
import { access, appendFile, mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const MODE_LOOKBACK_DAYS = {
  daily: 7,
  weekly: 21,
  monthly: 60,
};

const STATUS_SCORE = {
  pass: 1,
  warn: 0.6,
  fail: 0,
  skip: 0.5,
};

const CHECK_WEIGHTS = {
  code_test: 0.2,
  peer_review: 0.15,
  acceptance: 0.2,
  deploy_release: 0.15,
  post_deploy_validation: 0.1,
  ops_readiness: 0.1,
  code_hygiene: 0.1,
};

const SOURCE_FILE_EXT = new Set([
  ".js",
  ".ts",
  ".mjs",
  ".cjs",
  ".py",
  ".sh",
  ".go",
  ".rs",
  ".java",
  ".kt",
  ".php",
  ".rb",
  ".cpp",
  ".cc",
  ".c",
  ".h",
  ".hpp",
]);

const SKIP_DIR_NAMES = new Set([
  ".git",
  "node_modules",
  ".next",
  ".nuxt",
  "dist",
  "build",
  ".venv",
  "venv",
  "__pycache__",
  ".idea",
  ".vscode",
]);

const SKIP_PATH_PREFIXES = [
  ".workflow",
  ".workflow/runs",
  ".workflow/tmp-hook-selftest",
  ".workflow/tmp-hook-selftest-v2",
];

const BACKUP_FILE_RE =
  /(\.bak$|\.backup$|\.backup\.[^./]+$|\.old$|\.orig$|\.rej$|\.tmp$|\.current_broken$|\.backup_[^/]+$|\.copy$)/i;

function clamp(v, min = 0, max = 1) {
  return Math.max(min, Math.min(max, v));
}

function toFixed4(v) {
  return Number(clamp(v).toFixed(4));
}

function nowIso() {
  return new Date().toISOString();
}

function parseArgs(argv = process.argv.slice(2)) {
  const out = {
    workspace: process.cwd(),
    mode: "daily",
    dryRun: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--workspace") {
      out.workspace = argv[i + 1] || out.workspace;
      i += 1;
      continue;
    }
    if (token === "--mode") {
      out.mode = argv[i + 1] || out.mode;
      i += 1;
      continue;
    }
    if (token === "--dry-run") {
      out.dryRun = true;
    }
  }
  if (!Object.prototype.hasOwnProperty.call(MODE_LOOKBACK_DAYS, out.mode)) {
    throw new Error(`invalid --mode: ${out.mode}`);
  }
  return out;
}

function normalizeRel(p) {
  return String(p || "").replaceAll("\\", "/");
}

function shouldSkipPath(relPath, isDirectory) {
  const rel = normalizeRel(relPath);
  if (!rel || rel === ".") {
    return false;
  }
  const parts = rel.split("/");
  const tail = parts[parts.length - 1];
  if (isDirectory && SKIP_DIR_NAMES.has(tail)) {
    return true;
  }
  return SKIP_PATH_PREFIXES.some((prefix) => rel === prefix || rel.startsWith(`${prefix}/`));
}

async function exists(filePath) {
  try {
    await access(filePath, fsConstants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function safeJsonParse(input) {
  try {
    return JSON.parse(input);
  } catch {
    return null;
  }
}

async function readJsonMaybe(filePath) {
  if (!(await exists(filePath))) {
    return null;
  }
  try {
    return safeJsonParse(await readFile(filePath, "utf8"));
  } catch {
    return null;
  }
}

function parseRunIdToMs(runId) {
  const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/.exec(runId || "");
  if (!m) {
    return null;
  }
  const y = Number(m[1]);
  const mon = Number(m[2]) - 1;
  const d = Number(m[3]);
  const hh = Number(m[4]);
  const mm = Number(m[5]);
  const ss = Number(m[6]);
  const utc = Date.UTC(y, mon, d, hh, mm, ss);
  return Number.isFinite(utc) ? utc : null;
}

async function parseIssuesFile(filePath) {
  if (!(await exists(filePath))) {
    return { total: 0, failed: 0, byStage: {} };
  }
  const raw = await readFile(filePath, "utf8");
  const lines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  let failed = 0;
  const byStage = {};
  for (const line of lines) {
    const item = safeJsonParse(line);
    if (!item) {
      continue;
    }
    if (String(item.status || "").toLowerCase() !== "failed") {
      continue;
    }
    failed += 1;
    const stage = String(item.stage || "unknown");
    byStage[stage] = (byStage[stage] || 0) + 1;
  }
  return { total: lines.length, failed, byStage };
}

function stageWeight(stage) {
  if (/^score-/.test(stage)) {
    return 1;
  }
  if (stage === "test-loop") {
    return 1.1;
  }
  if (stage === "post-test") {
    return 1.2;
  }
  if (stage === "deploy") {
    return 1.2;
  }
  return 0.8;
}

async function collectRecentRuns(workspace, lookbackDays) {
  const runsDir = path.join(workspace, ".workflow", "runs");
  if (!(await exists(runsDir))) {
    return {
      runs: [],
      totalIssues: 0,
      failedIssues: 0,
      failureByStage: {},
    };
  }

  const cutoff = Date.now() - lookbackDays * 24 * 3600 * 1000;
  const entries = await readdir(runsDir, { withFileTypes: true });
  const runs = [];
  const failureByStage = {};
  let totalIssues = 0;
  let failedIssues = 0;

  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }
    const runId = entry.name;
    const runDir = path.join(runsDir, runId);
    let runMs = parseRunIdToMs(runId);
    if (!Number.isFinite(runMs)) {
      try {
        const st = await stat(runDir);
        runMs = st.mtime.getTime();
      } catch {
        runMs = null;
      }
    }
    if (!Number.isFinite(runMs) || runMs < cutoff) {
      continue;
    }

    const issues = await parseIssuesFile(path.join(runDir, "issues.ndjson"));
    totalIssues += issues.total;
    failedIssues += issues.failed;

    for (const [stage, count] of Object.entries(issues.byStage)) {
      failureByStage[stage] = (failureByStage[stage] || 0) + count;
    }

    runs.push({
      runId,
      runAt: new Date(runMs).toISOString(),
      issueTotal: issues.total,
      issueFailed: issues.failed,
      hasTimeline: await exists(path.join(runDir, "timeline.log")),
    });
  }

  runs.sort((a, b) => String(b.runId).localeCompare(String(a.runId)));
  return {
    runs,
    totalIssues,
    failedIssues,
    failureByStage,
  };
}

async function loadGateStates(workspace) {
  const gateDir = path.join(workspace, ".workflow", "gates");
  const names = [
    "tester",
    "reviewer",
    "api_doc",
    "quality_gate_predeploy",
    "quality_gate_postdeploy",
    "post_tester",
    "rollback",
    "score_requirements",
    "score_solution",
    "score_frontend",
    "score_backend",
    "score_security",
    "score_release",
    "score_final",
  ];
  const out = {};
  for (const name of names) {
    out[name] = await readJsonMaybe(path.join(gateDir, `${name}.json`));
  }
  return out;
}

function gatePass(gateObj) {
  return gateObj && gateObj.passed === true;
}

function gateFail(gateObj) {
  return gateObj && gateObj.passed === false;
}

function makeCheck(id, label, weight, status, reason, evidence = []) {
  return {
    id,
    label,
    weight,
    status,
    reason,
    evidence,
  };
}

function evaluateGateChecks(gates, hasRecentRuns) {
  const checks = [];

  const strictMissing = hasRecentRuns;

  const tester = gates.tester;
  if (gatePass(tester)) {
    checks.push(
      makeCheck(
        "code_test",
        "Code Test Gate",
        CHECK_WEIGHTS.code_test,
        "pass",
        "tester gate passed",
        [String(tester.reason || "")],
      ),
    );
  } else if (gateFail(tester)) {
    checks.push(
      makeCheck(
        "code_test",
        "Code Test Gate",
        CHECK_WEIGHTS.code_test,
        "fail",
        "tester gate failed",
        [String(tester.reason || "")],
      ),
    );
  } else {
    checks.push(
      makeCheck(
        "code_test",
        "Code Test Gate",
        CHECK_WEIGHTS.code_test,
        strictMissing ? "fail" : "warn",
        "tester gate missing",
      ),
    );
  }

  const reviewer = gates.reviewer;
  if (gatePass(reviewer)) {
    checks.push(
      makeCheck(
        "peer_review",
        "Peer Review Gate",
        CHECK_WEIGHTS.peer_review,
        "pass",
        "reviewer gate passed",
        [String(reviewer.reason || "")],
      ),
    );
  } else if (gateFail(reviewer)) {
    checks.push(
      makeCheck(
        "peer_review",
        "Peer Review Gate",
        CHECK_WEIGHTS.peer_review,
        "fail",
        "reviewer gate failed",
        [String(reviewer.reason || "")],
      ),
    );
  } else {
    checks.push(
      makeCheck(
        "peer_review",
        "Peer Review Gate",
        CHECK_WEIGHTS.peer_review,
        strictMissing ? "fail" : "warn",
        "reviewer gate missing",
      ),
    );
  }

  const acceptanceRequired = [
    "quality_gate_predeploy",
    "score_requirements",
    "score_solution",
    "score_frontend",
    "score_backend",
    "score_security",
  ];
  const acceptanceMissing = [];
  const acceptanceFailed = [];
  for (const name of acceptanceRequired) {
    const gate = gates[name];
    if (!gate) {
      acceptanceMissing.push(name);
      continue;
    }
    if (!gatePass(gate)) {
      acceptanceFailed.push(name);
    }
  }
  if (acceptanceFailed.length === 0 && acceptanceMissing.length === 0) {
    checks.push(
      makeCheck(
        "acceptance",
        "Acceptance Before Deploy",
        CHECK_WEIGHTS.acceptance,
        "pass",
        "predeploy and score gates passed",
      ),
    );
  } else {
    const missingPart = acceptanceMissing.length ? `missing=${acceptanceMissing.join(",")}` : "missing=none";
    const failedPart = acceptanceFailed.length ? `failed=${acceptanceFailed.join(",")}` : "failed=none";
    const status = acceptanceFailed.length > 0 ? "fail" : strictMissing ? "fail" : "warn";
    checks.push(
      makeCheck(
        "acceptance",
        "Acceptance Before Deploy",
        CHECK_WEIGHTS.acceptance,
        status,
        `${missingPart}; ${failedPart}`,
      ),
    );
  }

  const releaseRequired = ["score_release", "score_final", "quality_gate_postdeploy"];
  const releaseMissing = [];
  const releaseFailed = [];
  for (const name of releaseRequired) {
    const gate = gates[name];
    if (!gate) {
      releaseMissing.push(name);
      continue;
    }
    if (!gatePass(gate)) {
      releaseFailed.push(name);
    }
  }
  const rollbackPassed = gatePass(gates.rollback);
  if (releaseFailed.length === 0 && releaseMissing.length === 0) {
    checks.push(
      makeCheck(
        "deploy_release",
        "Deploy And Release Gate",
        CHECK_WEIGHTS.deploy_release,
        "pass",
        "release and postdeploy gates passed",
      ),
    );
  } else if (releaseFailed.includes("quality_gate_postdeploy") && rollbackPassed) {
    checks.push(
      makeCheck(
        "deploy_release",
        "Deploy And Release Gate",
        CHECK_WEIGHTS.deploy_release,
        "warn",
        "postdeploy failed but rollback gate passed",
        [String(gates.quality_gate_postdeploy?.reason || ""), String(gates.rollback?.reason || "")],
      ),
    );
  } else {
    const missingPart = releaseMissing.length ? `missing=${releaseMissing.join(",")}` : "missing=none";
    const failedPart = releaseFailed.length ? `failed=${releaseFailed.join(",")}` : "failed=none";
    const status = releaseFailed.length > 0 ? "fail" : strictMissing ? "warn" : "warn";
    checks.push(
      makeCheck(
        "deploy_release",
        "Deploy And Release Gate",
        CHECK_WEIGHTS.deploy_release,
        status,
        `${missingPart}; ${failedPart}`,
      ),
    );
  }

  const postTester = gates.post_tester;
  const rollback = gates.rollback;
  if (gatePass(postTester)) {
    checks.push(
      makeCheck(
        "post_deploy_validation",
        "Post Deploy Validation",
        CHECK_WEIGHTS.post_deploy_validation,
        "pass",
        "post_tester passed",
      ),
    );
  } else if (gateFail(postTester) && gatePass(rollback)) {
    checks.push(
      makeCheck(
        "post_deploy_validation",
        "Post Deploy Validation",
        CHECK_WEIGHTS.post_deploy_validation,
        "warn",
        "post_tester failed but rollback passed",
        [String(postTester.reason || ""), String(rollback.reason || "")],
      ),
    );
  } else if (gateFail(postTester)) {
    checks.push(
      makeCheck(
        "post_deploy_validation",
        "Post Deploy Validation",
        CHECK_WEIGHTS.post_deploy_validation,
        "fail",
        "post_tester failed and rollback not passed",
        [String(postTester.reason || ""), String(rollback?.reason || "rollback missing")],
      ),
    );
  } else {
    checks.push(
      makeCheck(
        "post_deploy_validation",
        "Post Deploy Validation",
        CHECK_WEIGHTS.post_deploy_validation,
        strictMissing ? "warn" : "warn",
        "post_tester gate missing",
      ),
    );
  }

  return checks;
}

async function analyzeOpsReadiness(workspace) {
  const artifactPaths = [
    "scripts/hardflow/ROLLBACK.md",
    "scripts/hardflow/check-review-test-gate.sh",
    "Project/docs/deployment/openclaw-runbooks.example.yml",
    "Project/docs/deployment/prometheus-alert-rules.example.yml",
  ];
  const found = [];
  const missing = [];
  for (const rel of artifactPaths) {
    const abs = path.join(workspace, rel);
    if (await exists(abs)) {
      found.push(rel);
    } else {
      missing.push(rel);
    }
  }
  return { found, missing };
}

async function scanCodeHygiene(workspace, maxBackupFiles) {
  const queue = [{ abs: workspace, rel: "" }];
  const backupFiles = [];
  let scannedFiles = 0;
  let totalSourceFiles = 0;

  while (queue.length > 0) {
    const current = queue.pop();
    const items = await readdir(current.abs, { withFileTypes: true });
    for (const item of items) {
      const rel = current.rel ? `${current.rel}/${item.name}` : item.name;
      const relNorm = normalizeRel(rel);

      if (shouldSkipPath(relNorm, item.isDirectory())) {
        continue;
      }

      const abs = path.join(current.abs, item.name);
      if (item.isDirectory()) {
        queue.push({ abs, rel: relNorm });
        continue;
      }
      if (!item.isFile()) {
        continue;
      }

      scannedFiles += 1;
      const ext = path.extname(item.name).toLowerCase();
      if (SOURCE_FILE_EXT.has(ext)) {
        totalSourceFiles += 1;
      }

      if (BACKUP_FILE_RE.test(item.name) || /(\.backup\.|\.bak\.)/i.test(item.name)) {
        if (backupFiles.length < 200) {
          backupFiles.push(relNorm);
        }
      }
    }
  }

  let status = "pass";
  let reason = "no obvious backup/dead files";
  if (backupFiles.length > maxBackupFiles) {
    status = "fail";
    reason = `backup-like files=${backupFiles.length} exceeds threshold=${maxBackupFiles}`;
  } else if (backupFiles.length > 0) {
    status = "warn";
    reason = `backup-like files=${backupFiles.length}, keep cleaning`;
  }

  return {
    status,
    reason,
    backupFiles,
    scannedFiles,
    totalSourceFiles,
    threshold: maxBackupFiles,
  };
}

function tailText(text, maxLen = 900) {
  const raw = String(text || "");
  if (raw.length <= maxLen) {
    return raw;
  }
  return raw.slice(raw.length - maxLen);
}

function shellSpecForCurrentPlatform(command) {
  if (process.platform === "win32") {
    return {
      command: "powershell.exe",
      args: ["-NoProfile", "-Command", command],
    };
  }
  return {
    command: "bash",
    args: ["-lc", command],
  };
}

async function runCommand(command, cwd, timeoutMs) {
  const shell = shellSpecForCurrentPlatform(command);
  const startedAt = Date.now();
  const child = spawn(shell.command, shell.args, {
    cwd,
    env: process.env,
  });

  let stdout = "";
  let stderr = "";
  let timedOut = false;

  child.stdout?.on("data", (chunk) => {
    stdout += String(chunk);
  });
  child.stderr?.on("data", (chunk) => {
    stderr += String(chunk);
  });

  const timer = setTimeout(() => {
    timedOut = true;
    child.kill("SIGTERM");
    setTimeout(() => {
      child.kill("SIGKILL");
    }, 1500).unref();
  }, timeoutMs);

  const code = await new Promise((resolve) => {
    child.on("close", (exitCode) => resolve(typeof exitCode === "number" ? exitCode : 1));
    child.on("error", () => resolve(1));
  });
  clearTimeout(timer);

  return {
    command,
    code,
    timedOut,
    durationMs: Date.now() - startedAt,
    stdoutTail: tailText(stdout),
    stderrTail: tailText(stderr),
  };
}

async function runConfiguredCommandChecks(workspace, timeoutMs) {
  const specs = [
    { id: "cmd_test", label: "Configured Test Command", env: "HARDFLOW_PROCESS_CMD_TEST" },
    { id: "cmd_review", label: "Configured Review Command", env: "HARDFLOW_PROCESS_CMD_REVIEW" },
    { id: "cmd_acceptance", label: "Configured Acceptance Command", env: "HARDFLOW_PROCESS_CMD_ACCEPTANCE" },
    { id: "cmd_postdeploy", label: "Configured Post-Deploy Command", env: "HARDFLOW_PROCESS_CMD_POSTDEPLOY" },
    { id: "cmd_ops", label: "Configured Ops Command", env: "HARDFLOW_PROCESS_CMD_OPS" },
    { id: "cmd_hygiene", label: "Configured Hygiene Command", env: "HARDFLOW_PROCESS_CMD_HYGIENE" },
  ];

  const results = [];
  for (const spec of specs) {
    const command = process.env[spec.env];
    if (!command || !String(command).trim()) {
      results.push({
        id: spec.id,
        label: spec.label,
        env: spec.env,
        configured: false,
        status: "skip",
        reason: "not configured",
      });
      continue;
    }
    const result = await runCommand(command, workspace, timeoutMs);
    results.push({
      id: spec.id,
      label: spec.label,
      env: spec.env,
      configured: true,
      status: result.code === 0 ? "pass" : "fail",
      reason: result.code === 0 ? "command passed" : `command failed, rc=${result.code}`,
      ...result,
    });
  }
  return results;
}

function buildHotspots(failureByStage) {
  return Object.entries(failureByStage)
    .map(([stage, count]) => ({
      stage,
      count: Number(count || 0),
      weighted: Number((Number(count || 0) * stageWeight(stage)).toFixed(3)),
    }))
    .sort((a, b) => {
      if (b.weighted !== a.weighted) {
        return b.weighted - a.weighted;
      }
      return b.count - a.count;
    })
    .slice(0, 8);
}

function scoreChecks(checks, commandChecks) {
  const totalWeight = checks.reduce((sum, c) => sum + c.weight, 0);
  const weighted = checks.reduce((sum, c) => {
    const score = STATUS_SCORE[c.status] ?? 0.5;
    return sum + c.weight * score;
  }, 0);
  const baseScore = totalWeight > 0 ? weighted / totalWeight : 0.5;

  const configured = commandChecks.filter((x) => x.configured);
  const failed = configured.filter((x) => x.status === "fail");
  const commandPenalty = clamp(failed.length * 0.05, 0, 0.2);
  const score = clamp(baseScore - commandPenalty);
  return {
    score: toFixed4(score),
    baseScore: toFixed4(baseScore),
    commandPenalty: toFixed4(commandPenalty),
  };
}

function classifyHealth(score, failCount) {
  if (failCount === 0 && score >= 0.85) {
    return "healthy";
  }
  if (score >= 0.65 && failCount <= 2) {
    return "warning";
  }
  return "critical";
}

async function loadHistory(historyFile) {
  if (!(await exists(historyFile))) {
    return [];
  }
  const raw = await readFile(historyFile, "utf8");
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => safeJsonParse(line))
    .filter(Boolean);
}

function buildRecommendations({ checks, hotspots, commandChecks, hygiene, trend }) {
  const recs = [];
  const add = (priority, id, title, action, why) => {
    recs.push({ priority, id, title, action, why });
  };

  for (const check of checks) {
    if (check.id === "code_test" && check.status !== "pass") {
      add(
        "P0",
        "hardening-test-loop",
        "Enforce test loop after every change",
        "Standardize TEST_CMD and require test-loop pass before any downstream gate.",
        check.reason,
      );
    }
    if (check.id === "peer_review" && check.status !== "pass") {
      add(
        "P0",
        "hardening-review",
        "Make peer review checklist blocking",
        "Treat reviewer gate as blocking and require boundary/rollback/maintainability checks.",
        check.reason,
      );
    }
    if (check.id === "acceptance" && check.status !== "pass") {
      add(
        "P0",
        "hardening-acceptance",
        "Strengthen acceptance gate",
        "Require predeploy and score gates to pass before deploy.",
        check.reason,
      );
    }
    if (check.id === "deploy_release" && check.status !== "pass") {
      add(
        "P0",
        "hardening-release",
        "Harden release closure",
        "Require score_release, score_final and postdeploy gate pass; otherwise rollback or manual approval.",
        check.reason,
      );
    }
    if (check.id === "post_deploy_validation" && check.status !== "pass") {
      add(
        "P0",
        "hardening-postdeploy",
        "Enforce post-deploy validation",
        "Run post_tester after deploy; rollback and record issue if it fails.",
        check.reason,
      );
    }
    if (check.id === "ops_readiness" && check.status !== "pass") {
      add(
        "P1",
        "ops-observability",
        "Improve ops observability",
        "Complete runbooks, alert rules and rollback docs for fast incident localization.",
        check.reason,
      );
    }
    if (check.id === "code_hygiene" && check.status !== "pass") {
      add(
        "P1",
        "cleanup-dead-artifacts",
        "Clean dead code artifacts",
        `Clean backup-like files, threshold=${hygiene.threshold}, current=${hygiene.backupFiles.length}.`,
        check.reason,
      );
    }
  }

  const hot = hotspots.filter((x) => x.count >= 2).slice(0, 3);
  if (hot.length > 0) {
    add(
      "P1",
      "recurring-failures",
      "Reduce recurring failure stages",
      `Create targeted SOPs for hotspots: ${hot.map((x) => `${x.stage}(${x.count})`).join(", ")}`,
      "recent runs show repeated failures",
    );
  }

  const failedCommands = commandChecks.filter((x) => x.configured && x.status === "fail");
  for (const cmd of failedCommands) {
    add(
      "P1",
      `fix-${cmd.id}`,
      `修复配置化校验命令: ${cmd.id}`,
      `修复 ${cmd.env} 对应命令并保证返回码为 0；必要时拆分成更稳定的小命令。`,
      cmd.reason,
    );
  }

  if (trend.deltaFromPrevious !== null && trend.deltaFromPrevious < -0.05) {
    add(
      "P1",
      "trend-regression",
      "Process health regressed",
      "Compare last two reports and fix newly introduced failures first.",
      `score delta=${trend.deltaFromPrevious}`,
    );
  }

  if (recs.length === 0) {
    add(
      "P2",
      "keep-iterating",
      "Keep iterative hardening",
      "Review latest report weekly and tune check commands and gate thresholds.",
      "no critical findings",
    );
  }

  return recs.slice(0, 12);
}

function markdownStatus(status) {
  if (status === "pass") {
    return "PASS";
  }
  if (status === "warn") {
    return "WARN";
  }
  if (status === "fail") {
    return "FAIL";
  }
  return "SKIP";
}

function buildSopDoc(report) {
  const lines = [];
  lines.push("# SOP Process Optimization");
  lines.push("");
  lines.push(`Generated at: ${report.generatedAt}`);
  lines.push(`Mode: ${report.mode}`);
  lines.push(`Process score: ${report.summary.processScore}`);
  lines.push(`Health: ${report.summary.health}`);
  lines.push("");
  lines.push("## Stage Checks");
  lines.push("");
  for (const check of report.checks) {
    lines.push(`- [${markdownStatus(check.status)}] ${check.label}: ${check.reason}`);
  }
  lines.push("");
  lines.push("## Hotspots");
  lines.push("");
  if (report.hotspots.length === 0) {
    lines.push("- none");
  } else {
    for (const item of report.hotspots) {
      lines.push(`- ${item.stage}: count=${item.count}, weighted=${item.weighted}`);
    }
  }
  lines.push("");
  lines.push("## Recommendations");
  lines.push("");
  for (const rec of report.recommendations) {
    lines.push(`1. [${rec.priority}] ${rec.title}`);
    lines.push(`Action: ${rec.action}`);
    lines.push(`Why: ${rec.why}`);
    lines.push("");
  }
  return `${lines.join("\n")}\n`;
}

async function writeOutputs({
  workspace,
  report,
  historyFile,
  latestFile,
  sopFile,
  dryRun,
}) {
  if (dryRun) {
    return;
  }

  await mkdir(path.dirname(historyFile), { recursive: true });
  await writeFile(latestFile, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await appendFile(historyFile, `${JSON.stringify({
    generatedAt: report.generatedAt,
    mode: report.mode,
    processScore: report.summary.processScore,
    health: report.summary.health,
    failChecks: report.summary.failChecks,
    hotspots: report.hotspots.slice(0, 5),
  })}\n`, "utf8");
  await writeFile(sopFile, buildSopDoc(report), "utf8");
}

async function run() {
  const { workspace, mode, dryRun } = parseArgs();
  const generatedAt = nowIso();
  const lookbackDays = MODE_LOOKBACK_DAYS[mode];
  const maxBackupFiles = Number(process.env.HARDFLOW_PROCESS_MAX_BACKUP_FILES || "8");
  const timeoutSec = Number(process.env.HARDFLOW_PROCESS_CMD_TIMEOUT_SEC || "900");
  const timeoutMs = Number.isFinite(timeoutSec) && timeoutSec > 0 ? timeoutSec * 1000 : 900000;

  const recent = await collectRecentRuns(workspace, lookbackDays);
  const gates = await loadGateStates(workspace);
  const gateChecks = evaluateGateChecks(gates, recent.runs.length > 0);

  const ops = await analyzeOpsReadiness(workspace);
  const opsStatus = ops.missing.length === 0 ? "pass" : ops.missing.length >= 3 ? "fail" : "warn";
  gateChecks.push(
    makeCheck(
      "ops_readiness",
      "Ops Readiness",
      CHECK_WEIGHTS.ops_readiness,
      opsStatus,
      ops.missing.length === 0
        ? "runbook and alert artifacts ready"
        : `missing artifacts: ${ops.missing.join(", ")}`,
      ops.found,
    ),
  );

  const hygiene = await scanCodeHygiene(workspace, Number.isFinite(maxBackupFiles) ? maxBackupFiles : 8);
  gateChecks.push(
    makeCheck(
      "code_hygiene",
      "Code Hygiene",
      CHECK_WEIGHTS.code_hygiene,
      hygiene.status,
      hygiene.reason,
      hygiene.backupFiles.slice(0, 15),
    ),
  );

  const commandChecks = await runConfiguredCommandChecks(workspace, timeoutMs);
  const score = scoreChecks(gateChecks, commandChecks);
  const failChecks = gateChecks.filter((x) => x.status === "fail").length;
  const warnChecks = gateChecks.filter((x) => x.status === "warn").length;
  const passChecks = gateChecks.filter((x) => x.status === "pass").length;
  const health = classifyHealth(score.score, failChecks);
  const hotspots = buildHotspots(recent.failureByStage);

  const outDir = path.join(workspace, ".workflow", "process-optimization");
  const latestFile = path.join(outDir, "latest-report.json");
  const historyFile = path.join(outDir, "history.ndjson");
  const sopFile = path.join(outDir, "SOP_PROCESS_OPTIMIZATION.md");

  const history = await loadHistory(historyFile);
  const previous = history.length > 0 ? history[history.length - 1] : null;
  const prevScore = previous && Number.isFinite(Number(previous.processScore)) ? Number(previous.processScore) : null;
  const delta = prevScore === null ? null : Number((score.score - prevScore).toFixed(4));
  const trend = {
    previousScore: prevScore,
    deltaFromPrevious: delta,
  };

  const recommendations = buildRecommendations({
    checks: gateChecks,
    hotspots,
    commandChecks,
    hygiene,
    trend,
  });

  const report = {
    generatedAt,
    mode,
    workspace,
    lookbackDays,
    summary: {
      processScore: score.score,
      baseScore: score.baseScore,
      commandPenalty: score.commandPenalty,
      health,
      checksTotal: gateChecks.length,
      passChecks,
      warnChecks,
      failChecks,
      recentRuns: recent.runs.length,
      totalIssues: recent.totalIssues,
      failedIssues: recent.failedIssues,
    },
    checks: gateChecks,
    commandChecks,
    hotspots,
    opsReadiness: ops,
    codeHygiene: {
      status: hygiene.status,
      reason: hygiene.reason,
      threshold: hygiene.threshold,
      backupFiles: hygiene.backupFiles,
      scannedFiles: hygiene.scannedFiles,
      sourceFiles: hygiene.totalSourceFiles,
    },
    trend,
    recommendations,
  };

  await writeOutputs({
    workspace,
    report,
    historyFile,
    latestFile,
    sopFile,
    dryRun,
  });

  console.log(JSON.stringify({
    ok: true,
    mode,
    workspace,
    report: {
      generatedAt: report.generatedAt,
      processScore: report.summary.processScore,
      health: report.summary.health,
      failChecks: report.summary.failChecks,
      hotspots: report.hotspots.slice(0, 5),
      recommendations: report.recommendations.slice(0, 5).map((x) => ({
        priority: x.priority,
        title: x.title,
      })),
    },
  }, null, 2));
}

run().catch((err) => {
  const message = err instanceof Error ? err.stack || err.message : String(err);
  console.error("[process-optimize] failed");
  console.error(message);
  process.exit(1);
});
