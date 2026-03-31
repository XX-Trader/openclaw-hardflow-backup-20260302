---
name: pretext-text-layout
displayName: "Pretext 文本布局计算"
version: "1.0.0"
description: "Pure-JS text measurement & layout engine (no DOM reflow). Use for overflow detection, height pre-calculation, virtual list sizing, and cross-env layout verification."
description_zh: "纯 JS 文本测量与布局引擎，无 DOM 重排。用于溢出检测、高度预计算、虚拟列表尺寸、跨环境布局校验。"
license: "MIT"
updated_at: "2026-03-31"
upstream: "https://github.com/chenglou/pretext"
npm_package: "@chenglou/pretext"

triggers:
  keywords:
    - "文本溢出"
    - "text overflow"
    - "布局计算"
    - "layout measurement"
    - "虚拟列表高度"
    - "virtual list height"
    - "CLS 优化"
    - "pretext"
  auto_trigger: true
  confidence_threshold: 0.7

tools:
  required: []
  optional:
    - Read
    - Write
    - Bash

permissions:
  level: "read"
---

# Pretext 文本布局计算技能

> 基于 [chenglou/pretext](https://github.com/chenglou/pretext) — 纯 JS/TS 文本测量与布局库
> 
> **核心价值**：完全避开 `getBoundingClientRect` 等触发浏览器重排的 DOM API，纯算术运算计算文本布局，性能极强。

## 何时触发

当前 Agent 遇到以下场景时，应自动调用此技能：

1. **文本溢出检测**：判断按钮/标签/卡片中的文本是否会溢出容器
2. **虚拟列表高度计算**：精确计算动态行高，消除滚动跳变
3. **CLS（布局偏移）优化**：提前算好文本高度做占位
4. **跨环境布局一致性**：确保多浏览器/多端文本渲染结果一致
5. **AI 生成 UI 预校验**：生成阶段检查文本是否溢出，无需渲染到浏览器
6. **Canvas/SVG/WebGL 文本渲染**：为非 DOM 渲染环境提供精确的换行与尺寸计算

## 安装

```bash
npm install @chenglou/pretext
```

Node.js 环境需要额外安装 Canvas polyfill：
```bash
npm install canvas
```

或使用一键安装脚本：
```bash
bash scripts/install.sh
```

## 性能基线

| 操作 | 500 段文本耗时 | 说明 |
|------|---------------|------|
| `prepare()` | ~19ms | 一次性预处理（字体测量） |
| `layout()` | ~0.09ms | 纯算术布局计算 |

> `layout()` 比 `prepare()` 快 **200 倍**，因此同一文本只需 prepare 一次，后续任意次 layout（如窗口 resize）代价极低。

## API 速查

### Use Case 1：快速测量文本高度（不碰 DOM）

```javascript
import { prepare, layout } from '@chenglou/pretext'

// 一次性预处理：分析文本 + 测量字体宽度
const prepared = prepare('AGI 春天到了. بدأت الرحلة 🚀', '16px Inter')

// 纯算术计算高度（可重复调用，如 resize 时）
const { height, lineCount } = layout(prepared, 300, 20)
// 300 = maxWidth(px), 20 = lineHeight(px)
```

**`prepare()` 签名**：
```typescript
prepare(
  text: string,
  font: string,  // 同 CSS font shorthand, e.g. '16px Inter', 'bold 14px "Helvetica Neue"'
  options?: { whiteSpace?: 'normal' | 'pre-wrap' }
): PreparedText
```

**`layout()` 签名**：
```typescript
layout(
  prepared: PreparedText,
  maxWidth: number,
  lineHeight: number
): { height: number, lineCount: number }
```

### Use Case 2：逐行手动布局

```javascript
import { prepareWithSegments, layoutWithLines } from '@chenglou/pretext'

const prepared = prepareWithSegments('多行文本...', '18px "Helvetica Neue"')
const { lines } = layoutWithLines(prepared, 320, 26)

// 渲染到 Canvas
for (let i = 0; i < lines.length; i++) {
  ctx.fillText(lines[i].text, 0, i * 26)
}
```

**高级 API**：
- `layoutWithLines()` — 返回所有行信息（text, width, start/end cursor）
- `walkLineRanges()` — 低开销遍历行宽度（适合二分搜索最佳宽度）
- `layoutNextLine()` — 迭代器模式，每行可用不同 maxWidth（文字绕排图片）

**辅助 API**：
- `clearCache()` — 清除内部字体测量缓存
- `setLocale(locale?)` — 设置文本分段的 locale

### 特殊功能

**textarea 模式**（保留空格和换行）：
```javascript
const prepared = prepare(textareaValue, '16px Inter', { whiteSpace: 'pre-wrap' })
```

**文字绕排图片**：
```javascript
let cursor = { segmentIndex: 0, graphemeIndex: 0 }
let y = 0
while (true) {
  const width = y < image.bottom ? columnWidth - image.width : columnWidth
  const line = layoutNextLine(prepared, cursor, width)
  if (line === null) break
  ctx.fillText(line.text, 0, y)
  cursor = line.end
  y += 26
}
```

## 工作流集成指南

### 🤖 web-agent 集成

**场景**：Agent 填充内容到页面前，预判文本是否溢出。

```javascript
// web-agent 填充前置校验钩子
async function prefillCheck(text, containerWidth, font, lineHeight) {
  const { prepare, layout } = await import('@chenglou/pretext')
  const prepared = prepare(text, font)
  const { height, lineCount } = layout(prepared, containerWidth, lineHeight)

  return {
    willOverflow: lineCount > 1,  // 单行场景：超过1行即溢出
    estimatedHeight: height,
    lineCount,
  }
}
```

**收益**：
- 操作前预判布局变化，减少 50%+ 的 DOM 校验操作
- 跨浏览器布局结果一致，Agent 元素定位准确率提升
- 无需启动 Headless Chrome 即可做布局分析

### 🧪 tester 集成

**场景**：CI 流水线中批量检测文本溢出。

```javascript
// 命令行溢出检测工具调用
// node scripts/pretext-check-overflow.js --text "按钮文案" --font "14px Inter" --width 120 --line-height 20
```

**批量扫描示例**：
```javascript
const components = [
  { name: 'submit-btn', text: '提交订单', width: 80, font: '14px Inter', lineHeight: 20 },
  { name: 'nav-label', text: 'Dashboard Overview', width: 120, font: '13px Roboto', lineHeight: 18 },
  // ...
]

for (const c of components) {
  const prepared = prepare(c.text, c.font)
  const { lineCount } = layout(prepared, c.width, c.lineHeight)
  if (lineCount > 1) {
    console.error(`❌ ${c.name}: "${c.text}" overflows (${lineCount} lines)`)
    process.exitCode = 1
  }
}
```

**收益**：
- 几千个用例几毫秒跑完，不需要启动浏览器
- 直接集成到 CI，漏测率降为 0
- 多语言/极限文案自动化检测

## 语言兼容性

✅ 中文、日文、韩文
✅ 阿拉伯语等双向文本（Bidi）
✅ Emoji 与混合文本
✅ 各浏览器兼容性差异自动处理

## 注意事项

1. **`prepare()` 是昂贵操作**：同一文本 + 字体不要重复调用，应缓存结果
2. **`layout()` 是廉价操作**：resize 时只需重新 layout，不需要重新 prepare
3. **`font` 参数必须与 CSS 声明一致**：包含 size、weight、style、family
4. **Node.js 环境**：需要安装 `canvas` 包提供底层字体测量能力

## 参考链接

- 🔗 GitHub: https://github.com/chenglou/pretext
- 🔗 在线 Demo: https://chenglou.me/pretext/
- 📦 NPM: https://www.npmjs.com/package/@chenglou/pretext
