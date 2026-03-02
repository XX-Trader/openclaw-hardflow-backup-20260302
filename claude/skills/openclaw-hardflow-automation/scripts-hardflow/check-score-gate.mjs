#!/usr/bin/env node
import { mkdir, readFile, writeFile, appendFile } from "node:fs/promises";
import path from "node:path";

function parseArgs(argv) {
  const args = {
    gate: "",
    scorecard: "",
    policy: path.join(process.cwd(), "scripts", "hardflow", "score-policy.json"),
    output: "",
    runId: "",
    auditLog: "",
  };

  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    const val = argv[i + 1];
    if (!key.startsWith("--")) {
      continue;
    }
    if (typeof val === "undefined") {
      continue;
    }
    if (key === "--gate") {
      args.gate = val;
      i += 1;
      continue;
    }
    if (key === "--scorecard") {
      args.scorecard = val;
      i += 1;
      continue;
    }
    if (key === "--policy") {
      args.policy = val;
      i += 1;
      continue;
    }
    if (key === "--output") {
      args.output = val;
      i += 1;
      continue;
    }
    if (key === "--run-id") {
      args.runId = val;
      i += 1;
      continue;
    }
    if (key === "--audit-log") {
      args.auditLog = val;
      i += 1;
    }
  }

  return args;
}

function usage() {
  return [
    "Usage:",
    "  node check-score-gate.mjs \\",
    "    --gate <requirements|solution|frontend|backend|security|release|final> \\",
    "    --scorecard <path> \\",
    "    --output <path> \\",
    "    [--policy <path>] [--run-id <id>] [--audit-log <ndjson>]",
  ].join("\n");
}

async function loadJson(file) {
  const raw = await readFile(file, "utf8");
  return JSON.parse(raw);
}

function toNumber(x) {
  if (typeof x === "number" && Number.isFinite(x)) {
    return x;
  }
  if (typeof x === "string" && x.trim() !== "") {
    const n = Number(x);
    if (Number.isFinite(n)) {
      return n;
    }
  }
  return NaN;
}

function normalize(value) {
  return String(value || "")
    .trim()
    .toLowerCase();
}

function collectFindings(scorecard) {
  const buckets = [
    scorecard.findings,
    scorecard.security_findings,
    scorecard.securityFindings,
    scorecard.criticalRisks,
  ];
  const out = [];
  for (const arr of buckets) {
    if (!Array.isArray(arr)) {
      continue;
    }
    for (const item of arr) {
      if (item && typeof item === "object") {
        out.push(item);
      }
    }
  }
  return out;
}

async function writeResult(file, result) {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, `${JSON.stringify(result, null, 2)}\n`, "utf8");
}

async function appendAudit(file, payload) {
  if (!file) {
    return;
  }
  await mkdir(path.dirname(file), { recursive: true });
  await appendFile(file, `${JSON.stringify(payload)}\n`, "utf8");
}

function evaluate({ gate, gatePolicy, scorecard }) {
  const now = new Date().toISOString();
  const dimensionThresholds = gatePolicy.dimensionThresholds || {};
  const dimensionScores = scorecard.dimensions && typeof scorecard.dimensions === "object" ? scorecard.dimensions : {};

  const overall = toNumber(scorecard.overall);
  const overallDeduction = Number.isNaN(overall) ? null : Math.max(0, 100 - overall);
  const failedChecks = [];
  const failedDimensions = [];
  const missingDimensions = [];
  const dimensionBreakdown = [];
  const deductionNotes = [];

  if (Number.isNaN(overall)) {
    failedChecks.push("overall score is missing or invalid");
  } else if (overall < gatePolicy.threshold) {
    failedChecks.push(`overall score ${overall} < required ${gatePolicy.threshold}`);
  }

  for (const [dimension, minScore] of Object.entries(dimensionThresholds)) {
    const val = toNumber(dimensionScores[dimension]);
    if (Number.isNaN(val)) {
      missingDimensions.push(dimension);
      dimensionBreakdown.push({
        dimension,
        score: null,
        threshold: Number(minScore),
        deduction_from_100: null,
        threshold_gap: null,
        status: "missing",
      });
      continue;
    }
    const thresholdNum = Number(minScore);
    const thresholdGap = val - thresholdNum;
    const deduction = Math.max(0, 100 - val);
    const status = thresholdGap >= 0 ? "passed" : "below_threshold";
    dimensionBreakdown.push({
      dimension,
      score: val,
      threshold: thresholdNum,
      deduction_from_100: deduction,
      threshold_gap: thresholdGap,
      status,
    });
    if (deduction > 0) {
      deductionNotes.push(`${dimension}: -${deduction} (score=${val})`);
    }
    if (val < Number(minScore)) {
      failedDimensions.push({ dimension, score: val, required: Number(minScore) });
    }
  }

  if (missingDimensions.length > 0) {
    failedChecks.push(`missing dimensions: ${missingDimensions.join(", ")}`);
  }
  if (failedDimensions.length > 0) {
    failedChecks.push(
      `dimension threshold failed: ${failedDimensions
        .map((x) => `${x.dimension}=${x.score}<${x.required}`)
        .join("; ")}`,
    );
  }

  const evidence = Array.isArray(scorecard.evidence) ? scorecard.evidence.filter((x) => String(x || "").trim() !== "") : [];
  const minEvidenceCount = Number(gatePolicy.minEvidenceCount || 0);
  if (evidence.length < minEvidenceCount) {
    failedChecks.push(`evidence count ${evidence.length} < required ${minEvidenceCount}`);
  }

  const vetoPolicy = gatePolicy.veto || { enabled: false };
  const vetoHits = [];
  if (vetoPolicy.enabled) {
    const severities = new Set((vetoPolicy.severities || []).map((x) => normalize(x)));
    const resolvedStatuses = new Set((vetoPolicy.resolvedStatuses || []).map((x) => normalize(x)));
    for (const finding of collectFindings(scorecard)) {
      const severity = normalize(finding.severity);
      const status = normalize(finding.status);
      if (!severities.has(severity)) {
        continue;
      }
      if (!resolvedStatuses.has(status)) {
        vetoHits.push({
          id: finding.id || "",
          severity,
          status,
          title: finding.title || "",
        });
      }
    }
  }

  if (vetoHits.length > 0) {
    deductionNotes.push(
      `security veto: ${vetoHits
        .map((x) => `${x.id || "unknown"}(${x.severity}/${x.status || "unknown"})`)
        .join(", ")}`,
    );
    failedChecks.push(
      `veto triggered by unresolved high-risk findings: ${vetoHits
        .map((x) => `${x.id || "unknown"}(${x.severity}/${x.status || "unknown"})`)
        .join(", ")}`,
    );
  }

  const passed = failedChecks.length === 0;
  const reason = passed ? "score gate passed" : failedChecks.join(" | ");

  return {
    passed,
    updated_at: now,
    gate,
    gate_id: gatePolicy.gateId || "",
    display_name: gatePolicy.displayName || gate,
    threshold: gatePolicy.threshold,
    overall_score: Number.isNaN(overall) ? null : overall,
    overall_deduction_from_100: overallDeduction,
    dimension_thresholds: dimensionThresholds,
    dimension_scores: dimensionScores,
    dimension_breakdown: dimensionBreakdown,
    deduction_notes: deductionNotes,
    failed_dimensions: failedDimensions,
    missing_dimensions: missingDimensions,
    min_evidence_count: minEvidenceCount,
    evidence_count: evidence.length,
    veto: {
      enabled: Boolean(vetoPolicy.enabled),
      hits: vetoHits,
    },
    reviewer: scorecard.reviewer || "",
    summary: scorecard.summary || "",
    reason,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.gate || !args.scorecard || !args.output) {
    console.error(usage());
    process.exit(2);
  }

  const policy = await loadJson(args.policy);
  const gatePolicy = policy?.gates?.[args.gate];
  if (!gatePolicy) {
    console.error(`unknown gate '${args.gate}' in policy '${args.policy}'`);
    process.exit(2);
  }

  const scorecard = await loadJson(args.scorecard);
  const result = evaluate({ gate: args.gate, gatePolicy, scorecard });
  result.policy_version = policy.version || "";
  result.run_id = args.runId || "";
  result.scorecard_path = path.resolve(args.scorecard);

  await writeResult(args.output, result);
  await appendAudit(args.auditLog, {
    ts: result.updated_at,
    run_id: result.run_id,
    gate: result.gate,
    gate_id: result.gate_id,
    passed: result.passed,
    overall_score: result.overall_score,
    overall_deduction_from_100: result.overall_deduction_from_100,
    deduction_notes: result.deduction_notes,
    reason: result.reason,
    scorecard_path: result.scorecard_path,
  });

  if (result.passed) {
    console.log(`[score-gate] pass gate=${args.gate} score=${result.overall_score}`);
    process.exit(0);
  }

  console.log(`[score-gate] fail gate=${args.gate}: ${result.reason}`);
  process.exit(1);
}

main().catch((err) => {
  const msg = err instanceof Error ? err.stack || err.message : String(err);
  console.error(`[score-gate] error: ${msg}`);
  process.exit(2);
});
