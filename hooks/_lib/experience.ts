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
const ANTI_PATTERNS_REL = path.join(LINKGRAPH_REL, "anti-patterns.json");
const REFLECTION_STATE_REL = path.join(LINKGRAPH_REL, "reflection-state.json");

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

export type EvolutionStrategy = "balanced" | "harden" | "repair-only";

export type LinkGraphStrategyPolicy = {
  strategy: EvolutionStrategy;
  decayDays: number;
  maxEvents: number;
  graphWeight: number;
  attemptSameAgent: number;
  attemptCrossAgent: number;
  successSameAgent: number;
  successCrossAgent: number;
  failureSameAgent: number;
  failureCrossAgent: number;
  unknownSameAgent: number;
  unknownCrossAgent: number;
  eventContributionCap: number;
};

export type StrategyRatios = {
  repair: number;
  optimize: number;
  innovate: number;
};

type ReflectionState = {
  recallCount: number;
  lastComputedRound: number;
  lastComputedAt?: string;
  strategy: EvolutionStrategy;
  ratios: StrategyRatios;
  windowDays: number;
  consideredOutcomes: number;
  successCount: number;
  failureCount: number;
  unknownCount: number;
  successRate: number;
  failureRate: number;
  unknownRate: number;
  reason: string;
};

type AntiPatternCard = {
  failureCount: number;
  lastFailureAt?: string;
  agents?: string[];
};

type AntiPatternEntry = {
  queryKey: string;
  querySamples: string[];
  failureCount: number;
  successCount: number;
  lastOutcomeAt?: string;
  lastFailureAt?: string;
  cards: Record<string, AntiPatternCard>;
};

type AntiPatternLibrary = {
  updatedAt: string;
  entries: Record<string, AntiPatternEntry>;
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

export function normalizeEvolutionStrategy(
  value: string | undefined,
  fallback: EvolutionStrategy = "balanced",
): EvolutionStrategy {
  const normalized = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/_/g, "-");
  if (normalized === "harden") {
    return "harden";
  }
  if (normalized === "repair-only") {
    return "repair-only";
  }
  if (normalized === "balanced") {
    return "balanced";
  }
  return fallback;
}

function baseLinkGraphPolicyFor(strategy: EvolutionStrategy): LinkGraphStrategyPolicy {
  if (strategy === "harden") {
    return {
      strategy,
      decayDays: 24,
      maxEvents: 2500,
      graphWeight: 0.3,
      attemptSameAgent: 0.03,
      attemptCrossAgent: 0.01,
      successSameAgent: 0.38,
      successCrossAgent: 0.22,
      failureSameAgent: -0.72,
      failureCrossAgent: -0.44,
      unknownSameAgent: 0.01,
      unknownCrossAgent: 0.005,
      eventContributionCap: 0.9,
    };
  }
  if (strategy === "repair-only") {
    return {
      strategy,
      decayDays: 14,
      maxEvents: 3000,
      graphWeight: 0.36,
      attemptSameAgent: 0.01,
      attemptCrossAgent: 0,
      successSameAgent: 0.18,
      successCrossAgent: 0.08,
      failureSameAgent: -0.95,
      failureCrossAgent: -0.62,
      unknownSameAgent: 0,
      unknownCrossAgent: 0,
      eventContributionCap: 1,
    };
  }
  return {
    strategy: "balanced",
    decayDays: 30,
    maxEvents: 2000,
    graphWeight: 0.25,
    attemptSameAgent: 0.05,
    attemptCrossAgent: 0.02,
    successSameAgent: 0.5,
    successCrossAgent: 0.28,
    failureSameAgent: -0.55,
    failureCrossAgent: -0.32,
    unknownSameAgent: 0.02,
    unknownCrossAgent: 0.01,
    eventContributionCap: 0.8,
  };
}

export function resolveLinkGraphStrategyPolicy(params: {
  strategy?: string;
  decayDays?: number;
  maxEvents?: number;
  graphWeight?: number;
}): LinkGraphStrategyPolicy {
  const strategy = normalizeEvolutionStrategy(params.strategy, "balanced");
  const base = baseLinkGraphPolicyFor(strategy);
  const decayDays =
    typeof params.decayDays === "number" ? Math.round(clamp(params.decayDays, 3, 120)) : base.decayDays;
  const maxEvents =
    typeof params.maxEvents === "number"
      ? Math.round(clamp(params.maxEvents, 200, 20000))
      : base.maxEvents;
  const graphWeight =
    typeof params.graphWeight === "number"
      ? clamp(params.graphWeight, 0, 0.6)
      : base.graphWeight;
  return {
    ...base,
    decayDays,
    maxEvents,
    graphWeight,
  };
}

function normalizeRatios(ratios: StrategyRatios): StrategyRatios {
  const repair = clamp(Number(ratios.repair || 0), 0, 1);
  const optimize = clamp(Number(ratios.optimize || 0), 0, 1);
  const innovate = clamp(Number(ratios.innovate || 0), 0, 1);
  const total = repair + optimize + innovate;
  if (total <= 0) {
    return { repair: 0.2, optimize: 0.3, innovate: 0.5 };
  }
  return {
    repair: repair / total,
    optimize: optimize / total,
    innovate: innovate / total,
  };
}

function ratiosFromStrategy(strategy: EvolutionStrategy): StrategyRatios {
  if (strategy === "repair-only") {
    return { repair: 0.8, optimize: 0.2, innovate: 0 };
  }
  if (strategy === "harden") {
    return { repair: 0.4, optimize: 0.4, innovate: 0.2 };
  }
  return { repair: 0.2, optimize: 0.3, innovate: 0.5 };
}

function buildDynamicRatios(params: {
  failureRate: number;
  unknownRate: number;
}): StrategyRatios {
  const failureRate = clamp(params.failureRate, 0, 1);
  const unknownRate = clamp(params.unknownRate, 0, 1);
  const repair = clamp(0.15 + failureRate * 0.92 + unknownRate * 0.28, 0.1, 0.88);
  const innovate = clamp(0.62 - failureRate * 0.96 - unknownRate * 0.2, 0, 0.72);
  const optimize = clamp(1 - repair - innovate, 0.08, 0.58);
  return normalizeRatios({ repair, optimize, innovate });
}

function strategyFromRatios(ratios: StrategyRatios): EvolutionStrategy {
  const normalized = normalizeRatios(ratios);
  if (normalized.repair >= 0.62) {
    return "repair-only";
  }
  if (normalized.repair >= 0.36) {
    return "harden";
  }
  return "balanced";
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
  graphWeight?: number;
  antiPatternPenalties?: Record<string, number>;
  antiPatternWeight?: number;
}): ExperienceCard[] {
  const { cards, stats, query, topK, graphBoosts, graphWeight, antiPatternPenalties, antiPatternWeight } = params;
  const normalizedGraphWeight =
    typeof graphWeight === "number" ? clamp(graphWeight, 0, 0.6) : 0.25;
  const normalizedAntiPatternWeight =
    typeof antiPatternWeight === "number" ? clamp(antiPatternWeight, 0, 0.7) : 0.36;
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
      const antiPenalty = clamp(Number(antiPatternPenalties?.[card.id] || 0), 0, 1);
      const score =
        relevance * 0.5 +
        confidence * 0.2 +
        recency * 0.1 +
        quality * 0.2 +
        lifecycleBias(lifecycle) +
        memoryTierBias(tier) +
        graphBoost * normalizedGraphWeight +
        antiPenalty * -normalizedAntiPatternWeight +
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

function recencyWeightByTs(ts: string, nowMs: number, decayDays: number): number {
  const tsMs = Number(new Date(ts).getTime());
  if (!Number.isFinite(tsMs) || tsMs <= 0) {
    return 0.35;
  }
  const ageDays = Math.max(0, (nowMs - tsMs) / (1000 * 3600 * 24));
  return Math.exp(-ageDays / Math.max(1, decayDays));
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
  strategy?: string;
  decayDays?: number;
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

  const policy = resolveLinkGraphStrategyPolicy({
    strategy: params.strategy,
    decayDays: params.decayDays,
    maxEvents: params.maxEvents,
  });
  const start = Math.max(0, rows.length - policy.maxEvents);
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
    const weight = recencyWeightByTs(event.ts, nowMs, policy.decayDays);
    let base = 0;
    if (event.type === "attempt") {
      base = sameAgent ? policy.attemptSameAgent : policy.attemptCrossAgent;
    } else if (event.outcome === "success") {
      base = sameAgent ? policy.successSameAgent : policy.successCrossAgent;
    } else if (event.outcome === "failure") {
      base = sameAgent ? policy.failureSameAgent : policy.failureCrossAgent;
    } else {
      base = sameAgent ? policy.unknownSameAgent : policy.unknownCrossAgent;
    }

    const delta = clamp(base * weight, -policy.eventContributionCap, policy.eventContributionCap);
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

function defaultReflectionState(): ReflectionState {
  const strategy: EvolutionStrategy = "balanced";
  const ratios = ratiosFromStrategy(strategy);
  return {
    recallCount: 0,
    lastComputedRound: 0,
    lastComputedAt: "",
    strategy,
    ratios,
    windowDays: 7,
    consideredOutcomes: 0,
    successCount: 0,
    failureCount: 0,
    unknownCount: 0,
    successRate: 0,
    failureRate: 0,
    unknownRate: 0,
    reason: "initial-default",
  };
}

function normalizeReflectionState(raw: unknown): ReflectionState {
  if (!raw || typeof raw !== "object") {
    return defaultReflectionState();
  }
  const item = raw as Record<string, unknown>;
  const strategy = normalizeEvolutionStrategy(String(item.strategy || "balanced"), "balanced");
  const ratios = normalizeRatios(
    item.ratios && typeof item.ratios === "object"
      ? {
          repair: Number((item.ratios as Record<string, unknown>).repair || 0),
          optimize: Number((item.ratios as Record<string, unknown>).optimize || 0),
          innovate: Number((item.ratios as Record<string, unknown>).innovate || 0),
        }
      : ratiosFromStrategy(strategy),
  );
  return {
    recallCount: Math.max(0, Number(item.recallCount || 0)),
    lastComputedRound: Math.max(0, Number(item.lastComputedRound || 0)),
    lastComputedAt: String(item.lastComputedAt || ""),
    strategy,
    ratios,
    windowDays: Math.max(1, Number(item.windowDays || 7)),
    consideredOutcomes: Math.max(0, Number(item.consideredOutcomes || 0)),
    successCount: Math.max(0, Number(item.successCount || 0)),
    failureCount: Math.max(0, Number(item.failureCount || 0)),
    unknownCount: Math.max(0, Number(item.unknownCount || 0)),
    successRate: clamp(Number(item.successRate || 0), 0, 1),
    failureRate: clamp(Number(item.failureRate || 0), 0, 1),
    unknownRate: clamp(Number(item.unknownRate || 0), 0, 1),
    reason: String(item.reason || "state-loaded"),
  };
}

async function readReflectionState(workspaceDir: string): Promise<ReflectionState> {
  const filePath = path.join(workspaceDir, REFLECTION_STATE_REL);
  if (!(await existsFile(filePath))) {
    return defaultReflectionState();
  }
  try {
    const raw = await readFile(filePath, "utf8");
    return normalizeReflectionState(JSON.parse(raw));
  } catch {
    return defaultReflectionState();
  }
}

async function saveReflectionState(workspaceDir: string, state: ReflectionState): Promise<void> {
  const filePath = path.join(workspaceDir, REFLECTION_STATE_REL);
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, JSON.stringify(state, null, 2), "utf8");
}

async function readRecentOutcomeEvents(params: {
  workspaceDir: string;
  maxEvents: number;
  windowDays: number;
}): Promise<LinkGraphEvent[]> {
  const filePath = path.join(params.workspaceDir, LINKGRAPH_EVENTS_REL);
  if (!(await existsFile(filePath))) {
    return [];
  }
  const raw = await readFile(filePath, "utf8");
  const rows = raw.split("\n").filter(Boolean);
  if (rows.length === 0) {
    return [];
  }
  const start = Math.max(0, rows.length - Math.max(1, params.maxEvents));
  const nowMs = Date.now();
  const out: LinkGraphEvent[] = [];

  for (let idx = start; idx < rows.length; idx += 1) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(rows[idx]);
    } catch {
      continue;
    }
    const event = normalizeLinkGraphEvent(parsed);
    if (!event || event.type !== "outcome") {
      continue;
    }
    const tsMs = Number(new Date(event.ts).getTime());
    if (!Number.isFinite(tsMs) || tsMs <= 0) {
      continue;
    }
    const ageDays = (nowMs - tsMs) / (1000 * 3600 * 24);
    if (ageDays > Math.max(1, params.windowDays)) {
      continue;
    }
    out.push(event);
  }
  return out;
}

export async function resolveAdaptiveGraphStrategy(params: {
  workspaceDir: string;
  requestedStrategy?: string;
  reflectionEnabled?: boolean;
  roundInterval?: number;
  windowDays?: number;
  minOutcomes?: number;
  maxEvents?: number;
}): Promise<{
  strategy: EvolutionStrategy;
  ratios: StrategyRatios;
  mode: "fixed" | "auto";
  reflection: ReflectionState;
}> {
  const requested = String(params.requestedStrategy || "")
    .trim()
    .toLowerCase()
    .replace(/_/g, "-");
  if (requested === "balanced" || requested === "harden" || requested === "repair-only") {
    const strategy = normalizeEvolutionStrategy(requested, "balanced");
    const reflection = normalizeReflectionState({
      ...defaultReflectionState(),
      strategy,
      ratios: ratiosFromStrategy(strategy),
      reason: "fixed-strategy",
    });
    return {
      strategy,
      ratios: reflection.ratios,
      mode: "fixed",
      reflection,
    };
  }

  const reflectionEnabled =
    params.reflectionEnabled === undefined ? true : Boolean(params.reflectionEnabled);
  if (!reflectionEnabled && requested !== "auto") {
    const strategy = normalizeEvolutionStrategy(requested, "balanced");
    const reflection = normalizeReflectionState({
      ...defaultReflectionState(),
      strategy,
      ratios: ratiosFromStrategy(strategy),
      reason: "reflection-disabled",
    });
    return {
      strategy,
      ratios: reflection.ratios,
      mode: "fixed",
      reflection,
    };
  }

  const interval = Math.round(clamp(Number(params.roundInterval || 8), 1, 200));
  const windowDays = Math.round(clamp(Number(params.windowDays || 7), 1, 90));
  const minOutcomes = Math.round(clamp(Number(params.minOutcomes || 6), 1, 200));
  const maxEvents = Math.round(clamp(Number(params.maxEvents || 2000), 200, 20000));
  const state = await readReflectionState(params.workspaceDir);
  state.recallCount += 1;

  const shouldCompute =
    state.lastComputedRound <= 0 || state.recallCount - state.lastComputedRound >= interval;
  if (shouldCompute) {
    const outcomes = await readRecentOutcomeEvents({
      workspaceDir: params.workspaceDir,
      maxEvents,
      windowDays,
    });
    let successCount = 0;
    let failureCount = 0;
    let unknownCount = 0;
    for (const event of outcomes) {
      if (event.outcome === "success") {
        successCount += 1;
      } else if (event.outcome === "failure") {
        failureCount += 1;
      } else {
        unknownCount += 1;
      }
    }

    const consideredOutcomes = successCount + failureCount;
    const totalOutcomes = consideredOutcomes + unknownCount;
    const successRate = consideredOutcomes > 0 ? successCount / consideredOutcomes : 0;
    const failureRate = consideredOutcomes > 0 ? failureCount / consideredOutcomes : 0;
    const unknownRate = totalOutcomes > 0 ? unknownCount / totalOutcomes : 0;

    let ratios = state.ratios;
    let strategy = state.strategy;
    let reason = "insufficient-outcomes-hold";
    if (consideredOutcomes >= minOutcomes) {
      ratios = buildDynamicRatios({ failureRate, unknownRate });
      strategy = strategyFromRatios(ratios);
      reason = "computed-from-recent-outcomes";
    } else if (state.lastComputedRound <= 0) {
      strategy = "balanced";
      ratios = ratiosFromStrategy(strategy);
      reason = "fallback-balanced-first-cycle";
    }

    state.lastComputedRound = state.recallCount;
    state.lastComputedAt = nowIso();
    state.strategy = strategy;
    state.ratios = normalizeRatios(ratios);
    state.windowDays = windowDays;
    state.consideredOutcomes = consideredOutcomes;
    state.successCount = successCount;
    state.failureCount = failureCount;
    state.unknownCount = unknownCount;
    state.successRate = successRate;
    state.failureRate = failureRate;
    state.unknownRate = unknownRate;
    state.reason = reason;
  }

  await saveReflectionState(params.workspaceDir, state);
  return {
    strategy: state.strategy,
    ratios: state.ratios,
    mode: "auto",
    reflection: state,
  };
}

function defaultAntiPatternLibrary(): AntiPatternLibrary {
  return {
    updatedAt: nowIso(),
    entries: {},
  };
}

function normalizeAntiPatternLibrary(raw: unknown): AntiPatternLibrary {
  if (!raw || typeof raw !== "object") {
    return defaultAntiPatternLibrary();
  }
  const item = raw as Record<string, unknown>;
  const entriesRaw =
    item.entries && typeof item.entries === "object"
      ? (item.entries as Record<string, unknown>)
      : {};
  const entries: Record<string, AntiPatternEntry> = {};

  for (const [queryKey, value] of Object.entries(entriesRaw)) {
    if (!value || typeof value !== "object") {
      continue;
    }
    const row = value as Record<string, unknown>;
    const cardsRaw =
      row.cards && typeof row.cards === "object" ? (row.cards as Record<string, unknown>) : {};
    const cards: Record<string, AntiPatternCard> = {};
    for (const [cardId, cardRaw] of Object.entries(cardsRaw)) {
      if (!cardRaw || typeof cardRaw !== "object") {
        continue;
      }
      const card = cardRaw as Record<string, unknown>;
      cards[cardId] = {
        failureCount: Math.max(0, Number(card.failureCount || 0)),
        lastFailureAt: typeof card.lastFailureAt === "string" ? card.lastFailureAt : undefined,
        agents: Array.isArray(card.agents)
          ? dedupeStringArray(card.agents.map((x) => String(x || ""))).slice(0, 12)
          : [],
      };
    }
    entries[queryKey] = {
      queryKey,
      querySamples: Array.isArray(row.querySamples)
        ? dedupeStringArray(row.querySamples.map((x) => shortText(String(x || ""), 180))).slice(0, 6)
        : [],
      failureCount: Math.max(0, Number(row.failureCount || 0)),
      successCount: Math.max(0, Number(row.successCount || 0)),
      lastOutcomeAt: typeof row.lastOutcomeAt === "string" ? row.lastOutcomeAt : undefined,
      lastFailureAt: typeof row.lastFailureAt === "string" ? row.lastFailureAt : undefined,
      cards,
    };
  }

  return {
    updatedAt: typeof item.updatedAt === "string" ? item.updatedAt : nowIso(),
    entries,
  };
}

async function readAntiPatternLibrary(workspaceDir: string): Promise<AntiPatternLibrary> {
  const filePath = path.join(workspaceDir, ANTI_PATTERNS_REL);
  if (!(await existsFile(filePath))) {
    return defaultAntiPatternLibrary();
  }
  try {
    const raw = await readFile(filePath, "utf8");
    return normalizeAntiPatternLibrary(JSON.parse(raw));
  } catch {
    return defaultAntiPatternLibrary();
  }
}

async function saveAntiPatternLibrary(
  workspaceDir: string,
  library: AntiPatternLibrary,
): Promise<void> {
  const filePath = path.join(workspaceDir, ANTI_PATTERNS_REL);
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, JSON.stringify(library, null, 2), "utf8");
}

export async function updateAntiPatternLibrary(params: {
  workspaceDir: string;
  queryKey: string;
  query: string;
  cardIds: string[];
  agentId?: string;
  outcome: "success" | "failure" | "unknown";
  ts?: string;
}): Promise<void> {
  const queryKey = String(params.queryKey || "").trim();
  const cardIds = dedupeStringArray(params.cardIds || []);
  if (!queryKey || cardIds.length === 0) {
    return;
  }
  const library = await readAntiPatternLibrary(params.workspaceDir);
  const ts = String(params.ts || "").trim() || nowIso();
  const agentId = String(params.agentId || "").trim();
  const query = shortText(params.query || "", 240);
  const entry =
    library.entries[queryKey] ||
    ({
      queryKey,
      querySamples: [],
      failureCount: 0,
      successCount: 0,
      cards: {},
    } as AntiPatternEntry);

  if (query) {
    entry.querySamples = dedupeStringArray([query, ...entry.querySamples]).slice(0, 6);
  }
  entry.lastOutcomeAt = ts;

  if (params.outcome === "failure") {
    entry.failureCount += 1;
    entry.lastFailureAt = ts;
    for (const cardId of cardIds) {
      const card = entry.cards[cardId] || { failureCount: 0, agents: [] };
      card.failureCount = Math.max(0, Number(card.failureCount || 0)) + 1;
      card.lastFailureAt = ts;
      if (agentId) {
        card.agents = dedupeStringArray([agentId, ...(card.agents || [])]).slice(0, 12);
      }
      entry.cards[cardId] = card;
    }
  } else if (params.outcome === "success") {
    entry.successCount += 1;
    for (const cardId of cardIds) {
      if (!entry.cards[cardId]) {
        continue;
      }
      entry.cards[cardId].failureCount = Math.max(
        0,
        Number(entry.cards[cardId].failureCount || 0) - 1,
      );
    }
  }

  library.entries[queryKey] = entry;
  library.updatedAt = ts;
  await saveAntiPatternLibrary(params.workspaceDir, library);
}

export async function readAntiPatternPenalties(params: {
  workspaceDir: string;
  queryKey: string;
  agentId?: string;
  maxPenalty?: number;
}): Promise<Record<string, number>> {
  const queryKey = String(params.queryKey || "").trim();
  if (!queryKey) {
    return {};
  }
  const library = await readAntiPatternLibrary(params.workspaceDir);
  const entry = library.entries[queryKey];
  if (!entry) {
    return {};
  }
  const maxPenalty =
    typeof params.maxPenalty === "number" ? clamp(params.maxPenalty, 0.1, 1) : 0.85;
  const nowMs = Date.now();
  const agentId = String(params.agentId || "").trim();
  const out: Record<string, number> = {};

  for (const [cardId, card] of Object.entries(entry.cards || {})) {
    const failCount = Math.max(0, Number(card.failureCount || 0));
    if (failCount <= 0) {
      continue;
    }
    const severity = clamp(Math.log1p(failCount) / Math.log1p(8), 0, 1);
    const recentWeight = recencyWeightByTs(card.lastFailureAt || entry.lastFailureAt || "", nowMs, 21);
    const sameAgent =
      agentId && Array.isArray(card.agents) ? card.agents.includes(agentId) : false;
    const boosted = severity * (0.55 + recentWeight * 0.45) + (sameAgent ? 0.08 : 0);
    out[cardId] = clamp(boosted, 0, maxPenalty);
  }

  return out;
}

export async function writeRecallDoc(params: {
  workspaceDir: string;
  cards: ExperienceCard[];
  stats: StatsFile;
  query: string;
  strategy?: EvolutionStrategy;
  strategyMode?: "fixed" | "auto";
  strategyRatios?: StrategyRatios;
  reflection?: ReflectionState;
  antiPatternPenalties?: Record<string, number>;
}): Promise<{ path: string; content: string }> {
  const { workspaceDir, cards, stats, query } = params;
  const lines: string[] = [];
  lines.push("# Experience Recall (Auto)");
  lines.push("");
  lines.push(`Generated at: ${nowIso()}`);
  lines.push(`Query hint: ${shortText(query || "none", 260)}`);
  if (params.strategy) {
    lines.push(`Graph strategy: ${params.strategy} (${params.strategyMode || "fixed"})`);
  }
  if (params.strategyRatios) {
    const ratios = normalizeRatios(params.strategyRatios);
    lines.push(
      `Reflection ratios (repair/optimize/innovate): ${(ratios.repair * 100).toFixed(0)}%/${(ratios.optimize * 100).toFixed(0)}%/${(ratios.innovate * 100).toFixed(0)}%`,
    );
  }
  if (params.reflection && params.strategyMode === "auto") {
    lines.push(
      `Reflection window: ${params.reflection.windowDays}d, considered outcomes: ${params.reflection.consideredOutcomes}, failure rate: ${(params.reflection.failureRate * 100).toFixed(1)}%`,
    );
  }
  lines.push("");
  lines.push("Usage policy:");
  lines.push("1. Reuse only when pattern matches.");
  lines.push("2. Run minimum verification before broad changes.");
  lines.push("3. Prefer current repo state if conflicts appear.");
  lines.push("4. Avoid anti-pattern cards with high failure risk unless verified.");
  lines.push("");
  if (cards.length === 0) {
    lines.push("No recall candidates.");
    lines.push("");
  } else {
    cards.forEach((card, idx) => {
      const conf = confidenceOf(stats.cards[card.id]).toFixed(2);
      const antiPenalty = clamp(Number(params.antiPatternPenalties?.[card.id] || 0), 0, 1);
      lines.push(`## ${idx + 1}. ${card.title}`);
      lines.push(`- ID: ${card.id}`);
      lines.push(`- Confidence: ${conf}`);
      lines.push(`- Tier: ${normalizeMemoryTier(card.memoryTier)}`);
      if (typeof card.priorityScore === "number") {
        lines.push(`- Priority score: ${card.priorityScore.toFixed(4)}`);
      }
      if (antiPenalty > 0) {
        lines.push(`- Anti-pattern risk: ${(antiPenalty * 100).toFixed(0)}%`);
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
