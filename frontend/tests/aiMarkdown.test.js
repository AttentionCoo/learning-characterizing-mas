import test from 'node:test'
import assert from 'node:assert/strict'

import { normalizeAiMarkdown } from '../src/utils/aiMarkdown.js'

test('整理中文顿号和缺少空格的数字编号', () => {
  const input = '建议如下：\n1、复习基础\n2)完成测验\n3.复盘错题'

  assert.equal(
    normalizeAiMarkdown(input),
    '建议如下：\n\n1. 复习基础\n2. 完成测验\n3. 复盘错题',
  )
})

test('拆分挤在同一行的连续编号', () => {
  const input = '1.复习基础；2.完成测验；3.复盘错题'

  assert.equal(
    normalizeAiMarkdown(input),
    '1. 复习基础；\n2. 完成测验；\n3. 复盘错题',
  )
})

test('不修改代码块中的数字内容', () => {
  const input = '```python\n1.print("test")\n```'

  assert.equal(normalizeAiMarkdown(input), input)
})
