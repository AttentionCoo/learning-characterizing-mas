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

test('SSE agent_msg 事件映射为对话级推理轨迹', async () => {
  const originalFetch = globalThis.fetch
  const originalLocalStorage = globalThis.localStorage
  const traces = []

  globalThis.localStorage = { getItem: () => null }
  globalThis.fetch = async () => new Response([
    'data: {"type":"agent_msg","node":"reason","from":"需求分析智能体","to":"题目生成智能体","round":1,"kind":"question","content":"难度怎么定？"}',
    '',
    'data: {"type":"done"}',
    '',
  ].join('\n'))

  try {
    await sseStreamRequest('/test', {}, {
      onThinking: (trace) => traces.push(trace),
      timeout: 1000,
    })

    assert.equal(traces.length, 1)
    assert.equal(traces[0].phase, 'agent_msg')
    assert.equal(traces[0].messages[0].from, '需求分析智能体')
    assert.equal(traces[0].messages[0].to, '题目生成智能体')
    assert.equal(traces[0].messages[0].kind, 'question')
    assert.equal(traces[0].messages[0].content, '难度怎么定？')
  } finally {
    globalThis.fetch = originalFetch
    globalThis.localStorage = originalLocalStorage
  }
})

test('SSE blackboard 事件映射为会诊黑板轨迹', async () => {
  const originalFetch = globalThis.fetch
  const originalLocalStorage = globalThis.localStorage
  const traces = []

  globalThis.localStorage = { getItem: () => null }
  globalThis.fetch = async () => new Response([
    'data: {"type":"blackboard","node":"reason","entries":[{"role":"需求分析智能体","round":1,"kind":"finding","content":"先拆解"}],"convergence":"共识已达成","arbitration":"以证据为准"}',
    '',
    'data: {"type":"done"}',
    '',
  ].join('\n'))

  try {
    await sseStreamRequest('/test', {}, {
      onThinking: (trace) => traces.push(trace),
      timeout: 1000,
    })

    assert.equal(traces.length, 1)
    assert.equal(traces[0].phase, 'blackboard')
    assert.equal(traces[0].blackboard.entries.length, 1)
    assert.equal(traces[0].blackboard.entries[0].role, '需求分析智能体')
    assert.equal(traces[0].blackboard.convergence, '共识已达成')
    assert.equal(traces[0].blackboard.arbitration, '以证据为准')
  } finally {
    globalThis.fetch = originalFetch
    globalThis.localStorage = originalLocalStorage
  }
})
