import {
  appendLinkGraphEvent,
  buildSignalKeyFromQuery,
  clearRuntimeRecall,
  ensureStatsRecord,
  findSessionRef,
  loadStats,
  readRuntimeRecallPayload,
  resolveAgentId,
  resolveOutcome,
  resolveWorkspaceDir,
  saveStats,
} from "../_lib/experience.ts";

const HOOK_NAME = "hardflow-experience-evolve";

export default async function hardflowExperienceEvolve(event: any): Promise<void> {
  if (event?.type !== "command" || event?.action !== "stop") {
    return;
  }
  const workspaceDir = resolveWorkspaceDir(event);
  const sessionKey = event?.sessionKey || "unknown";
  const fallbackAgentId = resolveAgentId(event);

  try {
    const runtimeRecall = await readRuntimeRecallPayload(workspaceDir, sessionKey);
    const recalledIds = runtimeRecall?.cardIds || [];
    if (recalledIds.length === 0) {
      return;
    }

    const sessionRef = findSessionRef(event);
    const outcome = await resolveOutcome({
      workspaceDir,
      sessionFile: sessionRef.sessionFile,
    });
    const stats = await loadStats(workspaceDir);
    const now = new Date().toISOString();

    for (const id of recalledIds) {
      const record = ensureStatsRecord(stats, id);
      if (outcome === "success") {
        record.successCount += 1;
      } else if (outcome === "failure") {
        record.failureCount += 1;
      }
      record.lastOutcome = outcome;
      record.lastOutcomeAt = now;
    }
    await saveStats(workspaceDir, stats);
    await appendLinkGraphEvent({
      workspaceDir,
      event: {
        type: "outcome",
        ts: now,
        sessionKey: runtimeRecall?.sessionKey || sessionKey,
        agentId: runtimeRecall?.agentId || fallbackAgentId,
        queryKey: runtimeRecall?.queryKey || buildSignalKeyFromQuery(runtimeRecall?.query || ""),
        query: runtimeRecall?.query || "",
        cardIds: recalledIds,
        outcome,
      },
    });
    await clearRuntimeRecall(workspaceDir, sessionKey);

    if (Array.isArray(event.messages)) {
      event.messages.push(`Experience evolved: ${outcome} (${recalledIds.length} cards)`);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[${HOOK_NAME}] failed: ${message}`);
  }
}

