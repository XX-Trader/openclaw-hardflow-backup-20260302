#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import path from "node:path";

const GATES = ["requirements", "solution", "frontend", "backend", "security", "release", "final"];

function parseArgs(argv) {
  const args = {
    workspace: process.cwd(),
    runId: "",
    gate: "",
    format: "text",
  };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    const val = argv[i + 1];
    if (key === "--workspace" && val) {
      args.workspace = val;
      i += 1;
      continue;
    }
    if (key === "--run-id" && val) {
      args.runId = val;
      i += 1;
      continue;
    }
    if (key === "--gate" && val) {
      args.gate = val;
      i += 1;
      continue;
    }
    if (key === "--format" && val) {
      args.format = val;
      i += 1;
    }
  }
  return args;
}

async function loadJson(file) {
  const raw = await readFile(file, "utf8");
  return JSON.parse(raw);
}

function gateFile(workspace, gate) {
  return path.join(workspace, ".workflow", "gates", `score_${gate}.json`);
}

function sortBreakdown(items) {
  return [...items].sort((a, b) => {
    const ad = typeof a.deduction_from_100 === "number" ? a.deduction_from_100 : -1;
    const bd = typeof b.deduction_from_100 === "number" ? b.deduction_from_100 : -1;
    return bd - ad;
  });
}

function lineForDimension(dim) {
  if (dim.status === "missing") {
    return `- ${dim.dimension}: 缺失（要求>=${dim.threshold}）`;
  }
  const mark = dim.status === "below_threshold" ? "FAIL" : "PASS";
  const gap = typeof dim.threshold_gap === "number" ? dim.threshold_gap : 0;
  const deduction = typeof dim.deduction_from_100 === "number" ? dim.deduction_from_100 : 0;
  return `- ${dim.dimension}: ${dim.score}/${dim.threshold} ${mark} | 扣分=${deduction} | 阈值差=${gap}`;
}

function toText(reports, runId) {
  const lines = [];
  lines.push(`HardFlow 评分报告 run_id=${runId || "unknown"}`);
  for (const rep of reports) {
    lines.push("");
    lines.push(`[${rep.gate_id}] ${rep.display_name} (${rep.gate})`);
    lines.push(`- 状态: ${rep.passed ? "PASS" : "FAIL"}`);
    lines.push(`- 总分: ${rep.overall_score ?? "N/A"} / 阈值 ${rep.threshold}`);
    lines.push(`- 总扣分: ${rep.overall_deduction_from_100 ?? "N/A"}`);
    lines.push(`- 评审: ${rep.reviewer || "unknown"}`);
    if (rep.reason) {
      lines.push(`- 结论: ${rep.reason}`);
    }
    const breakdown = sortBreakdown(Array.isArray(rep.dimension_breakdown) ? rep.dimension_breakdown : []);
    if (breakdown.length > 0) {
      lines.push("- 维度明细:");
      for (const dim of breakdown) {
        lines.push(lineForDimension(dim));
      }
    }
    if (rep.veto?.enabled && Array.isArray(rep.veto?.hits) && rep.veto.hits.length > 0) {
      lines.push("- 安全 veto:");
      for (const hit of rep.veto.hits) {
        lines.push(`- ${hit.id || "unknown"} ${hit.severity}/${hit.status} ${hit.title || ""}`.trim());
      }
    }
  }
  return lines.join("\n");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const selectedGates = args.gate ? [args.gate] : GATES;
  const reports = [];
  const missing = [];

  for (const gate of selectedGates) {
    try {
      const json = await loadJson(gateFile(args.workspace, gate));
      reports.push(json);
    } catch {
      missing.push(gate);
    }
  }

  if (args.format === "json") {
    const out = {
      run_id: args.runId || "",
      reports,
      missing_gates: missing,
    };
    console.log(JSON.stringify(out, null, 2));
    process.exit(missing.length > 0 ? 1 : 0);
  }

  console.log(toText(reports, args.runId));
  if (missing.length > 0) {
    console.log("");
    console.log(`缺失 Gate 结果: ${missing.join(", ")}`);
  }
  process.exit(missing.length > 0 ? 1 : 0);
}

main().catch((err) => {
  const msg = err instanceof Error ? err.stack || err.message : String(err);
  console.error(`[score-report] error: ${msg}`);
  process.exit(2);
});
