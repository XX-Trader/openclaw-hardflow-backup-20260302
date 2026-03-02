import {
  ensureStatsRecord,
  loadStats,
  rankCards,
  readCards,
  readQueryHint,
  resolveHookOptions,
  resolveWorkspaceDir,
  saveStats,
  writeRecallDoc,
  writeRuntimeRecall,
  nowIso,
} from "../_lib/experience.ts";

type RecallOptions = {
  enabled?: boolean;
  topK?: number;
};

const HOOK_NAME = "hardflow-experience-recall";

function isBootstrap(event: any): boolean {
  return event?.type === "agent" && event?.action === "bootstrap";
}

export default async function hardflowExperienceRecall(event: any): Promise<void> {
  if (!isBootstrap(event)) {
    return;
  }
  const opts = resolveHookOptions<RecallOptions>(event, HOOK_NAME);
  if (opts.enabled === false) {
    return;
  }

  const workspaceDir = resolveWorkspaceDir(event);
  const topK = typeof opts.topK === "number" && opts.topK > 0 ? opts.topK : 5;

  try {
    const cards = await readCards(workspaceDir);
    if (cards.length === 0) {
      return;
    }
    const stats = await loadStats(workspaceDir);
    const query = await readQueryHint(workspaceDir);
    const selected = rankCards({
      cards,
      stats,
      query,
      topK,
    });
    const selectedIds = selected.map((c) => c.id);
    if (selectedIds.length === 0) {
      return;
    }

    const recall = await writeRecallDoc({
      workspaceDir,
      cards: selected,
      stats,
      query,
    });
    await writeRuntimeRecall({
      workspaceDir,
      sessionKey: event?.sessionKey || "unknown",
      cardIds: selectedIds,
      query,
    });

    for (const cardId of selectedIds) {
      const record = ensureStatsRecord(stats, cardId);
      record.reuseCount += 1;
      record.lastRecalledAt = nowIso();
    }
    await saveStats(workspaceDir, stats);

    const files = Array.isArray(event?.context?.bootstrapFiles)
      ? event.context.bootstrapFiles
      : [];
    files.push({
      name: "MEMORY.md",
      path: recall.path,
      content: recall.content,
      missing: false,
    });
    event.context.bootstrapFiles = files;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[${HOOK_NAME}] failed: ${message}`);
  }
}

