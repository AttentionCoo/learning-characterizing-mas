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

test('连续中文大写序号重复时按出现顺序重新编号', () => {
  const input = '一、复习基础\n一、完成测验\n一、复盘错题'

  assert.equal(
    normalizeAiMarkdown(input),
    '一、复习基础\n二、完成测验\n三、复盘错题',
  )
})

test('中文大写标题序号分别按标题层级重新编号', () => {
  const input = [
    '## 一、总体评估',
    '### 一、优势',
    '### 一、短板',
    '## 一、改进计划',
    '### 一、第一步',
  ].join('\n')

  assert.equal(
    normalizeAiMarkdown(input),
    [
      '## 一、总体评估',
      '### 一、优势',
      '### 二、短板',
      '## 二、改进计划',
      '### 一、第一步',
    ].join('\n'),
  )
})

test('不修改代码块中的中文大写序号', () => {
  const input = '```text\n一、原始内容\n一、原始内容\n```'

  assert.equal(normalizeAiMarkdown(input), input)
})

test('拆分并重排同一行内重复的中文大写序号', () => {
  const input = '建议如下：一、复习基础；一、完成测验；一、复盘错题'

  assert.equal(
    normalizeAiMarkdown(input),
    '建议如下：\n一、复习基础；\n二、完成测验；\n三、复盘错题',
  )
})

test('中文大写章节被正文隔开时仍连续编号', () => {
  const input = [
    '一、总体评估',
    '当前基础掌握较好。',
    '',
    '一、改进建议',
    '建议增加练习。',
    '',
    '一、行动计划',
  ].join('\n')

  assert.equal(
    normalizeAiMarkdown(input),
    [
      '一、总体评估',
      '当前基础掌握较好。',
      '',
      '二、改进建议',
      '建议增加练习。',
      '',
      '三、行动计划',
    ].join('\n'),
  )
})
