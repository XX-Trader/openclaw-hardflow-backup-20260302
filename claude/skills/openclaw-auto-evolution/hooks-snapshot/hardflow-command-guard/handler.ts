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
  const required = [
    "todo.md",
    "done.md",
    "scripts/hardflow/hardflow-v1.lobster.yaml",
    "scripts/hardflow/score-policy.json",
    "scripts/hardflow/check-score-gate.mjs",
  ];

  const missing: string[] = [];
  for (const rel of required) {
    try {
      await access(path.join(workspaceDir, rel));
    } catch {
      missing.push(rel);
    }
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
