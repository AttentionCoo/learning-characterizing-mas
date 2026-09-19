import test from 'node:test'
import assert from 'node:assert/strict'

import { escapeHtml, renderMarkdown, clearMarkdownCache } from '../src/utils/markdown.js'

test('escapeHtml 转义 HTML 特殊字符', () => {
  assert.equal(escapeHtml('<b>&</b>'), '&lt;b&gt;&amp;&lt;/b&gt;')
  assert.equal(escapeHtml('普通文本'), '普通文本')
})

test('renderMarkdown 空输入返回空串', () => {
  assert.equal(renderMarkdown(''), '')
  assert.equal(renderMarkdown(null), '')
})

test('renderMarkdown 渲染基础 Markdown 为 HTML', () => {
  const html = renderMarkdown('**加粗** 与 *斜体*')
  assert.ok(html.includes('<strong>加粗</strong>'), html)
  assert.ok(html.includes('<em>斜体</em>'), html)
})

test('renderMarkdown 对相同输入使用缓存并返回相同结果', () => {
  clearMarkdownCache()
  const first = renderMarkdown('# 标题\n\n内容段落')
  const second = renderMarkdown('# 标题\n\n内容段落')
  assert.equal(second, first)
  clearMarkdownCache()
})

test('renderMarkdown 把「**答案：X**」行增强为答案提示块', () => {
  const html = renderMarkdown('1. 脑卒中最常见的类型是？\n   - A. 出血性脑卒中\n   - B. 缺血性脑卒中\n\n   **答案：B**')
  assert.ok(html.includes('answer-line'), html)
  assert.ok(html.includes('answer-tag'), html)
  assert.ok(html.includes('答案'), html)
  assert.ok(html.includes('B</span>') || html.includes('B</p>'), html)
})

test('renderMarkdown 中文冒号与空答案（正文另起一行）不误伤', () => {
  // 「**答案：**」单独一行：渲染为答案标签块，正文保持普通段落
  const html = renderMarkdown('**答案：**\n急性期处理原则包括：迅速识别症状。')
  assert.ok(html.includes('answer-line'), html)
  assert.ok(html.includes('急性期处理原则包括'), html)
  assert.ok(!html.includes('<strong>答案'), html)
  // 普通加粗文本不受影响
  const plain = renderMarkdown('**加粗强调**')
  assert.ok(!plain.includes('answer-line'), plain)
})

test('renderMarkdown 表格渲染带表头与斑马纹结构', () => {
  const html = renderMarkdown('| 类型 | 占比 |\n|------|------|\n| 缺血性 | 约80% |')
  assert.ok(html.includes('<table>'), html)
  assert.ok(html.includes('<th>'), html)
  assert.ok(html.includes('约80%'), html)
})
