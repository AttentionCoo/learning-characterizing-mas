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

// ── 实时流式：专家发言逐条到达时聚合进同一个「参与专家」区块 ──

test('连续到达的专家发言聚合进同一条参与专家条目', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent({
    phase: 'experts', step: 'reason', title: '多专家协同（3 位）',
    experts: { active: ['需求分析智能体', '文档撰写智能体', '学习激励智能体'], advices: [], selectionReason: '难度 0.52' },
  }, 'chat')
  appendReasoningEvent({
    phase: 'experts', step: 'reason',
    expertSpeech: { role: '需求分析智能体', content: '先讲解剖', index: 1, total: 3 },
  }, 'chat')
  appendReasoningEvent({
    phase: 'experts', step: 'reason',
    expertSpeech: { role: '文档撰写智能体', content: '给文档', index: 2, total: 3 },
  }, 'chat')

  assert.equal(reasoningEntries.value.length, 1, '发言应并入名单条目，而不是各开一条')
  const ex = reasoningEntries.value[0].experts
  assert.equal(ex.active.length, 3)
  assert.equal(ex.selectionReason, '难度 0.52')
  assert.deepEqual(ex.advices.map((a) => a.role), ['需求分析智能体', '文档撰写智能体'])
})

test('发言先到、名单后到时就地补齐，不拆成两块', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent({
    phase: 'experts', step: 'reason',
    expertSpeech: { role: '需求分析智能体', content: 'a', index: 1, total: 2 },
  }, 'chat')
  appendReasoningEvent({
    phase: 'experts', step: 'reason', title: '多专家协同（2 位）',
    experts: { active: ['需求分析智能体', '学习激励智能体'], selectionReason: '规则编排', debateRounds: 2 },
  }, 'chat')

  assert.equal(reasoningEntries.value.length, 1)
  const entry = reasoningEntries.value[0]
  assert.deepEqual(entry.experts.active, ['需求分析智能体', '学习激励智能体'])
  assert.equal(entry.experts.selectionReason, '规则编排')
  assert.equal(entry.experts.debateRounds, 2)
  assert.equal(entry.experts.advices.length, 1, '已有发言不应重复追加')
  assert.equal(entry.title, '多专家协同（2 位）')
})

test('名单里的发言与已到达的发言按角色去重', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent({
    phase: 'experts', step: 'reason',
    expertSpeech: { role: 'A', content: '实时版', index: 1, total: 2 },
  }, 'chat')
  appendReasoningEvent({
    phase: 'experts', step: 'reason', title: '多专家协同（2 位）',
    experts: {
      active: ['A', 'B'],
      advices: [{ role: 'A', content: '补发版' }, { role: 'B', content: 'b' }],
    },
  }, 'chat')

  const advices = reasoningEntries.value[0].experts.advices
  assert.deepEqual(advices.map((a) => a.role), ['A', 'B'])
  assert.equal(advices[0].content, '实时版', '已到达的实时发言优先保留')
})

test('不同 scope 的专家发言不聚合', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent({
    phase: 'experts', step: 'reason',
    expertSpeech: { role: 'A', content: 'a', index: 1, total: 1 },
  }, 'chat1')
  appendReasoningEvent({
    phase: 'experts', step: 'reason',
    expertSpeech: { role: 'B', content: 'b', index: 1, total: 1 },
  }, 'chat2')
  assert.equal(reasoningEntries.value.length, 2)
})
