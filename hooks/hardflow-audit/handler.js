import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";

/**
 * Append command events to the workflow audit log.
 *
 * @param {any} event OpenClaw command hook event.
 * @returns {Promise<void>} Resolves after appending a JSONL record when the event is a command.
 * @throws {Error} Propagates filesystem write failures after logging the underlying message.
 */
export default async function hardflowAudit(event) {
  if (event?.type !== "command") {
    return;
  }

  const workspaceDir = event?.context?.workspaceDir || process.cwd();
  const logDir = path.join(workspaceDir, ".workflow", "hook-audit");
  const logFile = path.join(logDir, "commands.log");
  const record = {
    ts: event?.timestamp?.toISOString?.() ?? new Date().toISOString(),
    type: event?.type ?? "unknown",
    action: event?.action ?? "unknown",
    sessionKey: event?.sessionKey ?? "",
    source: event?.context?.commandSource ?? "",
    senderId: event?.context?.senderId ?? "",
    workspaceDir,
  };

  try {
    await mkdir(logDir, { recursive: true });
    await appendFile(logFile, `${JSON.stringify(record)}\n`, "utf8");
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[hardflow-audit] append log failed: ${message}`);
  }
}
