import { access, readFile } from "node:fs/promises";
import path from "node:path";

async function gatePassed(filePath) {
  try {
    const raw = await readFile(filePath, "utf8");
    const data = JSON.parse(raw);
    return data?.passed === true ? "passed" : "failed";
  } catch {
    return "missing";
  }
}

async function fileExists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

/**
 * Remind the operator about unresolved gates before `/stop` finishes.
 *
 * @param {any} event OpenClaw command hook event.
 * @returns {Promise<void>} Resolves after appending a stop-state reminder message.
 * @throws {Error} Propagates filesystem errors only when required gate files cannot be inspected.
 */
export default async function hardflowStopGateReminder(event) {
  if (event?.type !== "command" || event?.action !== "stop") {
    return;
  }

  const messages = Array.isArray(event?.messages) ? event.messages : [];
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

  const missing = [];
  const failed = [];

  for (const gateName of required) {
    const status = await gatePassed(path.join(gateDir, `${gateName}.json`));
    if (status === "missing") {
      missing.push(gateName);
    } else if (status === "failed") {
      failed.push(gateName);
    }
  }

  if (missing.length === 0 && failed.length === 0) {
    messages.push("HardFlow stop reminder: all required gates are passed.");
    return;
  }

  messages.push(
    [
      "HardFlow stop reminder: unresolved gate constraints.",
      `missing gates: ${missing.length > 0 ? missing.join(", ") : "none"}`,
      `failed gates: ${failed.length > 0 ? failed.join(", ") : "none"}`,
      "Please fix, re-score, and re-test before ending the workflow.",
    ].join("\n"),
  );
}
