import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { normalizeAiMarkdown } from './aiMarkdown.js'

marked.setOptions({ gfm: true, breaks: true })

// ── 有界渲染缓存 ─────────────────────────────────────────────
// SSE 流式追加时，同一份累积文本会在每次响应式重渲染时被重复解析/消毒，
// 长报告（数十 KB）下重复解析退化为 O(n²)。这里按输入文本缓存渲染结果。
const MAX_CACHE_ENTRIES = 300
const cache = new Map()

export function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function sanitize(dirty) {
  // 浏览器环境：DOMPurify 已初始化为可用的 sanitizer；Node 单测环境无 DOM，透传
  if (typeof DOMPurify.sanitize === 'function') {
    return DOMPurify.sanitize(dirty)
  }
  return dirty
}

// 「**答案：X**」行（含中文冒号、前后空格、空内容变体）：课程文档练习题/问答类
// 回答里答案常混在正文中不醒目，转成带标签的提示块（.answer-line）独立呈现。
// 空内容（**答案：** 单独一行、正文另起一行）也匹配，输出标签块。
const ANSWER_LINE_PATTERN = /^\s*\*\*答案[:：]\s*(.*?)\*\*\s*$/

function enhanceAnswerLines(text) {
  const out = []
  for (const line of String(text).split('\n')) {
    const m = line.match(ANSWER_LINE_PATTERN)
    if (m) {
      out.push(`<p class="answer-line"><span class="answer-tag">答案</span>${m[1]}</p>`)
      out.push('') // 块级 HTML 前后补空行，避免与相邻正文粘连成一段
    } else {
      out.push(line)
    }
  }
  return out.join('\n')
}

/**
 * AI 文本 → 安全 HTML：
 * 1. normalizeAiMarkdown 规范化流式输出中的中文序号等格式问题
 * 2. marked 解析 Markdown
 * 3. DOMPurify 消毒（XSS 防护）
 * 4. 解析失败时回退为转义后的纯文本
 */
export function renderMarkdown(text) {
  if (!text) return ''
  const cached = cache.get(text)
  if (cached !== undefined) return cached

  let html
  try {
    html = sanitize(marked.parse(enhanceAnswerLines(normalizeAiMarkdown(text))))
  } catch (e) {
    console.error('[markdown] 渲染失败，回退为纯文本:', e)
    html = `<pre style="white-space:pre-wrap;word-break:break-word">${escapeHtml(text)}</pre>`
  }

  if (cache.size >= MAX_CACHE_ENTRIES) {
    cache.clear()
  }
  cache.set(text, html)
  return html
}

export function clearMarkdownCache() {
  cache.clear()
}
