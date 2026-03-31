#!/usr/bin/env node
/**
 * pretext-check-overflow.js
 *
 * 命令行文本溢出检测工具
 * 基于 @chenglou/pretext 纯 JS 文本测量引擎
 *
 * 用法:
 *   node pretext-check-overflow.js --text "按钮文案" --font "14px Inter" --width 120 --line-height 20
 *   node pretext-check-overflow.js --json '[{"text":"提交","font":"14px Inter","width":80,"lineHeight":20}]'
 *   node pretext-check-overflow.js --file components.json
 *
 * 退出码:
 *   0 = 全部通过（无溢出）
 *   1 = 存在溢出
 *   2 = 参数错误
 */

const { prepare, layout } = require('@chenglou/pretext')

/**
 * 检测单个文本是否溢出容器
 * @param {string} text - 文本内容
 * @param {string} font - CSS font 声明, e.g. '14px Inter'
 * @param {number} maxWidth - 容器最大宽度 (px)
 * @param {number} lineHeight - 行高 (px)
 * @param {number} [maxLines=1] - 允许的最大行数，超过即视为溢出
 * @returns {{ overflow: boolean, lineCount: number, height: number }}
 */
function checkOverflow(text, font, maxWidth, lineHeight, maxLines = 1) {
  const prepared = prepare(text, font)
  const result = layout(prepared, maxWidth, lineHeight)
  return {
    overflow: result.lineCount > maxLines,
    lineCount: result.lineCount,
    height: result.height,
  }
}

// --- CLI ---
function parseArgs() {
  const args = process.argv.slice(2)
  const opts = {}
  for (let i = 0; i < args.length; i++) {
    const key = args[i]
    if (key === '--text') opts.text = args[++i]
    else if (key === '--font') opts.font = args[++i]
    else if (key === '--width') opts.width = Number(args[++i])
    else if (key === '--line-height') opts.lineHeight = Number(args[++i])
    else if (key === '--max-lines') opts.maxLines = Number(args[++i])
    else if (key === '--json') opts.json = args[++i]
    else if (key === '--file') opts.file = args[++i]
    else if (key === '--help' || key === '-h') opts.help = true
  }
  return opts
}

function printUsage() {
  console.log(`
pretext-check-overflow - 文本溢出检测工具

用法:
  单个检测:
    node pretext-check-overflow.js --text "文案" --font "14px Inter" --width 120 --line-height 20

  批量检测 (JSON):
    node pretext-check-overflow.js --json '[{"text":"提交","font":"14px Inter","width":80,"lineHeight":20}]'

  批量检测 (文件):
    node pretext-check-overflow.js --file components.json

参数:
  --text         文本内容
  --font         CSS font 声明 (e.g. '14px Inter')
  --width        容器最大宽度 (px)
  --line-height  行高 (px)
  --max-lines    允许最大行数 (默认: 1)
  --json         JSON 数组格式的批量检测
  --file         JSON 文件路径
  --help         显示此帮助
`)
}

function main() {
  const opts = parseArgs()

  if (opts.help) {
    printUsage()
    process.exit(0)
  }

  // 批量模式
  if (opts.json || opts.file) {
    let items
    if (opts.file) {
      const fs = require('fs')
      items = JSON.parse(fs.readFileSync(opts.file, 'utf8'))
    } else {
      items = JSON.parse(opts.json)
    }

    let hasOverflow = false
    const results = []

    for (const item of items) {
      const r = checkOverflow(
        item.text,
        item.font || '14px Inter',
        item.width || 200,
        item.lineHeight || 20,
        item.maxLines || 1,
      )
      const status = r.overflow ? '❌ OVERFLOW' : '✅ OK'
      const name = item.name || item.text.substring(0, 20)
      console.log(`${status}  ${name}  lines=${r.lineCount} height=${r.height}px`)
      if (r.overflow) hasOverflow = true
      results.push({ ...item, ...r })
    }

    console.log(`\n总计: ${items.length} 项, ${results.filter(r => r.overflow).length} 溢出`)
    process.exit(hasOverflow ? 1 : 0)
  }

  // 单个模式
  if (!opts.text || !opts.font || !opts.width || !opts.lineHeight) {
    console.error('错误: 缺少必要参数。使用 --help 查看用法。')
    process.exit(2)
  }

  const r = checkOverflow(opts.text, opts.font, opts.width, opts.lineHeight, opts.maxLines || 1)
  const status = r.overflow ? '❌ OVERFLOW' : '✅ OK'
  console.log(`${status}  lines=${r.lineCount} height=${r.height}px`)
  console.log(JSON.stringify(r, null, 2))
  process.exit(r.overflow ? 1 : 0)
}

main()
