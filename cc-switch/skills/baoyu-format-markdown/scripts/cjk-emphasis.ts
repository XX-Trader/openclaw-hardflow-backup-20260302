const CJK_PUNCT_COMMON = "。．，、？！：；";
const CJK_OPENING_PUNCT = "（〔〖〘〚「『〈《【\u201C\u2018";
const CJK_CLOSING_PUNCT = "）〕〗〙〛」』〉》】\u201D\u2019" + CJK_PUNCT_COMMON;
const CJK_SCRIPTS =
  "\\p{Script=Han}\\p{Script=Hiragana}\\p{Script=Katakana}\\p{Script=Hangul}";

export const CJK_CLOSING_PUNCT_RE = new RegExp(`[${CJK_CLOSING_PUNCT}]`);
export const CJK_OPENING_PUNCT_RE = new RegExp(`^[${CJK_OPENING_PUNCT}]`);
export const CJK_CHAR_RE = new RegExp(`[${CJK_SCRIPTS}]`, "u");

const PUNCT_OR_SYMBOL_RE = /[\p{P}\p{S}]/u;
const WORD_CHAR_RE = /[\p{L}\p{N}]/u;

const CJK_PUNCT_PAIRS: Record<string, string> = {
  "“": "”",
  "‘": "’",
  "（": "）",
  "〔": "〕",
  "〖": "〗",
  "〘": "〙",
  "〚": "〛",
  "「": "」",
  "『": "』",
  "〈": "〉",
  "《": "》",
  "【": "】",
};

function findInlineCodeRanges(text: string): Array<[number, number]> {
  const ranges: Array<[number, number]> = [];
  let i = 0;
  while (i < text.length) {
    if (text[i] !== "`") {
      i += 1;
      continue;
    }

    let run = 1;
    while (i + run < text.length && text[i + run] === "`") {
      run += 1;
    }

    const start = i;
    let j = i + run;
    let found = false;
    while (j < text.length) {
      if (text[j] !== "`") {
        j += 1;
        continue;
      }
      let closeRun = 1;
      while (j + closeRun < text.length && text[j + closeRun] === "`") {
        closeRun += 1;
      }
      if (closeRun === run) {
        ranges.push([start, j + closeRun - 1]);
        i = j + closeRun;
        found = true;
        break;
      }
      j += closeRun;
    }

    if (!found) {
      i = start + run;
    }
  }
  return ranges;
}

function isEscaped(text: string, pos: number): boolean {
  let count = 0;
  for (let i = pos - 1; i >= 0 && text[i] === "\\"; i -= 1) {
    count += 1;
  }
  return count % 2 === 1;
}

function isWhitespaceChar(ch: string | undefined): boolean {
  return !ch || /\s/u.test(ch);
}

function isPunctuationOrSymbol(ch: string | undefined): boolean {
  return !!ch && PUNCT_OR_SYMBOL_RE.test(ch);
}

function isMatchingCjkPunct(open: string, close: string): boolean {
  return CJK_PUNCT_PAIRS[open] === close;
}

function mapNonCodeSegments(
  block: string,
  mapper: (segment: string) => string
): string {
  const codeRanges = findInlineCodeRanges(block);
  if (codeRanges.length === 0) {
    return mapper(block);
  }

  let result = "";
  let lastIndex = 0;
  for (const [start, end] of codeRanges) {
    if (start > lastIndex) {
      result += mapper(block.slice(lastIndex, start));
    }
    result += block.slice(start, end + 1);
    lastIndex = end + 1;
  }
  if (lastIndex < block.length) {
    result += mapper(block.slice(lastIndex));
  }
  return result;
}

function moveCjkPunctuationOutsideEmphasis(block: string): string {
  return mapNonCodeSegments(block, (segment) => {
    const delimiterPositions: number[] = [];
    let cursor = 0;
    while (cursor < segment.length - 1) {
      if (
        segment[cursor] === "*" &&
        segment[cursor + 1] === "*" &&
        segment[cursor - 1] !== "*" &&
        segment[cursor + 2] !== "*" &&
        !isEscaped(segment, cursor)
      ) {
        delimiterPositions.push(cursor);
        cursor += 2;
        continue;
      }
      cursor += 1;
    }

    if (delimiterPositions.length < 2) return segment;

    const stack: number[] = [];
    const pairs: Array<{ open: number; close: number }> = [];
    for (const pos of delimiterPositions) {
      if (stack.length === 0) {
        stack.push(pos);
      } else {
        const open = stack.pop() as number;
        pairs.push({ open, close: pos });
      }
    }

    const skip = new Set<number>();
    const insertBefore = new Map<number, string>();

    for (const pair of pairs) {
      const openPunctPos = pair.open + 2;
      const closePunctPos = pair.close - 1;
      if (openPunctPos >= closePunctPos) continue;

      const openPunct = segment[openPunctPos];
      const closePunct = segment[closePunctPos];
      if (!openPunct || !closePunct) continue;
      if (!CJK_OPENING_PUNCT_RE.test(openPunct)) continue;
      if (!CJK_CLOSING_PUNCT_RE.test(closePunct)) continue;
      if (!isMatchingCjkPunct(openPunct, closePunct)) continue;
      if (openPunctPos + 1 >= closePunctPos) continue;

      const inner = segment.slice(openPunctPos + 1, closePunctPos);
      if (inner.length === 0) continue;

      skip.add(openPunctPos);
      skip.add(closePunctPos);

      insertBefore.set(pair.open, (insertBefore.get(pair.open) ?? "") + openPunct);
      const afterClose = pair.close + 2;
      insertBefore.set(
        afterClose,
        (insertBefore.get(afterClose) ?? "") + closePunct
      );
    }

    if (skip.size === 0) return segment;

    let result = "";
    for (let idx = 0; idx < segment.length; idx += 1) {
      const insert = insertBefore.get(idx);
      if (insert) {
        result += insert;
      }
      if (skip.has(idx)) {
        continue;
      }
      result += segment[idx];
    }
    const tailInsert = insertBefore.get(segment.length);
    if (tailInsert) {
      result += tailInsert;
    }
    return result;
  });
}

function fixCjkEmphasisSpacingInBlock(block: string): string {
  const normalized = moveCjkPunctuationOutsideEmphasis(block);
  const codeRanges = findInlineCodeRanges(normalized);
  let rangeIndex = 0;

  const delimiters: Array<{
    pos: number;
    canOpen: boolean;
    canClose: boolean;
  }> = [];
  let cursor = 0;
  while (cursor < normalized.length - 1) {
    if (rangeIndex < codeRanges.length && cursor >= codeRanges[rangeIndex][0]) {
      if (cursor <= codeRanges[rangeIndex][1]) {
        cursor = codeRanges[rangeIndex][1] + 1;
        continue;
      }
      rangeIndex += 1;
      continue;
    }

    if (
      normalized[cursor] === "*" &&
      normalized[cursor + 1] === "*" &&
      normalized[cursor - 1] !== "*" &&
      normalized[cursor + 2] !== "*" &&
      !isEscaped(normalized, cursor)
    ) {
      const before = normalized[cursor - 1];
      const after = normalized[cursor + 2];
      const beforeIsSpace = isWhitespaceChar(before);
      const afterIsSpace = isWhitespaceChar(after);
      const beforeIsPunct = isPunctuationOrSymbol(before);
      const afterIsPunct = isPunctuationOrSymbol(after);
      const leftFlanking =
        !afterIsSpace && (!afterIsPunct || beforeIsSpace || beforeIsPunct);
      const rightFlanking =
        !beforeIsSpace && (!beforeIsPunct || afterIsSpace || afterIsPunct);
      const cjkPunctBefore = !!before && CJK_CLOSING_PUNCT_RE.test(before);
      const wordAfter = !!after && WORD_CHAR_RE.test(after);

      delimiters.push({
        pos: cursor,
        canOpen: leftFlanking,
        canClose: rightFlanking || (cjkPunctBefore && wordAfter),
      });
      cursor += 2;
      continue;
    }

    cursor += 1;
  }

  const stack: Array<{ pos: number }> = [];
  const pairs: Array<{ open: number; close: number }> = [];
  for (const delimiter of delimiters) {
    if (delimiter.canClose) {
      let openerIndex = -1;
      for (let j = stack.length - 1; j >= 0; j -= 1) {
        openerIndex = j;
        break;
      }
      if (openerIndex !== -1) {
        const opener = stack.splice(openerIndex, 1)[0];
        pairs.push({ open: opener.pos, close: delimiter.pos });
      }
    }
    if (delimiter.canOpen) {
      stack.push({ pos: delimiter.pos });
    }
  }

  if (pairs.length === 0) return normalized;

  const insertPositions = new Set<number>();
  for (const pair of pairs) {
    const insideLast = normalized[pair.close - 1];
    const afterClose = normalized[pair.close + 2];
    if (!afterClose) continue;
    if (
      CJK_CLOSING_PUNCT_RE.test(insideLast) &&
      WORD_CHAR_RE.test(afterClose)
    ) {
      insertPositions.add(pair.close + 2);
    }
  }

  if (insertPositions.size === 0) return normalized;

  let result = "";
  for (let idx = 0; idx < normalized.length; idx += 1) {
    if (insertPositions.has(idx)) {
      result += " ";
    }
    result += normalized[idx];
  }
  if (insertPositions.has(normalized.length)) {
    result += " ";
  }
  return result;
}

export function fixCjkEmphasisSpacing(content: string): string {
  const parts = content.split(/(^```[\s\S]*?^```|^~~~[\s\S]*?^~~~)/m);
  return parts
    .map((part, i) => {
      if (i % 2 === 1) return part;
      const blocks = part.split(/(\n\s*\n+)/);
      return blocks
        .map((block, index) => {
          if (index % 2 === 1) return block;
          return fixCjkEmphasisSpacingInBlock(block);
        })
        .join("");
    })
    .join("");
}
