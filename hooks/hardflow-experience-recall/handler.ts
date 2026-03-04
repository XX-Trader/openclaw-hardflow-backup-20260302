import {
  appendLinkGraphEvent,
  buildSignalKeyFromQuery,
  ensureStatsRecord,
  loadStats,
  rankCards,
  readPriorityBucketCards,
  readCards,
  readLinkGraphBoosts,
  readQueryHint,
  resolveLinkGraphStrategyPolicy,
  resolveAgentId,
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
  graphStrategy?: "balanced" | "harden" | "repair-only";
  graphDecayDays?: number;
  graphMaxEvents?: number;
  graphWeight?: number;
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
  const agentId = resolveAgentId(event);
  const topK = typeof opts.topK === "number" && opts.topK > 0 ? opts.topK : 5;

  try {
    let cards = await readPriorityBucketCards({
      workspaceDir,
      agentId,
      topK,
    });
    if (cards.length === 0) {
      cards = await readCards(workspaceDir);
    }
    if (cards.length === 0) {
      return;
    }
    const stats = await loadStats(workspaceDir);
    const query = await readQueryHint(workspaceDir);
    const queryKey = buildSignalKeyFromQuery(query);
    const graphPolicy = resolveLinkGraphStrategyPolicy({
      strategy: opts.graphStrategy || process.env.EVOLVE_STRATEGY,
      decayDays: opts.graphDecayDays,
      maxEvents: opts.graphMaxEvents,
      graphWeight: opts.graphWeight,
    });
    const graphBoosts = await readLinkGraphBoosts({
      workspaceDir,
      queryKey,
      agentId,
      strategy: graphPolicy.strategy,
      decayDays: graphPolicy.decayDays,
      maxEvents: graphPolicy.maxEvents,
    });
    const selected = rankCards({
      cards,
      stats,
      query,
      topK,
      graphBoosts,
      graphWeight: graphPolicy.graphWeight,
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
      queryKey,
      agentId,
    });
    await appendLinkGraphEvent({
      workspaceDir,
      event: {
        type: "attempt",
        ts: nowIso(),
        sessionKey: event?.sessionKey || "unknown",
        agentId,
        queryKey,
        query,
        cardIds: selectedIds,
      },
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
