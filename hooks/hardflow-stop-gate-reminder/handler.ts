import { access, readFile } from "node:fs/promises";
import path from "node:path";

async function gatePassed(file: string): Promise<"passed" | "failed" | "missing"> {
  try {
    const raw = await readFile(file, "utf8");
    const data = JSON.parse(raw);
    return data?.passed === true ? "passed" : "failed";
  } catch {
    return "missing";
  }
}

async function fileExists(file: string): Promise<boolean> {
  try {
    await access(file);
    return true;
  } catch {
    return false;
  }
}

export default async function hardflowStopGateReminder(event: any): Promise<void> {
  if (event?.type !== "command" || event?.action !== "stop") {
    return;
  }

  const workspaceDir = event?.context?.workspaceDir || process.cwd();
  const gateDir = path.join(workspaceDir, ".workflow", "gates");
  const stateFile = path.join(workspaceDir, ".workflow", "current_run_id");

  const requiredPreDeploy = [
    "reviewer",
    "tester",
    "api_doc",
    "score_requirements",
    "score_solution",
    "score_frontend",
    "score_backend",
    "score_security",
    "quality_gate_predeploy",
  ];
  const requiredPostDeploy = ["post_tester", "score_release", "score_final", "quality_gate_postdeploy"];

  const required = [...requiredPreDeploy];
  if (await fileExists(path.join(gateDir, "post_tester.json"))) {
    required.push(...requiredPostDeploy);
  } else if (await fileExists(stateFile)) {
    const runId = (await readFile(stateFile, "utf8")).trim();
    if (runId) {
      const deployLog = path.join(workspaceDir, ".workflow", "runs", runId, "deploy.log");
      if (await fileExists(deployLog)) {
        required.push(...requiredPostDeploy);
      }
    }
  }

  const missing: string[] = [];
  const failed: string[] = [];

  for (const gate of required) {
    const status = await gatePassed(path.join(gateDir, `${gate}.json`));
    if (status === "missing") {
      missing.push(gate);
    } else if (status === "failed") {
      failed.push(gate);
    }
  }

  if (missing.length === 0 && failed.length === 0) {
    event.messages.push("HardFlow 收口检查已通过，所有必需门禁均已通过。");
    return;
  }

  event.messages.push(
    [
      "HardFlow 收口检查未通过，当前仍有未闭环门禁。",
      `缺失门禁：${missing.length > 0 ? missing.join(", ") : "无"}`,
      `失败门禁：${failed.length > 0 ? failed.join(", ") : "无"}`,
      "请先继续修复、重新评分并复测，再结束当前流程。",
    ].join("\n"),
  );
}
