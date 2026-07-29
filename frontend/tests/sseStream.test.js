import test from 'node:test'
import assert from 'node:assert/strict'

import { mergeStreamContent, sseStreamRequest } from '../src/utils/sseStream.js'

test('普通流式片段继续追加', () => {
  assert.equal(mergeStreamContent('一、旧片段', 'chunk', '二、新片段'), '一、旧片段二、新片段')
})

test('完整报告事件替换已接收片段而不是再次追加', () => {
  const streamed = '一、总体评估\n二、改进建议'
  const complete = '一、总体评估\n二、改进建议'

  assert.equal(mergeStreamContent(streamed, 'replace', complete), complete)
})

test('SSE 收到完整报告事件后返回替换结果并通知页面清空旧内容', async () => {
  const originalFetch = globalThis.fetch
  const originalLocalStorage = globalThis.localStorage
  const chunks = []

  globalThis.localStorage = { getItem: () => null }
  globalThis.fetch = async () => new Response([
    'data: {"type":"chunk","content":"一、旧内容"}',
    '',
    'data: {"type":"replace","content":"一、新内容\\n二、下一项"}',
    '',
    'data: {"type":"done"}',
    '',
  ].join('\n'))

  try {
    const result = await sseStreamRequest('/test', {}, {
      onChunk: (content, event) => chunks.push({ content, replace: event.replace }),
      timeout: 1000,
    })

    assert.equal(result.data.content, '一、新内容\n二、下一项')
    assert.deepEqual(chunks, [
      { content: '一、旧内容', replace: false },
      { content: '一、新内容\n二、下一项', replace: true },
    ])
  } finally {
    globalThis.fetch = originalFetch
    globalThis.localStorage = originalLocalStorage
  }
})
