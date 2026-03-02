import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";

export default async function hardflowAudit(event: any): Promise<void> {
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
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[hardflow-audit] append log failed: ${message}`);
  }
}
