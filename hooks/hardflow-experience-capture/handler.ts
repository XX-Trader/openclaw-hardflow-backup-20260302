import {
  appendCard,
  buildCardFromMessages,
  ensureExperienceDirs,
  ensureStatsRecord,
  existsFile,
  findSessionRef,
  hasMeaningfulFixSignal,
  loadStats,
  nowIso,
  readCards,
  readSessionMessages,
  resolveAgentId,
  resolveHookOptions,
  resolveWorkspaceDir,
  saveStats,
  shortText,
} from "../_lib/experience.ts";

type CaptureOptions = {
  enabled?: boolean;
  messages?: number;
  minMessages?: number;
};

const HOOK_NAME = "hardflow-experience-capture";

function shouldHandle(event: any): boolean {
  if (event?.type !== "command") {
    return false;
  }
  return event?.action === "stop" || event?.action === "new" || event?.action === "reset";
}

export default async function hardflowExperienceCapture(event: any): Promise<void> {
  if (!shouldHandle(event)) {
    return;
  }

  const opts = resolveHookOptions<CaptureOptions>(event, HOOK_NAME);
  if (opts.enabled === false) {
    return;
  }

  const workspaceDir = resolveWorkspaceDir(event);
  const agentId = resolveAgentId(event);
  const maxMessages = typeof opts.messages === "number" && opts.messages > 0 ? opts.messages : 80;
  const minMessages = typeof opts.minMessages === "number" && opts.minMessages > 0 ? opts.minMessages : 8;
  const sessionRef = findSessionRef(event);
  const sessionFile = sessionRef.sessionFile;
  if (!sessionFile || !(await existsFile(sessionFile))) {
    return;
  }

  try {
    const messages = await readSessionMessages(sessionFile, maxMessages);
    if (messages.length < minMessages) {
      return;
    }
    if (!hasMeaningfulFixSignal(messages)) {
      return;
    }

    const now = nowIso();
    const card = buildCardFromMessages({
      messages,
      sourceAction: event?.action || "unknown",
      sessionKey: event?.sessionKey || "",
      sessionId: sessionRef.sessionId,
      now,
      agentId,
    });
    if (!card) {
      return;
    }

    await ensureExperienceDirs(workspaceDir);
    const existing = await readCards(workspaceDir);
    if (existing.some((x) => x.fingerprint === card.fingerprint)) {
      return;
    }

    await appendCard(workspaceDir, card);
    const stats = await loadStats(workspaceDir);
    ensureStatsRecord(stats, card.id);
    await saveStats(workspaceDir, stats);

    if (event?.action === "stop" && Array.isArray(event.messages)) {
      event.messages.push(
        `🧠 Experience captured: ${shortText(card.title, 60)} (${card.id})`,
      );
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[${HOOK_NAME}] failed: ${message}`);
  }
}
