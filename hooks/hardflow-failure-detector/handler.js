import path from "node:path";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";

/**
 * 解析工具执行结果中的错误信号。
 *
 * @param {any} event Hook 事件对象
 * @returns {{ isError: boolean, errorDetail: string }} 检测结果
 */
function detectFailure(event) {
  const toolResult = event?.tool_result ?? event?.result ?? "";
  const resultText = typeof toolResult === "object"
    ? JSON.stringify(toolResult)
    : String(toolResult);

  const exitCode = event?.tool_result?.exit_code
    ?? event?.tool_result?.exitCode
    ?? event?.exit_code
    ?? 0;

  const errorPatterns = [
    /error/i,
    /exit code [1-9]/i,
    /command not found/i,
    /no such file/i,
    /permission denied/i,
    /\bFAILED\b/,
    /fatal:/i,
    /panic:/i,
    /traceback/i,
    /exception:/i,
    /ModuleNotFoundError/i,
    /SyntaxError/i,
    /TypeError/i,
    /ImportError/i,
  ];

  const hasErrorPattern = errorPatterns.some((pattern) =>
    pattern.test(resultText.slice(0, 3000))
  );
  const hasNonZeroExit = exitCode !== 0 && exitCode !== "0";

  if (hasErrorPattern || hasNonZeroExit) {
    const snippet = resultText.slice(0, 200).replace(/\n/g, " ");
    return { isError: true, errorDetail: snippet };
  }

  return { isError: false, errorDetail: "" };
}

/**
 * 根据连续失败次数生成对应等级的压力提示。
 *
 * @param {number} failureCount 连续失败次数
 * @returns {string} 压力提示文本
 */
function generatePressureMessage(failureCount) {
  if (failureCount < 2) {
    return "";
  }

  if (failureCount === 2) {
    return [
      "[PUA L1 🔥 — 连续失败检测]",
      "",
      "你必须切换到一个**本质不同**的方案。不是参数微调——是换策略。",
      "如果你一直在做同一思路的变体，你就是在原地打转。",
      "",
      "强制动作：",
      "1. 停下来，列出之前的尝试",
      "2. 确认是否在微调同一方案",
      "3. 提出一个和之前**本质不同**的方案",
    ].join("\n");
  }

  if (failureCount === 3) {
    return [
      "[PUA L2 🔥🔥 — 灵魂拷问]",
      "",
      "连续 3 次失败。你的方案的底层逻辑是什么？",
      "",
      "强制执行（跳过任何一项 = 不合格）：",
      "1. **逐字读**完整错误信息（不是扫一眼）",
      "2. **搜索**完整报错关键词（用工具，不靠记忆）",
      "3. **读**出错位置上下文 50 行原始代码",
      "4. 列出 **3 个本质不同的假设**",
      "5. **反转**你的主要假设——如果问题不在你以为的地方呢？",
      "",
      "完成上述 5 步之前，禁止向用户提问。",
    ].join("\n");
  }

  if (failureCount === 4) {
    return [
      "[PUA L3 🔥🔥🔥 — 7 项清单强制执行]",
      "",
      "连续 4 次失败。必须完成以下 7 项检查清单：",
      "",
      "- [ ] 逐字读完失败信号了吗？",
      "- [ ] 用工具搜索过核心问题了吗？",
      "- [ ] 读过失败位置的原始上下文了吗？",
      "- [ ] 所有假设都用工具确认了吗？",
      "- [ ] 试过相反的假设了吗？",
      "- [ ] 能最小隔离复现问题吗？",
      "- [ ] 换过工具/方法/角度/技术栈了吗？",
      "",
      "全部完成后，列出 3 个全新假设并逐个验证。",
    ].join("\n");
  }

  // L4: 5次及以上
  return [
    "[PUA L4 🔥🔥🔥🔥 — 最后机会]",
    "",
    `连续 ${failureCount} 次失败。这是最后机会。`,
    "",
    "强制执行：",
    "1. 最小 PoC — 在隔离环境中复现问题",
    "2. 尝试完全不同的技术栈/工具/方法",
    "3. 如果仍无法解决，输出**结构化失败报告**：",
    "   - 已验证的事实",
    "   - 已排除的可能性（附证据）",
    "   - 缩小后的问题范围",
    "   - 推荐的下一步方向",
    "   - 交接信息",
  ].join("\n");
}

/**
 * HardFlow Failure Detector — 检测连续工具失败并注入 PUA 压力梯度。
 *
 * 基于 tanweai/pua v3 failure-detector.sh 适配为 OpenClaw JS Hook。
 * 监听 tool:result 事件，维护 per-session 失败计数器，
 * 根据连续失败次数注入 L1-L4 分级压力提示。
 *
 * @param {any} event OpenClaw hook event
 * @returns {Promise<void>}
 */
export default async function hardflowFailureDetector(event) {
  if (event?.type !== "tool" && event?.type !== "tool:result") {
    return;
  }

  const messages = Array.isArray(event?.messages) ? event.messages : [];
  const sessionId = event?.context?.sessionId
    ?? event?.session_id
    ?? "default";

  const homeDir = process.env.HOME || process.env.USERPROFILE || "";
  const stateDir = path.join(homeDir, ".openclaw", "pua-state");
  const counterFile = path.join(stateDir, `failure-count-${sessionId}.json`);

  if (!existsSync(stateDir)) {
    mkdirSync(stateDir, { recursive: true });
  }

  // 读取当前计数
  let state = { count: 0, sessionId };
  if (existsSync(counterFile)) {
    try {
      state = JSON.parse(readFileSync(counterFile, "utf8"));
    } catch {
      state = { count: 0, sessionId };
    }
  }

  const { isError, errorDetail } = detectFailure(event);

  if (isError) {
    state.count += 1;
    state.lastError = errorDetail;
    writeFileSync(counterFile, JSON.stringify(state, null, 2), "utf8");

    const pressureMessage = generatePressureMessage(state.count);
    if (pressureMessage) {
      messages.push(pressureMessage);
    }
  } else {
    // 成功执行 → 重置计数器
    if (state.count > 0) {
      state.count = 0;
      state.lastError = "";
      writeFileSync(counterFile, JSON.stringify(state, null, 2), "utf8");
    }
  }
}
