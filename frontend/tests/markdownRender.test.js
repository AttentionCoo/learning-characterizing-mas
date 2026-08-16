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
