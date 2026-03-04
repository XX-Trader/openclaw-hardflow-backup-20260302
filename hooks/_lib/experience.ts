import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile, appendFile, access, rm } from "node:fs/promises";
import path from "node:path";

export const EXPERIENCE_ROOT_REL = path.join(".workflow", "experience");
const CARDS_REL = path.join(EXPERIENCE_ROOT_REL, "cards");
const RUNTIME_REL = path.join(EXPERIENCE_ROOT_REL, "runtime");
const CARDS_INDEX_REL = path.join(EXPERIENCE_ROOT_REL, "cards.ndjson");
const STATS_REL = path.join(EXPERIENCE_ROOT_REL, "stats.json");
const RECALL_DOC_REL = path.join(EXPERIENCE_ROOT_REL, "EXPERIENCE_RECALL.md");
const MAINTENANCE_REL = path.join(EXPERIENCE_ROOT_REL, "maintenance");
const PRIORITY_BUCKETS_REL = path.join(MAINTENANCE_REL, "priority-buckets.json");
const LINKGRAPH_REL = path.join(EXPERIENCE_ROOT_REL, "linkgraph");
const LINKGRAPH_EVENTS_REL = path.join(LINKGRAPH_REL, "events.jsonl");

export type MemoryTier = "reflex" | "long_term" | "recent" | "archive";

export type SessionMessage = {
  role: "user" | "assistant";
  text: string;
};

export type ExperienceCard = {
  id: string;
  createdAt: string;
  updatedAt: string;
  sourceAction: string;
  sessionKey: string;
  sessionId: string;
  title: string;
  problem: string;
  rootCause: string;
  solutionSteps: string[];
  verification: string;
  boundaries: string;
  failureSignals: string;
  rollback: string;
  tags: string[];
  fingerprint: string;
  cardFile: string;
  lifecycle?: "draft" | "candidate" | "stable" | "deprecated";
  canonicalId?: string;
  clusterId?: string;
  maintenanceScore?: number;
  qualityScore?: number;
  scoreVersion?: string;
  lastMaintainedAt?: string;
  duplicateReason?: string;
  agentId?: string;
  memoryTier?: MemoryTier;
  priorityScore?: number;
};

type StatsRecord = {
  reuseCount: number;
  successCount: number;
  failureCount: number;
  lastRecalledAt?: string;
  lastOutcome?: "success" | "failure" | "unknown";
  lastOutcomeAt?: string;
  maintenanceScore?: number;
  lifecycle?: "draft" | "candidate" | "stable" | "deprecated";
  canonicalId?: string;
  clusterId?: string;
  dedupedAt?: string;
  memoryTier?: MemoryTier;
  priorityScore?: number;
};

type StatsFile = {
  cards: Record<string, StatsRecord>;
};

type PriorityBucketsFile = {
  generatedAt?: string;
  scoreVersion?: string;
  tierOrder?: MemoryTier[];
  global?: Partial<Record<MemoryTier, ExperienceCard[]>>;
  byAgent?: Record<string, Partial<Record<MemoryTier, ExperienceCard[]>>>;
};

export type RuntimeRecallPayload = {
  sessionKey: string;
  cardIds: string[];
  query: string;
  queryKey: string;
  recalledAt: string;
  agentId?: string;
};

type LinkGraphEvent = {
  type: "attempt" | "outcome";
  ts: string;
  sessionKey: string;
  agentId: string;
  queryKey: string;
  query: string;
  cardIds: string[];
  outcome?: "success" | "failure" | "unknown";
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function dedupeStringArray(values: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of values) {
    const value = String(raw || "").trim();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    out.push(value);
  }
  return out;
}

export function safeSessionKey(sessionKey: string): string {
  const normalized = (sessionKey || "unknown").replace(/[^a-zA-Z0-9._-]+/g, "_");
  return normalized.length > 0 ? normalized : "unknown";
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function normalizeMemoryTier(value: string | undefined): MemoryTier {
  if (value === "reflex" || value === "long_term" || value === "recent" || value === "archive") {
    return value;
  }
  return "recent";
}

export function shortText(input: string, max = 280): string {
  const text = (input || "").replace(/\s+/g, " ").trim();
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max - 3)}...`;
}

export async function ensureExperienceDirs(workspaceDir: string): Promise<void> {
  await mkdir(path.join(workspaceDir, CARDS_REL), { recursive: true });
  await mkdir(path.join(workspaceDir, RUNTIME_REL), { recursive: true });
}

export async function existsFile(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

function extractText(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    const chunks: string[] = [];
    for (const item of content) {
      const text = (item as { text?: string })?.text;
      if (typeof text === "string" && text.length > 0) {
        chunks.push(text);
      }
    }
    return chunks.join("\n");
  }
  return "";
}

export async function readSessionMessages(
  sessionFile: string,
  maxMessages = 80,
): Promise<SessionMessage[]> {
  const raw = await readFile(sessionFile, "utf8");
  const lines = raw.split("\n").filter(Boolean);
  const rows: SessionMessage[] = [];
  for (const line of lines) {
    try {
      const entry = JSON.parse(line);
      if (entry?.type !== "message" || !entry?.message) {
        continue;
      }
      const msg = entry.message;
      const role = msg.role;
      if (role !== "user" && role !== "assistant") {
        continue;
      }
      const text = extractText(msg.content).trim();
      if (!text || text.startsWith("/")) {
        continue;
      }
      rows.push({ role, text });
    } catch {
      // ignore bad lines
    }
  }
  if (rows.length <= maxMessages) {
    return rows;
  }
  return rows.slice(rows.length - maxMessages);
}

function findFirstLineByPattern(lines: string[], patterns: RegExp[]): string {
  for (const line of lines) {
    const text = line.trim();
    if (!text) {
      continue;
    }
    for (const pattern of patterns) {
      if (pattern.test(text)) {
        return text;
      }
    }
  }
  return "";
}

function extractSteps(lines: string[]): string[] {
  const out: string[] = [];
  for (const line of lines) {
    const text = line.trim();
    if (!text) {
      continue;
    }
    if (/^(\d+[\.\)]|[-*])\s+/.test(text)) {
      out.push(text.replace(/^(\d+[\.\)]|[-*])\s+/, ""));
    } else if (/^(step|steps)\s*\d+/i.test(text)) {
      out.push(text);
    }
    if (out.length >= 8) {
      break;
    }
  }
  return out;
}

const TAG_RULES: Array<{ tag: string; keys: string[] }> = [
  { tag: "deployment", keys: ["deploy", "gateway", "restart", "release"] },
  { tag: "config", keys: ["config", "json", "env", "variable"] },
  { tag: "network", keys: ["network", "socket", "dns", "timeout", "connect"] },
  { tag: "database", keys: ["mysql", "redis", "database", "migration", "sql"] },
  { tag: "frontend", keys: ["vue", "react", "frontend", "ui"] },
  { tag: "backend", keys: ["django", "fastapi", "backend", "api"] },
  { tag: "testing", keys: ["test", "pytest", "verify", "smoke", "pass"] },
  { tag: "hooks", keys: ["hook", "hooks", "event", "bootstrap"] },
  { tag: "openclaw", keys: ["openclaw", "lobster", "agent", "session"] },
];

function extractTags(raw: string): string[] {
  const text = raw.toLowerCase();
  const tags: string[] = [];
  for (const rule of TAG_RULES) {
    if (rule.keys.some((key) => text.includes(key))) {
      tags.push(rule.tag);
    }
  }
  return tags.slice(0, 8);
}

function buildTitle(problem: string): string {
  if (!problem) {
    return "Experience Card";
  }
  return shortText(problem, 48);
}

function hashFingerprint(input: string): string {
  return createHash("sha1").update(input).digest("hex");
}

function toSlug(input: string): string {
  const normalized = (input || "experience")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  return normalized || "experience";
}

export function buildCardFromMessages(params: {
  messages: SessionMessage[];
  sourceAction: string;
  sessionKey: string;
  sessionId: string;
  now: string;
  agentId?: string;
}): ExperienceCard | null {
  const { messages, sourceAction, sessionKey, sessionId, now, agentId } = params;
  if (!messages || messages.length < 2) {
    return null;
  }

  const users = messages.filter((m) => m.role === "user");
  const assistants = messages.filter((m) => m.role === "assistant");
  if (users.length === 0 || assistants.length === 0) {
    return null;
  }

  const problem = shortText(users[users.length - 1]?.text || "", 320);
  const assistantText = assistants.map((m) => m.text).join("\n");
  const allLines = assistantText.split("\n").map((line) => line.trim());

  const rootCause =
    findFirstLineByPattern(allLines, [
      /\u6839\u56e0/i,
      /\u539f\u56e0/i,
      /root cause/i,
      /because/i,
      /due to/i,
    ]) || "No explicit root cause found.";
  const verification =
    findFirstLineByPattern(allLines, [
      /\u9a8c\u8bc1/i,
      /\u6d4b\u8bd5/i,
      /\u901a\u8fc7/i,
      /verify/i,
      /pass/i,
      /smoke/i,
    ]) || "No explicit verification found.";
  const boundaries =
    findFirstLineByPattern(allLines, [
      /\u8fb9\u754c/i,
      /\u9650\u5236/i,
      /scope/i,
      /limit/i,
      /only/i,
    ]) || "No boundary notes.";
  const failureSignals =
    findFirstLineByPattern(allLines, [
      /\u62a5\u9519/i,
      /\u5f02\u5e38/i,
      /failed/i,
      /error/i,
      /timeout/i,
    ]) || "No failure signals captured.";
  const rollback =
    findFirstLineByPattern(allLines, [
      /\u56de\u6eda/i,
      /\u6062\u590d/i,
      /rollback/i,
      /revert/i,
    ]) || "No rollback steps captured.";
  const solutionSteps = extractSteps(allLines);
  const tags = extractTags(`${problem}\n${assistantText}`);

  const fingerprint = hashFingerprint(
    [problem, rootCause, solutionSteps.join("|"), verification, tags.join("|")].join("||"),
  );
  const id = fingerprint.slice(0, 16);
  const title = buildTitle(problem);
  const cardFile = path.join(
    CARDS_REL,
    `${now.slice(0, 10)}-${toSlug(title)}-${id.slice(0, 6)}.md`,
  );

  return {
    id,
    createdAt: now,
    updatedAt: now,
    sourceAction,
    sessionKey,
    sessionId,
    title,
    problem,
    rootCause,
    solutionSteps,
    verification,
    boundaries,
    failureSignals,
    rollback,
    tags,
    fingerprint,
    cardFile,
    agentId: agentId || undefined,
    memoryTier: "recent",
    priorityScore: 0.5,
  };
}

export async function readCards(workspaceDir: string): Promise<ExperienceCard[]> {
  const file = path.join(workspaceDir, CARDS_INDEX_REL);
  if (!(await existsFile(file))) {
    return [];
  }
  const raw = await readFile(file, "utf8");
  const cards: ExperienceCard[] = [];
  for (const line of raw.split("\n")) {
    const text = line.trim();
    if (!text) {
      continue;
    }
    try {
      cards.push(JSON.parse(text));
    } catch {
      // ignore bad lines
    }
  }
  return cards;
}

export async function appendCard(workspaceDir: string, card: ExperienceCard): Promise<void> {
  await ensureExperienceDirs(workspaceDir);
  const indexFile = path.join(workspaceDir, CARDS_INDEX_REL);
  await appendFile(indexFile, `${JSON.stringify(card)}\n`, "utf8");

  const md = [
    `# ${card.title}`,
    "",
    `- ID: ${card.id}`,
    `- Time: ${card.createdAt}`,
    `- Source action: ${card.sourceAction}`,
    `- Session: ${card.sessionKey}`,
    `- Tags: ${card.tags.join(", ") || "none"}`,
    "",
    "## Problem",
    card.problem || "N/A",
    "",
    "## Root Cause",
    card.rootCause || "N/A",
    "",
    "## Solution Steps",
    ...(card.solutionSteps.length > 0
      ? card.solutionSteps.map((step, idx) => `${idx + 1}. ${step}`)
      : ["1. N/A"]),
    "",
    "## Verification",
    card.verification || "N/A",
    "",
    "## Boundaries",
    card.boundaries || "N/A",
    "",
    "## Failure Signals",
    card.failureSignals || "N/A",
    "",
    "## Rollback",
    card.rollback || "N/A",
    "",
  ].join("\n");

  const cardPath = path.join(workspaceDir, card.cardFile);
  await mkdir(path.dirname(cardPath), { recursive: true });
  await writeFile(cardPath, md, "utf8");
}

export function hasMeaningfulFixSignal(messages: SessionMessage[]): boolean {
  const text = messages.map((m) => m.text).join("\n").toLowerCase();
  const cues = [
    "\u5df2\u4fee\u590d",
    "\u4fee\u590d",
    "\u89e3\u51b3",
    "\u901a\u8fc7",
    "\u9a8c\u8bc1",
    "fixed",
    "resolved",
    "pass",
    "rollback",
  ];
  return cues.some((cue) => text.includes(cue.toLowerCase()));
}

export async function loadStats(workspaceDir: string): Promise<StatsFile> {
  const file = path.join(workspaceDir, STATS_REL);
  if (!(await existsFile(file))) {
    return { cards: {} };
  }
  try {
    const raw = await readFile(file, "utf8");
    const parsed = JSON.parse(raw) as StatsFile;
    if (!parsed.cards || typeof parsed.cards !== "object") {
      return { cards: {} };
    }
    return parsed;
  } catch {
    return { cards: {} };
  }
}

export async function saveStats(workspaceDir: string, stats: StatsFile): Promise<void> {
  const file = path.join(workspaceDir, STATS_REL);
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, JSON.stringify(stats, null, 2), "utf8");
}

export function ensureStatsRecord(stats: StatsFile, cardId: string): StatsRecord {
  if (!stats.cards[cardId]) {
    stats.cards[cardId] = {
      reuseCount: 0,
      successCount: 0,
      failureCount: 0,
    };
  }
  return stats.cards[cardId];
}

export function confidenceOf(stats: StatsRecord | undefined): number {
  if (!stats) {
    return 0.5;
  }
  if (stats.reuseCount <= 0) {
    return 0.5;
  }
  return (stats.successCount + 1) / (stats.reuseCount + 2);
}

function normalizeLifecycle(value: string | undefined): "draft" | "candidate" | "stable" | "deprecated" {
  if (value === "candidate" || value === "stable" || value === "deprecated") {
    return value;
  }
  return "draft";
}

function lifecycleBias(lifecycle: "draft" | "candidate" | "stable" | "deprecated"): number {
  if (lifecycle === "stable") {
    return 0.12;
  }
  if (lifecycle === "candidate") {
    return 0.05;
  }
  if (lifecycle === "deprecated") {
    return -0.45;
  }
  return 0;
}

function memoryTierBias(tier: MemoryTier): number {
  if (tier === "reflex") {
    return 0.24;
  }
  if (tier === "long_term") {
    return 0.12;
  }
  if (tier === "archive") {
    return -0.35;
  }
  return 0.03;
}

function tokenize(text: string): string[] {
  return (text || "")
    .toLowerCase()
    .split(/[^a-z0-9\u4e00-\u9fa5]+/g)
    .map((x) => x.trim())
    .filter((x) => x.length >= 2);
}

function overlapScore(a: string, b: string): number {
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

export function buildSignalKeyFromQuery(query: string): string {
  const normalized = shortText(String(query || ""), 1200);
  const tokens = Array.from(new Set(tokenize(normalized))).sort();
  if (tokens.length === 0) {
    return "empty";
  }
  const payload = tokens.slice(0, 24).join("|");
  return createHash("sha1").update(payload).digest("hex").slice(0, 20);
}

export async function readQueryHint(workspaceDir: string): Promise<string> {
  const candidates = ["todo.md", "done.md"];
  const chunks: string[] = [];
  for (const rel of candidates) {
    const file = path.join(workspaceDir, rel);
    if (!(await existsFile(file))) {
      continue;
    }
    try {
      chunks.push(await readFile(file, "utf8"));
    } catch {
      // ignore
    }
  }
  return shortText(chunks.join("\n"), 2000);
}

export function rankCards(params: {
  cards: ExperienceCard[];
  stats: StatsFile;
  query: string;
  topK: number;
  graphBoosts?: Record<string, number>;
}): ExperienceCard[] {
  const { cards, stats, query, topK, graphBoosts } = params;
  const now = Date.now();
  const scored = cards
    .map((card) => {
      const canonicalId = card.canonicalId || card.id;
      if (canonicalId !== card.id) {
        return null;
      }
      const record = stats.cards[card.id];
      const confidence = confidenceOf(record);
      const relevance = overlapScore(
        query,
        `${card.problem}\n${card.rootCause}\n${card.tags.join(" ")}`,
      );
      const ageDays = Math.max(
        0,
        (now - new Date(card.updatedAt || card.createdAt).getTime()) / (1000 * 3600 * 24),
      );
      const recency = Math.max(0, 1 - ageDays / 30);
      const lifecycle = normalizeLifecycle(card.lifecycle || record?.lifecycle);
      if (lifecycle === "deprecated") {
        return null;
      }
      const tier = normalizeMemoryTier(card.memoryTier || record?.memoryTier);
      const quality = Math.max(
        0,
        Math.min(
          1,
          typeof card.maintenanceScore === "number"
            ? card.maintenanceScore
            : typeof record?.maintenanceScore === "number"
              ? record.maintenanceScore
              : 0.5,
        ),
      );
      const graphBoost = clamp(Number(graphBoosts?.[card.id] || 0), -1, 1);
      const score =
        relevance * 0.5 +
        confidence * 0.2 +
        recency * 0.1 +
        quality * 0.2 +
        lifecycleBias(lifecycle) +
        memoryTierBias(tier) +
        graphBoost * 0.25 +
        Math.max(
          0,
          Math.min(
            0.2,
            typeof card.priorityScore === "number"
              ? card.priorityScore * 0.2
              : typeof record?.priorityScore === "number"
                ? record.priorityScore * 0.2
                : 0,
          ),
        );
      return { card, score };
    })
    .filter((x): x is { card: ExperienceCard; score: number } => Boolean(x))
    .sort((a, b) => b.score - a.score);
  return scored.slice(0, topK).map((x) => x.card);
}

function normalizeArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((x) => String(x || "").trim())
    .filter((x) => x.length > 0);
}

function normalizeBucketCard(raw: unknown): ExperienceCard | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const item = raw as Record<string, unknown>;
  const id = String(item.id || "").trim();
  if (!id) {
    return null;
  }
  const createdAt = String(item.createdAt || item.updatedAt || nowIso());
  const updatedAt = String(item.updatedAt || createdAt);
  return {
    id,
    createdAt,
    updatedAt,
    sourceAction: String(item.sourceAction || "maintenance"),
    sessionKey: String(item.sessionKey || ""),
    sessionId: String(item.sessionId || ""),
    title: shortText(String(item.title || "Experience Card"), 96),
    problem: String(item.problem || "N/A"),
    rootCause: String(item.rootCause || "N/A"),
    solutionSteps: normalizeArray(item.solutionSteps),
    verification: String(item.verification || "N/A"),
    boundaries: String(item.boundaries || "N/A"),
    failureSignals: String(item.failureSignals || "N/A"),
    rollback: String(item.rollback || "N/A"),
    tags: normalizeArray(item.tags),
    fingerprint: String(item.fingerprint || id),
    cardFile: String(item.cardFile || ""),
    lifecycle:
      item.lifecycle === "stable" ||
      item.lifecycle === "candidate" ||
      item.lifecycle === "deprecated"
        ? (item.lifecycle as "stable" | "candidate" | "deprecated")
        : "draft",
    canonicalId: String(item.canonicalId || id),
    clusterId: String(item.clusterId || ""),
    maintenanceScore:
      typeof item.maintenanceScore === "number" ? item.maintenanceScore : undefined,
    qualityScore: typeof item.qualityScore === "number" ? item.qualityScore : undefined,
    scoreVersion: typeof item.scoreVersion === "string" ? item.scoreVersion : undefined,
    lastMaintainedAt:
      typeof item.lastMaintainedAt === "string" ? item.lastMaintainedAt : undefined,
    duplicateReason:
      typeof item.duplicateReason === "string" ? item.duplicateReason : undefined,
    agentId: typeof item.agentId === "string" ? item.agentId : undefined,
    memoryTier: normalizeMemoryTier(String(item.memoryTier || "recent")),
    priorityScore: typeof item.priorityScore === "number" ? item.priorityScore : undefined,
  };
}

export async function readPriorityBuckets(
  workspaceDir: string,
): Promise<PriorityBucketsFile | null> {
  const file = path.join(workspaceDir, PRIORITY_BUCKETS_REL);
  if (!(await existsFile(file))) {
    return null;
  }
  try {
    const raw = await readFile(file, "utf8");
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    return parsed as PriorityBucketsFile;
  } catch {
    return null;
  }
}

export async function readPriorityBucketCards(params: {
  workspaceDir: string;
  agentId?: string;
  topK: number;
}): Promise<ExperienceCard[]> {
  const { workspaceDir, agentId, topK } = params;
  const buckets = await readPriorityBuckets(workspaceDir);
  if (!buckets) {
    return [];
  }

  const order: MemoryTier[] =
    Array.isArray(buckets.tierOrder) && buckets.tierOrder.length > 0
      ? buckets.tierOrder.map((x) => normalizeMemoryTier(String(x)))
      : ["reflex", "long_term", "recent", "archive"];
  const picked: ExperienceCard[] = [];
  const seen = new Set<string>();
  const target = Math.max(topK * 8, topK + 8);

  const appendFromBuckets = (group: Partial<Record<MemoryTier, ExperienceCard[]>> | undefined): void => {
    if (!group) {
      return;
    }
    for (const tier of order) {
      const rows = Array.isArray(group[tier]) ? group[tier] : [];
      for (const row of rows) {
        const card = normalizeBucketCard(row);
        if (!card || seen.has(card.id)) {
          continue;
        }
        seen.add(card.id);
        picked.push(card);
        if (picked.length >= target) {
          return;
        }
      }
      if (picked.length >= target) {
        return;
      }
    }
  };

  const normalizedAgent = String(agentId || "").trim();
  if (normalizedAgent && buckets.byAgent && buckets.byAgent[normalizedAgent]) {
    appendFromBuckets(buckets.byAgent[normalizedAgent]);
  }
  appendFromBuckets(buckets.global);

  return picked;
}

function normalizeLinkGraphEvent(raw: unknown): LinkGraphEvent | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const item = raw as Record<string, unknown>;
  const type = item.type === "attempt" || item.type === "outcome" ? item.type : null;
  if (!type) {
    return null;
  }
  const query = shortText(String(item.query || ""), 800);
  const queryKeyRaw = String(item.queryKey || "").trim();
  const queryKey = queryKeyRaw || buildSignalKeyFromQuery(query);
  const cardIds = dedupeStringArray(
    Array.isArray(item.cardIds)
      ? item.cardIds.map((x) => String(x || ""))
      : [],
  );
  if (cardIds.length === 0) {
    return null;
  }
  const agentId = String(item.agentId || "unknown").trim() || "unknown";
  const sessionKey = String(item.sessionKey || "unknown").trim() || "unknown";
  const ts = String(item.ts || "").trim() || nowIso();
  const outcome =
    item.outcome === "success" || item.outcome === "failure" || item.outcome === "unknown"
      ? item.outcome
      : undefined;
  return {
    type,
    ts,
    sessionKey,
    agentId,
    queryKey,
    query,
    cardIds,
    outcome,
  };
}

function recencyWeightByTs(ts: string, nowMs: number): number {
  const tsMs = Number(new Date(ts).getTime());
  if (!Number.isFinite(tsMs) || tsMs <= 0) {
    return 0.35;
  }
  const ageDays = Math.max(0, (nowMs - tsMs) / (1000 * 3600 * 24));
  return Math.exp(-ageDays / 30);
}

export async function appendLinkGraphEvent(params: {
  workspaceDir: string;
  event: LinkGraphEvent;
}): Promise<void> {
  const filePath = path.join(params.workspaceDir, LINKGRAPH_EVENTS_REL);
  const normalized = normalizeLinkGraphEvent(params.event);
  if (!normalized) {
    return;
  }
  await mkdir(path.dirname(filePath), { recursive: true });
  await appendFile(filePath, `${JSON.stringify(normalized)}\n`, "utf8");
}

export async function readLinkGraphBoosts(params: {
  workspaceDir: string;
  queryKey: string;
  agentId?: string;
  maxEvents?: number;
}): Promise<Record<string, number>> {
  const filePath = path.join(params.workspaceDir, LINKGRAPH_EVENTS_REL);
  if (!(await existsFile(filePath))) {
    return {};
  }
  const queryKey = String(params.queryKey || "").trim();
  if (!queryKey) {
    return {};
  }
  const raw = await readFile(filePath, "utf8");
  const rows = raw.split("\n").filter(Boolean);
  if (rows.length === 0) {
    return {};
  }

  const maxEvents =
    typeof params.maxEvents === "number" && params.maxEvents > 0 ? params.maxEvents : 2000;
  const start = Math.max(0, rows.length - maxEvents);
  const normalizedAgent = String(params.agentId || "").trim();
  const nowMs = Date.now();
  const boosts = new Map<string, number>();

  const addBoost = (cardId: string, delta: number): void => {
    const current = boosts.get(cardId) || 0;
    boosts.set(cardId, clamp(current + delta, -1, 1));
  };

  for (let idx = start; idx < rows.length; idx += 1) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(rows[idx]);
    } catch {
      continue;
    }
    const event = normalizeLinkGraphEvent(parsed);
    if (!event || event.queryKey !== queryKey) {
      continue;
    }

    const sameAgent = normalizedAgent && event.agentId === normalizedAgent;
    const weight = recencyWeightByTs(event.ts, nowMs);
    let base = 0;
    if (event.type === "attempt") {
      base = sameAgent ? 0.05 : 0.02;
    } else if (event.outcome === "success") {
      base = sameAgent ? 0.5 : 0.28;
    } else if (event.outcome === "failure") {
      base = sameAgent ? -0.55 : -0.32;
    } else {
      base = sameAgent ? 0.02 : 0.01;
    }

    const delta = clamp(base * weight, -0.8, 0.8);
    for (const cardId of event.cardIds) {
      addBoost(cardId, delta);
    }
  }

  const out: Record<string, number> = {};
  for (const [cardId, value] of boosts.entries()) {
    out[cardId] = clamp(value, -1, 1);
  }
  return out;
}

export async function writeRecallDoc(params: {
  workspaceDir: string;
  cards: ExperienceCard[];
  stats: StatsFile;
  query: string;
}): Promise<{ path: string; content: string }> {
  const { workspaceDir, cards, stats, query } = params;
  const lines: string[] = [];
  lines.push("# Experience Recall (Auto)");
  lines.push("");
  lines.push(`Generated at: ${nowIso()}`);
  lines.push(`Query hint: ${shortText(query || "none", 260)}`);
  lines.push("");
  lines.push("Usage policy:");
  lines.push("1. Reuse only when pattern matches.");
  lines.push("2. Run minimum verification before broad changes.");
  lines.push("3. Prefer current repo state if conflicts appear.");
  lines.push("");
  if (cards.length === 0) {
    lines.push("No recall candidates.");
    lines.push("");
  } else {
    cards.forEach((card, idx) => {
      const conf = confidenceOf(stats.cards[card.id]).toFixed(2);
      lines.push(`## ${idx + 1}. ${card.title}`);
      lines.push(`- ID: ${card.id}`);
      lines.push(`- Confidence: ${conf}`);
      lines.push(`- Tier: ${normalizeMemoryTier(card.memoryTier)}`);
      if (typeof card.priorityScore === "number") {
        lines.push(`- Priority score: ${card.priorityScore.toFixed(4)}`);
      }
      if (card.agentId) {
        lines.push(`- Agent: ${card.agentId}`);
      }
      lines.push(`- Tags: ${card.tags.join(", ") || "none"}`);
      lines.push(`- Problem: ${shortText(card.problem, 180)}`);
      lines.push(`- Root cause: ${shortText(card.rootCause, 180)}`);
      lines.push("- Steps:");
      if (card.solutionSteps.length === 0) {
        lines.push("  - N/A");
      } else {
        for (const step of card.solutionSteps.slice(0, 4)) {
          lines.push(`  - ${shortText(step, 160)}`);
        }
      }
      lines.push(`- Verification: ${shortText(card.verification, 160)}`);
      lines.push(`- Rollback: ${shortText(card.rollback, 160)}`);
      lines.push(`- Card file: ${card.cardFile}`);
      lines.push("");
    });
  }
  const content = lines.join("\n");
  const filePath = path.join(workspaceDir, RECALL_DOC_REL);
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, content, "utf8");
  return { path: filePath, content };
}

export async function writeRuntimeRecall(params: {
  workspaceDir: string;
  sessionKey: string;
  cardIds: string[];
  query: string;
  queryKey?: string;
  agentId?: string;
}): Promise<void> {
  const filePath = path.join(
    params.workspaceDir,
    RUNTIME_REL,
    `${safeSessionKey(params.sessionKey)}.json`,
  );
  const query = shortText(params.query, 600);
  const queryKey = String(params.queryKey || "").trim() || buildSignalKeyFromQuery(query);
  const data = {
    sessionKey: params.sessionKey,
    cardIds: dedupeStringArray(params.cardIds || []),
    query,
    queryKey,
    recalledAt: nowIso(),
    agentId: String(params.agentId || "").trim() || undefined,
  };
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, JSON.stringify(data, null, 2), "utf8");
}

export async function readRuntimeRecallPayload(
  workspaceDir: string,
  sessionKey: string,
): Promise<RuntimeRecallPayload | null> {
  const filePath = path.join(workspaceDir, RUNTIME_REL, `${safeSessionKey(sessionKey)}.json`);
  if (!(await existsFile(filePath))) {
    return null;
  }
  try {
    const raw = await readFile(filePath, "utf8");
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const cardIds = dedupeStringArray(
      Array.isArray(parsed.cardIds) ? parsed.cardIds.map((x) => String(x || "")) : [],
    );
    if (cardIds.length === 0) {
      return null;
    }
    const query = shortText(String(parsed.query || ""), 600);
    const queryKey =
      String(parsed.queryKey || "").trim() || buildSignalKeyFromQuery(query || "empty");
    const recalledAt = String(parsed.recalledAt || "").trim() || nowIso();
    const agentIdRaw = String(parsed.agentId || "").trim();
    return {
      sessionKey: String(parsed.sessionKey || sessionKey),
      cardIds,
      query,
      queryKey,
      recalledAt,
      agentId: agentIdRaw || undefined,
    };
  } catch {
    return null;
  }
}

export async function readRuntimeRecall(
  workspaceDir: string,
  sessionKey: string,
): Promise<string[]> {
  const payload = await readRuntimeRecallPayload(workspaceDir, sessionKey);
  return payload?.cardIds || [];
}

export async function clearRuntimeRecall(workspaceDir: string, sessionKey: string): Promise<void> {
  const filePath = path.join(workspaceDir, RUNTIME_REL, `${safeSessionKey(sessionKey)}.json`);
  try {
    await rm(filePath, { force: true });
  } catch {
    // ignore
  }
}

export async function resolveOutcome(params: {
  workspaceDir: string;
  sessionFile?: string;
}): Promise<"success" | "failure" | "unknown"> {
  const gateDir = path.join(params.workspaceDir, ".workflow", "gates");
  const required = ["tester", "reviewer", "api_doc"];
  let seen = 0;
  let failed = 0;
  for (const gate of required) {
    const filePath = path.join(gateDir, `${gate}.json`);
    if (!(await existsFile(filePath))) {
      continue;
    }
    seen += 1;
    try {
      const raw = await readFile(filePath, "utf8");
      const data = JSON.parse(raw);
      if (data?.passed !== true) {
        failed += 1;
      }
    } catch {
      failed += 1;
    }
  }
  if (seen > 0) {
    return failed === 0 ? "success" : "failure";
  }

  if (params.sessionFile && (await existsFile(params.sessionFile))) {
    const messages = await readSessionMessages(params.sessionFile, 30);
    const text = messages.map((m) => m.text).join("\n").toLowerCase();
    if (/(success|passed|resolved|fixed|\u901a\u8fc7|\u6210\u529f)/i.test(text)) {
      return "success";
    }
    if (/(failed|error|timeout|\u5931\u8d25|\u62a5\u9519|\u5f02\u5e38)/i.test(text)) {
      return "failure";
    }
  }
  return "unknown";
}

export function resolveHookOptions<T extends Record<string, unknown>>(
  event: any,
  hookName: string,
): T {
  const cfg = event?.context?.cfg;
  return (cfg?.hooks?.internal?.entries?.[hookName] ?? {}) as T;
}

export function resolveWorkspaceDir(event: any): string {
  return event?.context?.workspaceDir || process.cwd();
}

export function resolveAgentId(event: any): string {
  const candidates = [
    event?.context?.agentId,
    event?.context?.targetAgentId,
    event?.context?.receiverAgentId,
    event?.context?.bindingAgentId,
    event?.agentId,
  ];
  for (const item of candidates) {
    const value = String(item || "").trim();
    if (value) {
      return value;
    }
  }
  return "unknown";
}

export function findSessionRef(event: any): { sessionFile?: string; sessionId: string } {
  const action = event?.action;
  const ctx = event?.context ?? {};
  if (action === "new" || action === "reset") {
    const previous = ctx.previousSessionEntry ?? ctx.sessionEntry ?? {};
    return {
      sessionFile: previous?.sessionFile,
      sessionId: previous?.sessionId ?? "",
    };
  }
  const current = ctx.sessionEntry ?? {};
  return {
    sessionFile: current?.sessionFile,
    sessionId: current?.sessionId ?? ctx?.sessionId ?? "",
  };
}
