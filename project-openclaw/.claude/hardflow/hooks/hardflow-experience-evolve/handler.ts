import {
  clearRuntimeRecall,
  ensureStatsRecord,
  findSessionRef,
  loadStats,
  readRuntimeRecall,
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

  try {
    const recalledIds = await readRuntimeRecall(workspaceDir, sessionKey);
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
    await clearRuntimeRecall(workspaceDir, sessionKey);

    if (Array.isArray(event.messages)) {
      event.messages.push(`📈 Experience evolved: ${outcome} (${recalledIds.length} cards)`);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[${HOOK_NAME}] failed: ${message}`);
  }
}

