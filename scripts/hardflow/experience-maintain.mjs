#!/usr/bin/env node
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile, appendFile, access } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import path from "node:path";

const SCORE_VERSION = "experience-score-v1";

function clamp(v, min = 0, max = 1) {
  return Math.max(min, Math.min(max, v));
}

function nowIso() {
  return new Date().toISOString();
}

function toFixed4(v) {
  return Number(clamp(v).toFixed(4));
}

function parseArgs() {
  const args = process.argv.slice(2);
  const out = {
    workspace: process.cwd(),
    mode: "daily",
    dryRun: false,
  };
  for (let i = 0; i < args.length; i += 1) {
    const token = args[i];
    if (token === "--workspace") {
      out.workspace = args[i + 1] || out.workspace;
      i += 1;
      continue;
    }
    if (token === "--mode") {
      out.mode = args[i + 1] || out.mode;
      i += 1;
      continue;
    }
    if (token === "--dry-run") {
      out.dryRun = true;
    }
  }
  if (!["daily", "weekly", "monthly"].includes(out.mode)) {
    throw new Error(`invalid --mode: ${out.mode}`);
  }
  return out;
}

async function exists(filePath) {
  try {
    await access(filePath, fsConstants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function safeJsonParse(line) {
  try {
    return JSON.parse(line);
  } catch {
    return null;
  }
}

function tokenize(text) {
  return String(text || "")
    .toLowerCase()
    .split(/[^a-z0-9\u4e00-\u9fa5]+/g)
    .map((x) => x.trim())
    .filter((x) => x.length >= 2);
}

function overlapScore(a, b) {
  const ta = new Set(tokenize(a));
  const tb = new Set(tokenize(b));
  if (ta.size === 0 || tb.size === 0) {
    return 0;
  }
  let hits = 0;
  for (const t of ta) {
    if (tb.has(t)) {
      hits += 1;
    }
  }
  return hits / Math.max(ta.size, tb.size);
}

function makeCardText(card) {
  return [
    card.title,
    card.problem,
    card.rootCause,
    Array.isArray(card.solutionSteps) ? card.solutionSteps.join(" ") : "",
    card.verification,
    Array.isArray(card.tags) ? card.tags.join(" ") : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function stableHash(input) {
  return createHash("sha1").update(input).digest("hex");
}

function ensureStatsRecord(stats, id) {
  if (!stats.cards[id]) {
    stats.cards[id] = {
      reuseCount: 0,
      successCount: 0,
      failureCount: 0,
    };
  }
  return stats.cards[id];
}

function bayesianSuccess(statsRecord) {
  const success = Number(statsRecord?.successCount || 0);
  const fail = Number(statsRecord?.failureCount || 0);
  return (success + 1) / (success + fail + 2);
}

function daysSince(iso) {
  const ts = new Date(iso || "").getTime();
  if (!Number.isFinite(ts) || ts <= 0) {
    return 9999;
  }
  return Math.max(0, (Date.now() - ts) / (1000 * 3600 * 24));
}

function completenessScore(card) {
  const checks = [
    card.problem && String(card.problem).trim() !== "",
    card.rootCause && String(card.rootCause).trim() !== "",
    Array.isArray(card.solutionSteps) && card.solutionSteps.length > 0,
    card.verification && String(card.verification).trim() !== "",
    card.boundaries && String(card.boundaries).trim() !== "",
    card.rollback && String(card.rollback).trim() !== "",
    Array.isArray(card.tags) && card.tags.length > 0,
  ];
  const hits = checks.filter(Boolean).length;
  return hits / checks.length;
}

function verificationQuality(card) {
  const text = String(card.verification || "").toLowerCase();
  if (!text || text.includes("no explicit verification")) {
    return 0.2;
  }
  if (
    text.includes("pass") ||
    text.includes("smoke") ||
    text.includes("pytest") ||
    text.includes("\u9a8c\u8bc1")
  ) {
    return 1;
  }
  return 0.65;
}

function solveCoverage(card) {
  const steps = Array.isArray(card.solutionSteps) ? card.solutionSteps.length : 0;
  return clamp(steps / 4);
}

function metricsFor(card, statsRecord) {
  const recency = clamp(1 - daysSince(card.updatedAt || card.createdAt) / 120);
  const reliability = bayesianSuccess(statsRecord);
  const reuse = clamp(Math.log2(Number(statsRecord?.reuseCount || 0) + 1) / 2.8);
  const completeness = completenessScore(card);
  const verification = verificationQuality(card);
  const coverage = solveCoverage(card);
  const fail = Number(statsRecord?.failureCount || 0);
  const success = Number(statsRecord?.successCount || 0);
  const failPenalty = fail > success ? clamp((fail - success) / (fail + success + 1)) * 0.2 : 0;
  const score =
    completeness * 0.2 +
    verification * 0.15 +
    coverage * 0.1 +
    reliability * 0.25 +
    reuse * 0.2 +
    recency * 0.1 -
    failPenalty;
  return {
    score: clamp(score),
    quality: clamp(completeness * 0.65 + verification * 0.35),
    reliability,
    reuse: Number(statsRecord?.reuseCount || 0),
    success,
    fail,
    recencyDays: daysSince(card.updatedAt || card.createdAt),
  };
}

function lifecycleByMode(mode, m, isDuplicate) {
  if (isDuplicate) {
    return "deprecated";
  }
  const stableScore = mode === "monthly" ? 0.82 : 0.78;
  const candidateScore = mode === "monthly" ? 0.62 : 0.58;
  const staleDays = mode === "monthly" ? 180 : 240;
  if (
    m.score >= stableScore &&
    m.reliability >= 0.72 &&
    m.reuse >= 3 &&
    m.fail <= m.success + 1
  ) {
    return "stable";
  }
  if ((m.reliability < 0.35 && m.fail >= 2) || (m.recencyDays > staleDays && m.reuse === 0)) {
    return "deprecated";
  }
  if (m.score >= candidateScore && (m.reuse >= 1 || m.reliability >= 0.62)) {
    return "candidate";
  }
  return "draft";
}

function sharedTagScore(aTags, bTags) {
  const a = new Set(Array.isArray(aTags) ? aTags : []);
  const b = new Set(Array.isArray(bTags) ? bTags : []);
  if (a.size === 0 || b.size === 0) {
    return 0;
  }
  let hit = 0;
  for (const t of a) {
    if (b.has(t)) {
      hit += 1;
    }
  }
  return hit / Math.max(a.size, b.size);
}

async function loadState(workspace) {
  const root = path.join(workspace, ".workflow", "experience");
  const files = {
    root,
    cards: path.join(root, "cards.ndjson"),
    stats: path.join(root, "stats.json"),
    maintainDir: path.join(root, "maintenance"),
    memoryDir: path.join(workspace, "memory"),
  };
  if (!(await exists(files.cards))) {
    return { files, cards: [], stats: { cards: {} } };
  }
  const cardsRaw = await readFile(files.cards, "utf8");
  const cards = cardsRaw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => safeJsonParse(line))
    .filter(Boolean);

  let stats = { cards: {} };
  if (await exists(files.stats)) {
    const parsed = safeJsonParse(await readFile(files.stats, "utf8"));
    if (parsed && parsed.cards && typeof parsed.cards === "object") {
      stats = parsed;
    }
  }
  return { files, cards, stats };
}

function dedupCards(cards, metricsMap) {
  const byFingerprint = new Map();
  for (const card of cards) {
    const fp = String(card.fingerprint || card.id || "");
    if (!byFingerprint.has(fp)) {
      byFingerprint.set(fp, []);
    }
    byFingerprint.get(fp).push(card);
  }

  const canonicalMap = new Map();
  const duplicateReasons = new Map();
  const pickBest = (arr) =>
    arr
      .slice()
      .sort((a, b) => {
        const sa = metricsMap.get(a.id)?.score || 0;
        const sb = metricsMap.get(b.id)?.score || 0;
        if (sb !== sa) {
          return sb - sa;
        }
        return String(b.updatedAt || b.createdAt || "").localeCompare(String(a.updatedAt || a.createdAt || ""));
      })[0];

  for (const group of byFingerprint.values()) {
    const canonical = pickBest(group);
    for (const card of group) {
      canonicalMap.set(card.id, canonical.id);
      if (card.id !== canonical.id) {
        duplicateReasons.set(card.id, "exact-fingerprint");
      }
    }
  }

  const canonicalCards = cards.filter((c) => canonicalMap.get(c.id) === c.id);
  const sortedCanon = canonicalCards
    .slice()
    .sort((a, b) => (metricsMap.get(b.id)?.score || 0) - (metricsMap.get(a.id)?.score || 0));
  for (let i = 0; i < sortedCanon.length; i += 1) {
    const base = sortedCanon[i];
    const baseId = canonicalMap.get(base.id);
    if (baseId !== base.id) {
      continue;
    }
    for (let j = i + 1; j < sortedCanon.length; j += 1) {
      const cand = sortedCanon[j];
      if (canonicalMap.get(cand.id) !== cand.id) {
        continue;
      }
      const sim = overlapScore(makeCardText(base), makeCardText(cand));
      const tagSim = sharedTagScore(base.tags, cand.tags);
      if (sim >= 0.88 || (sim >= 0.72 && tagSim >= 0.66)) {
        canonicalMap.set(cand.id, base.id);
        duplicateReasons.set(cand.id, "near-duplicate");
      }
    }
  }
  return { canonicalMap, duplicateReasons };
}

function clusterCanonicalCards(cards, canonicalMap, metricsMap) {
  const canonicalCards = cards.filter((c) => canonicalMap.get(c.id) === c.id);
  const sorted = canonicalCards
    .slice()
    .sort((a, b) => (metricsMap.get(b.id)?.score || 0) - (metricsMap.get(a.id)?.score || 0));
  const clusters = [];
  const cardCluster = new Map();

  for (const card of sorted) {
    let bestIdx = -1;
    let bestScore = 0;
    for (let i = 0; i < clusters.length; i += 1) {
      const rep = clusters[i].representative;
      const sim = overlapScore(makeCardText(card), makeCardText(rep));
      const tagSim = sharedTagScore(card.tags, rep.tags);
      const s = sim * 0.75 + tagSim * 0.25;
      if (s > bestScore) {
        bestScore = s;
        bestIdx = i;
      }
    }
    if (bestIdx >= 0 && bestScore >= 0.42) {
      clusters[bestIdx].items.push(card);
      cardCluster.set(card.id, clusters[bestIdx].id);
      continue;
    }
    const id = `cluster-${stableHash(card.id).slice(0, 8)}`;
    clusters.push({
      id,
      representative: card,
      items: [card],
    });
    cardCluster.set(card.id, id);
  }
  return { clusters, cardCluster };
}

function summarizeClusters(clusters, scoredCards) {
  return clusters.map((cluster) => {
    const mergedTags = new Map();
    for (const card of cluster.items) {
      for (const tag of Array.isArray(card.tags) ? card.tags : []) {
        mergedTags.set(tag, (mergedTags.get(tag) || 0) + 1);
      }
    }
    const topTags = Array.from(mergedTags.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map((x) => x[0]);
    const topScore = Math.max(...cluster.items.map((x) => scoredCards.get(x.id)?.maintenanceScore || 0));
    return {
      id: cluster.id,
      representativeId: cluster.representative.id,
      size: cluster.items.length,
      topTags,
      topScore: toFixed4(topScore),
      members: cluster.items.map((x) => x.id),
    };
  });
}

async function writeOutputs({ files, cards, stats, report, clusterIndex, stableCards, mode, dryRun }) {
  if (dryRun) {
    return;
  }
  await mkdir(files.maintainDir, { recursive: true });
  await writeFile(
    files.cards,
    `${cards.map((card) => JSON.stringify(card)).join("\n")}\n`,
    "utf8",
  );
  await writeFile(files.stats, `${JSON.stringify(stats, null, 2)}\n`, "utf8");
  await writeFile(
    path.join(files.maintainDir, "latest-report.json"),
    `${JSON.stringify(report, null, 2)}\n`,
    "utf8",
  );
  await writeFile(
    path.join(files.maintainDir, "clusters.json"),
    `${JSON.stringify(clusterIndex, null, 2)}\n`,
    "utf8",
  );
  const stableDoc = [
    "# Stable Experience Candidates",
    "",
    `Generated at: ${report.generatedAt}`,
    `Mode: ${mode}`,
    `Score version: ${SCORE_VERSION}`,
    "",
    ...stableCards.slice(0, 20).map((card, idx) => {
      const score = card.maintenanceScore ?? 0;
      return [
        `## ${idx + 1}. ${card.title || card.id}`,
        `- ID: ${card.id}`,
        `- Score: ${score.toFixed(4)}`,
        `- Cluster: ${card.clusterId || "none"}`,
        `- Tags: ${(card.tags || []).join(", ") || "none"}`,
        `- Problem: ${String(card.problem || "").slice(0, 180)}`,
        "",
      ].join("\n");
    }),
  ].join("\n");
  await writeFile(path.join(files.maintainDir, "SOP_STABLE.md"), stableDoc, "utf8");

  await mkdir(files.memoryDir, { recursive: true });
  const day = report.generatedAt.slice(0, 10);
  const memoryFile = path.join(files.memoryDir, `${day}.md`);
  const summary = [
    "",
    `## Experience Maintenance ${report.generatedAt}`,
    `- mode: ${mode}`,
    `- cards: ${report.totals.cards}`,
    `- canonical: ${report.totals.canonical}`,
    `- duplicates: ${report.totals.duplicates}`,
    `- clusters: ${report.totals.clusters}`,
    `- stable/candidate/draft/deprecated: ${report.lifecycle.stable}/${report.lifecycle.candidate}/${report.lifecycle.draft}/${report.lifecycle.deprecated}`,
    `- promoted: ${report.lifecycleChanges.promoted}, demoted: ${report.lifecycleChanges.demoted}`,
  ].join("\n");
  await appendFile(memoryFile, `${summary}\n`, "utf8");
}

async function run() {
  const { workspace, mode, dryRun } = parseArgs();
  const generatedAt = nowIso();
  const state = await loadState(workspace);
  const { cards, stats, files } = state;
  if (cards.length === 0) {
    console.log(
      JSON.stringify({
        ok: true,
        mode,
        workspace,
        message: "no cards found",
      }),
    );
    return;
  }

  const metricsMap = new Map();
  for (const card of cards) {
    const statsRecord = ensureStatsRecord(stats, card.id);
    metricsMap.set(card.id, metricsFor(card, statsRecord));
  }

  const { canonicalMap, duplicateReasons } = dedupCards(cards, metricsMap);
  const { clusters, cardCluster } = clusterCanonicalCards(cards, canonicalMap, metricsMap);

  const scoredCards = new Map();
  let promoted = 0;
  let demoted = 0;
  for (const card of cards) {
    const metrics = metricsMap.get(card.id);
    const canonicalId = canonicalMap.get(card.id) || card.id;
    const isDuplicate = canonicalId !== card.id;
    const clusterId = cardCluster.get(canonicalId) || card.clusterId || "cluster-unknown";
    const previous = String(card.lifecycle || "draft");
    const lifecycle = lifecycleByMode(mode, metrics, isDuplicate);
    if (previous !== lifecycle) {
      if (
        (previous === "draft" && (lifecycle === "candidate" || lifecycle === "stable")) ||
        (previous === "candidate" && lifecycle === "stable")
      ) {
        promoted += 1;
      }
      if (
        (previous === "stable" && lifecycle !== "stable") ||
        (previous === "candidate" && (lifecycle === "draft" || lifecycle === "deprecated")) ||
        (previous === "draft" && lifecycle === "deprecated")
      ) {
        demoted += 1;
      }
    }
    const maintained = {
      ...card,
      canonicalId,
      clusterId,
      lifecycle,
      maintenanceScore: toFixed4(metrics.score),
      qualityScore: toFixed4(metrics.quality),
      scoreVersion: SCORE_VERSION,
      lastMaintainedAt: generatedAt,
      duplicateReason: duplicateReasons.get(card.id),
    };
    scoredCards.set(card.id, maintained);
    const statsRecord = ensureStatsRecord(stats, card.id);
    statsRecord.maintenanceScore = maintained.maintenanceScore;
    statsRecord.lifecycle = lifecycle;
    statsRecord.canonicalId = canonicalId;
    statsRecord.clusterId = clusterId;
    if (isDuplicate) {
      statsRecord.dedupedAt = generatedAt;
    }
  }

  const updatedCards = cards.map((card) => scoredCards.get(card.id));
  const lifecycleCounts = {
    stable: updatedCards.filter((x) => x.lifecycle === "stable").length,
    candidate: updatedCards.filter((x) => x.lifecycle === "candidate").length,
    draft: updatedCards.filter((x) => x.lifecycle === "draft").length,
    deprecated: updatedCards.filter((x) => x.lifecycle === "deprecated").length,
  };
  const canonical = updatedCards.filter((x) => x.canonicalId === x.id);
  const duplicates = updatedCards.length - canonical.length;
  const stableCards = canonical
    .filter((x) => x.lifecycle === "stable")
    .sort((a, b) => (b.maintenanceScore || 0) - (a.maintenanceScore || 0));
  const clusterIndex = summarizeClusters(clusters, scoredCards);
  const report = {
    generatedAt,
    mode,
    scoreVersion: SCORE_VERSION,
    totals: {
      cards: updatedCards.length,
      canonical: canonical.length,
      duplicates,
      clusters: clusterIndex.length,
    },
    lifecycle: lifecycleCounts,
    lifecycleChanges: {
      promoted,
      demoted,
    },
    topStable: stableCards.slice(0, 10).map((x) => ({
      id: x.id,
      title: x.title,
      score: x.maintenanceScore,
      clusterId: x.clusterId,
      tags: x.tags,
    })),
  };

  await writeOutputs({
    files,
    cards: updatedCards,
    stats,
    report,
    clusterIndex,
    stableCards,
    mode,
    dryRun,
  });

  console.log(JSON.stringify({ ok: true, workspace, mode, report }, null, 2));
}

run().catch((err) => {
  const message = err instanceof Error ? err.stack || err.message : String(err);
  console.error("[experience-maintain] failed");
  console.error(message);
  process.exit(1);
});
