import type { CaptureMode } from "./client.js";

export const MEMORY_TRIGGERS = [
  /remember|preference|prefer|important|decision|decided|always|never/i,
  /\u8bb0\u4f4f|\u504f\u597d|\u559c\u6b22|\u559c\u7231|\u5d07\u62dc|\u8ba8\u538c|\u5bb3\u6015|\u91cd\u8981|\u51b3\u5b9a|\u603b\u662f|\u6c38\u8fdc|\u4f18\u5148|\u4e60\u60ef|\u7231\u597d|\u64c5\u957f|\u6700\u7231|\u4e0d\u559c\u6b22/i,
  /[\w.-]+@[\w.-]+\.\w+/,
  /\+\d{10,}/,
  /(?:\u6211|my)\s*(?:\u662f|\u53eb|\u540d\u5b57|name|\u4f4f\u5728|live|\u6765\u81ea|from|\u751f\u65e5|birthday|\u7535\u8bdd|phone|\u90ae\u7bb1|email)/i,
  /(?:\u6211|i)\s*(?:\u559c\u6b22|\u5d07\u62dc|\u8ba8\u538c|\u5bb3\u6015|\u64c5\u957f|\u4e0d\u4f1a|\u7231|\u6068|\u60f3\u8981|\u9700\u8981|\u5e0c\u671b|\u89c9\u5f97|\u8ba4\u4e3a|\u76f8\u4fe1)/i,
  /(?:favorite|favourite|love|hate|enjoy|dislike|admire|idol|fan of)/i,
];

const CJK_CHAR_REGEX = /[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]/;
const RELEVANT_MEMORIES_BLOCK_RE = /<relevant-memories>[\s\S]*?<\/relevant-memories>/gi;
const INGEST_REPLY_ASSIST_BLOCK_RE = /<ingest-reply-assist>[\s\S]*?<\/ingest-reply-assist>/gi;
const CONVERSATION_METADATA_BLOCK_RE =
  /(?:^|\n)\s*(?:Conversation info|Conversation metadata|\u4f1a\u8bdd\u4fe1\u606f|\u5bf9\u8bdd\u4fe1\u606f)\s*(?:\([^)]+\))?\s*:\s*```[\s\S]*?```/gi;
/** Strips "Sender (untrusted metadata): ```json ... ```" so capture sends clean text to OpenViking extract. */
const SENDER_METADATA_BLOCK_RE = /Sender\s*\([^)]*\)\s*:\s*```[\s\S]*?```/gi;
const FENCED_JSON_BLOCK_RE = /```json\s*([\s\S]*?)```/gi;
const METADATA_JSON_KEY_RE =
  /"(session|sessionid|sessionkey|conversationid|channel|sender|userid|agentid|timestamp|timezone)"\s*:/gi;
const LEADING_TIMESTAMP_PREFIX_RE = /^\s*\[[^\]\n]{1,120}\]\s*/;
const COMMAND_TEXT_RE = /^\/[a-z0-9_-]{1,64}\b/i;
const NON_CONTENT_TEXT_RE = /^[\p{P}\p{S}\s]+$/u;
const SUBAGENT_CONTEXT_RE = /^\s*\[Subagent Context\]/i;
const MEMORY_INTENT_RE = /\u8bb0\u4f4f|\u8bb0\u4e0b|remember|save|store|\u504f\u597d|preference|\u89c4\u5219|rule|\u4e8b\u5b9e|fact/i;
const AUTOMATION_PROMPT_HEADER_RE = /\[(?:cron|job|task|workflow):[^\]\n]+\]/i;
const EXEC_TOOL_INSTRUCTION_RE = /\bYour first assistant turn MUST contain exactly one exec tool call\b/i;
const AUTO_DELIVERY_INSTRUCTION_RE = /\bReturn your summary as plain text; it will be delivered automatically\b/i;
const CURRENT_TIME_INSTRUCTION_RE = /\bCurrent time:\s/i;
const QUESTION_CUE_RE =
  /[?\uff1f]|\b(?:what|when|where|who|why|how|which|can|could|would|did|does|is|are)\b|^(?:\u8bf7\u95ee|\u80fd\u5426|\u53ef\u5426|\u600e\u4e48|\u5982\u4f55|\u4ec0\u4e48\u65f6\u5019|\u8c01|\u4ec0\u4e48|\u54ea|\u662f\u5426)/i;
const SPEAKER_TAG_RE = /(?:^|\s)([A-Za-z\u4e00-\u9fa5][A-Za-z0-9_\u4e00-\u9fa5-]{1,30}):\s/g;

export const CAPTURE_LIMIT = 3;

function resolveCaptureMinLength(text: string): number {
  return CJK_CHAR_REGEX.test(text) ? 4 : 10;
}

function looksLikeMetadataJsonBlock(content: string): boolean {
  const matchedKeys = new Set<string>();
  const matches = content.matchAll(METADATA_JSON_KEY_RE);
  for (const match of matches) {
    const key = (match[1] ?? "").toLowerCase();
    if (key) {
      matchedKeys.add(key);
    }
  }
  return matchedKeys.size >= 3;
}

export function sanitizeUserTextForCapture(text: string): string {
  return text
    .replace(RELEVANT_MEMORIES_BLOCK_RE, " ")
    .replace(INGEST_REPLY_ASSIST_BLOCK_RE, " ")
    .replace(CONVERSATION_METADATA_BLOCK_RE, " ")
    .replace(SENDER_METADATA_BLOCK_RE, " ")
    .replace(FENCED_JSON_BLOCK_RE, (full, inner) =>
      looksLikeMetadataJsonBlock(String(inner ?? "")) ? " " : full,
    )
    .replace(LEADING_TIMESTAMP_PREFIX_RE, "")
    .replace(/\u0000/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function looksLikeQuestionOnlyText(text: string): boolean {
  if (!QUESTION_CUE_RE.test(text) || MEMORY_INTENT_RE.test(text)) {
    return false;
  }
  // Multi-speaker transcripts often contain many "?" but should still be captured.
  const speakerTags = text.match(/[A-Za-z\u4e00-\u9fa5]{2,20}:\s/g) ?? [];
  if (speakerTags.length >= 2 || text.length > 280) {
    return false;
  }
  return true;
}

export type TranscriptLikeIngestDecision = {
  shouldAssist: boolean;
  reason: string;
  normalizedText: string;
  speakerTurns: number;
  chars: number;
};

function countSpeakerTurns(text: string): number {
  let count = 0;
  for (const _match of text.matchAll(SPEAKER_TAG_RE)) {
    count += 1;
  }
  return count;
}

function looksLikeAutomationPrompt(text: string): boolean {
  let signals = 0;
  if (AUTOMATION_PROMPT_HEADER_RE.test(text)) {
    signals += 1;
  }
  if (EXEC_TOOL_INSTRUCTION_RE.test(text)) {
    signals += 1;
  }
  if (AUTO_DELIVERY_INSTRUCTION_RE.test(text)) {
    signals += 1;
  }
  if (CURRENT_TIME_INSTRUCTION_RE.test(text)) {
    signals += 1;
  }
  return signals >= 2;
}

export function isTranscriptLikeIngest(
  text: string,
  options: {
    minSpeakerTurns: number;
    minChars: number;
  },
): TranscriptLikeIngestDecision {
  const normalizedText = sanitizeUserTextForCapture(text.trim());
  if (!normalizedText) {
    return {
      shouldAssist: false,
      reason: "empty_text",
      normalizedText,
      speakerTurns: 0,
      chars: 0,
    };
  }

  if (COMMAND_TEXT_RE.test(normalizedText)) {
    return {
      shouldAssist: false,
      reason: "command_text",
      normalizedText,
      speakerTurns: 0,
      chars: normalizedText.length,
    };
  }

  if (SUBAGENT_CONTEXT_RE.test(normalizedText)) {
    return {
      shouldAssist: false,
      reason: "subagent_context",
      normalizedText,
      speakerTurns: 0,
      chars: normalizedText.length,
    };
  }

  if (NON_CONTENT_TEXT_RE.test(normalizedText)) {
    return {
      shouldAssist: false,
      reason: "non_content_text",
      normalizedText,
      speakerTurns: 0,
      chars: normalizedText.length,
    };
  }

  if (looksLikeQuestionOnlyText(normalizedText)) {
    return {
      shouldAssist: false,
      reason: "question_text",
      normalizedText,
      speakerTurns: 0,
      chars: normalizedText.length,
    };
  }

  if (looksLikeAutomationPrompt(normalizedText)) {
    return {
      shouldAssist: false,
      reason: "automation_prompt",
      normalizedText,
      speakerTurns: 0,
      chars: normalizedText.length,
    };
  }

  const chars = normalizedText.length;
  if (chars < options.minChars) {
    return {
      shouldAssist: false,
      reason: "chars_below_threshold",
      normalizedText,
      speakerTurns: 0,
      chars,
    };
  }

  const speakerTurns = countSpeakerTurns(normalizedText);
  if (speakerTurns < options.minSpeakerTurns) {
    return {
      shouldAssist: false,
      reason: "speaker_turns_below_threshold",
      normalizedText,
      speakerTurns,
      chars,
    };
  }

  return {
    shouldAssist: true,
    reason: "transcript_like_ingest",
    normalizedText,
    speakerTurns,
    chars,
  };
}

function normalizeDedupeText(text: string): string {
  return text.toLowerCase().replace(/\s+/g, " ").trim();
}

function normalizeCaptureDedupeText(text: string): string {
  return normalizeDedupeText(text).replace(/[\p{P}\p{S}]+/gu, " ").replace(/\s+/g, " ").trim();
}

export function pickRecentUniqueTexts(texts: string[], limit: number): string[] {
  if (limit <= 0 || texts.length === 0) {
    return [];
  }
  const seen = new Set<string>();
  const picked: string[] = [];
  for (let i = texts.length - 1; i >= 0; i -= 1) {
    const text = texts[i];
    const key = normalizeCaptureDedupeText(text);
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    picked.push(text);
    if (picked.length >= limit) {
      break;
    }
  }
  return picked.reverse();
}

export function getCaptureDecision(text: string, mode: CaptureMode, captureMaxLength: number): {
  shouldCapture: boolean;
  reason: string;
  normalizedText: string;
} {
  const trimmed = text.trim();
  const normalizedText = sanitizeUserTextForCapture(trimmed);
  const hadSanitization = normalizedText !== trimmed;
  if (!normalizedText) {
    return {
      shouldCapture: false,
      reason: /<relevant-memories>/i.test(trimmed) ? "injected_memory_context_only" : "empty_text",
      normalizedText: "",
    };
  }

  const compactText = normalizedText.replace(/\s+/g, "");
  const minLength = resolveCaptureMinLength(compactText);
  if (compactText.length < minLength || normalizedText.length > captureMaxLength) {
    return {
      shouldCapture: false,
      reason: "length_out_of_range",
      normalizedText,
    };
  }

  if (COMMAND_TEXT_RE.test(normalizedText)) {
    return {
      shouldCapture: false,
      reason: "command_text",
      normalizedText,
    };
  }

  if (NON_CONTENT_TEXT_RE.test(normalizedText)) {
    return {
      shouldCapture: false,
      reason: "non_content_text",
      normalizedText,
    };
  }
  if (SUBAGENT_CONTEXT_RE.test(normalizedText)) {
    return {
      shouldCapture: false,
      reason: "subagent_context",
      normalizedText,
    };
  }
  if (looksLikeQuestionOnlyText(normalizedText)) {
    return {
      shouldCapture: false,
      reason: "question_text",
      normalizedText,
    };
  }

  if (mode === "keyword") {
    for (const trigger of MEMORY_TRIGGERS) {
      if (trigger.test(normalizedText)) {
        return {
          shouldCapture: true,
          reason: hadSanitization
            ? `matched_trigger_after_sanitize:${trigger.toString()}`
            : `matched_trigger:${trigger.toString()}`,
          normalizedText,
        };
      }
    }
    return {
      shouldCapture: false,
      reason: hadSanitization ? "no_trigger_matched_after_sanitize" : "no_trigger_matched",
      normalizedText,
    };
  }

  return {
    shouldCapture: true,
    reason: hadSanitization ? "semantic_candidate_after_sanitize" : "semantic_candidate",
    normalizedText,
  };
}

export function extractTextsFromUserMessages(messages: unknown[]): string[] {
  const texts: string[] = [];
  for (const msg of messages) {
    if (!msg || typeof msg !== "object") {
      continue;
    }
    const msgObj = msg as Record<string, unknown>;
    if (msgObj.role !== "user") {
      continue;
    }
    const content = msgObj.content;
    if (typeof content === "string") {
      texts.push(content);
      continue;
    }
    if (Array.isArray(content)) {
      for (const block of content) {
        if (!block || typeof block !== "object") {
          continue;
        }
        const blockObj = block as Record<string, unknown>;
        if (blockObj.type === "text" && typeof blockObj.text === "string") {
          texts.push(blockObj.text);
        }
      }
    }
  }
  return texts;
}

/**
 * Extract new messages starting at startIndex (user + assistant) and return formatted text.
 */
export function extractNewTurnTexts(
  messages: unknown[],
  startIndex: number,
): { texts: string[]; newCount: number } {
  const texts: string[] = [];
  let count = 0;
  for (let i = startIndex; i < messages.length; i++) {
    const msg = messages[i] as Record<string, unknown>;
    if (!msg || typeof msg !== "object") continue;
    const role = msg.role as string;
    if (role !== "user" && role !== "assistant") continue;
    count++;
    const content = msg.content;
    if (typeof content === "string" && content.trim()) {
      texts.push(`[${role}]: ${content.trim()}`);
    } else if (Array.isArray(content)) {
      for (const block of content) {
        const b = block as Record<string, unknown>;
        if (b?.type === "text" && typeof b.text === "string") {
          texts.push(`[${role}]: ${(b.text as string).trim()}`);
        }
      }
    }
  }
  return { texts, newCount: count };
}

export function extractLatestUserText(messages: unknown[] | undefined): string {
  if (!messages || messages.length === 0) {
    return "";
  }
  const texts = extractTextsFromUserMessages(messages);
  for (let i = texts.length - 1; i >= 0; i -= 1) {
    const normalized = sanitizeUserTextForCapture(texts[i] ?? "");
    if (normalized) {
      return normalized;
    }
  }
  return "";
}
