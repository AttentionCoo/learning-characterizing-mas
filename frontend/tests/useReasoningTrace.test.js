import test from 'node:test'
import assert from 'node:assert/strict'

import { useReasoningTrace } from '../src/composables/useReasoningTrace.js'

test('普通事件追加为独立条目', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent({ phase: 'experts', step: 'reason', title: '专家', experts: { active: ['A'] } }, 'chat')
  appendReasoningEvent({ phase: 'done', step: 'generate_report', title: '完成' }, 'chat')
  assert.equal(reasoningEntries.value.length, 2)
  assert.equal(reasoningEntries.value[0].phase, 'experts')
  assert.equal(reasoningEntries.value[1].phase, 'done')
})

test('连续 agent_msg 事件聚合为一条会诊对话', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent({
    phase: 'agent_msg', step: 'reason',
    messages: [{ from: 'A', to: 'B', round: 1, kind: 'question', content: '难度怎么定？' }],
  }, 'chat')
  appendReasoningEvent({
    phase: 'agent_msg', step: 'reason',
    messages: [{ from: 'B', to: 'A', round: 1, kind: 'reply', content: '按画像匹配。' }],
  }, 'chat')
  appendReasoningEvent({
    phase: 'agent_msg', step: 'reason',
    messages: [{ from: 'C', to: '__all__', round: 2, kind: 'agree', content: '认同。' }],
  }, 'chat')

  assert.equal(reasoningEntries.value.length, 1)
  const entry = reasoningEntries.value[0]
  assert.equal(entry.phase, 'agent_msg')
  assert.equal(entry.messages.length, 3)
  assert.equal(entry.messages[1].from, 'B')
  assert.equal(entry.messages[2].to, '__all__')
  assert.match(entry.title, /3 条消息/)
})

test('不同 scope 的 agent_msg 事件不聚合', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent({
    phase: 'agent_msg', step: 'reason',
    messages: [{ from: 'A', to: 'B', round: 1, kind: 'question', content: 'q' }],
  }, 'chat1')
  appendReasoningEvent({
    phase: 'agent_msg', step: 'reason',
    messages: [{ from: 'B', to: 'A', round: 1, kind: 'reply', content: 'r' }],
  }, 'chat2')

  assert.equal(reasoningEntries.value.length, 2)
})

test('agent_msg 后跟其他事件则开启新条目', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent({
    phase: 'agent_msg', step: 'reason',
    messages: [{ from: 'A', to: 'B', round: 1, kind: 'question', content: 'q' }],
  }, 'chat')
  appendReasoningEvent({ phase: 'blackboard', step: 'reason', blackboard: { entries: [] } }, 'chat')
  appendReasoningEvent({
    phase: 'agent_msg', step: 'reason',
    messages: [{ from: 'B', to: 'A', round: 1, kind: 'reply', content: 'r' }],
  }, 'chat')

  assert.equal(reasoningEntries.value.length, 3)
})

test('reset 清空所有条目', () => {
  const { reasoningEntries, appendReasoningEvent, resetReasoningTrace } = useReasoningTrace()
  appendReasoningEvent({ phase: 'experts', step: 'reason', title: '专家' }, 'chat')
  resetReasoningTrace()
  assert.equal(reasoningEntries.value.length, 0)
})
