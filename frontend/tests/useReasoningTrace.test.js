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

// ── 逐 token 文本流式（text_start/delta/end）──

function streamEvent(stage, channel, payload = {}) {
  return {
    phase: 'stream', step: 'reason',
    textStream: { stage, channel, label: payload.label || '', delta: payload.delta || '', content: payload.content || '' },
  }
}

test('专家发言逐 token 写入「参与专家」区块', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent(streamEvent('text_start', 'expert:需求分析智能体', { label: '需求分析智能体' }), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'expert:需求分析智能体', { delta: '先讲' }), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'expert:需求分析智能体', { delta: '解剖' }), 'chat')

  assert.equal(reasoningEntries.value.length, 1)
  const advice = reasoningEntries.value[0].experts.advices[0]
  assert.equal(advice.role, '需求分析智能体')
  assert.equal(advice.content, '先讲解剖')
  assert.equal(advice.streaming, true, '流式中应带标记，供光标显示')

  appendReasoningEvent(streamEvent('text_end', 'expert:需求分析智能体', { content: '先讲解剖（完整）' }), 'chat')
  assert.equal(advice.content, '先讲解剖（完整）', 'text_end 以权威全文收口')
  assert.equal(advice.streaming, false)
})

test('多位专家的 token 互不串台（并发流式）', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent(streamEvent('text_start', 'expert:A'), 'chat')
  appendReasoningEvent(streamEvent('text_start', 'expert:B'), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'expert:A', { delta: 'a1' }), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'expert:B', { delta: 'b1' }), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'expert:A', { delta: 'a2' }), 'chat')

  const advices = reasoningEntries.value[0].experts.advices
  assert.equal(advices.find((x) => x.role === 'A').content, 'a1a2')
  assert.equal(advices.find((x) => x.role === 'B').content, 'b1')
})

test('专家发言流式后到达的权威发言覆盖而非重复追加', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent(streamEvent('text_start', 'expert:A'), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'expert:A', { delta: '草稿' }), 'chat')
  appendReasoningEvent(streamEvent('text_end', 'expert:A', { content: '草稿' }), 'chat')
  appendReasoningEvent({
    phase: 'experts', step: 'reason',
    expertSpeech: { role: 'A', content: '权威全文', index: 1, total: 1 },
  }, 'chat')

  const advices = reasoningEntries.value[0].experts.advices
  assert.equal(advices.length, 1, '不得出现两条同角色发言')
  assert.equal(advices[0].content, '权威全文')
})

test('综合 / 收敛 / 仲裁各自流式成独立区块且不互相覆盖', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent(streamEvent('text_start', 'synthesis', { label: '综合提案与风险批判' }), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'synthesis', { delta: '提案…' }), 'chat')
  appendReasoningEvent(streamEvent('text_start', 'convergence', { label: '教学总监收敛结论' }), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'convergence', { delta: '共识…' }), 'chat')
  appendReasoningEvent(streamEvent('text_start', 'arbitration', { label: '仲裁裁决' }), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'arbitration', { delta: '裁决…' }), 'chat')

  assert.equal(reasoningEntries.value.length, 3)
  const [syn, conv, arb] = reasoningEntries.value
  assert.equal(syn.verdictKind, 'synthesis')
  assert.equal(syn.verdictText, '提案…')
  assert.equal(conv.verdictKind, 'convergence')
  assert.equal(conv.verdictText, '共识…')
  assert.equal(arb.verdictKind, 'arbitration')
  assert.equal(arb.verdictText, '裁决…')
  assert.equal(arb.verdictLabel, '仲裁裁决')
  assert.equal(arb.phase, 'verdict')
})

test('未知 channel 的流式事件被忽略，不产生空条目', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent(streamEvent('text_start', 'unknown-channel'), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'unknown-channel', { delta: 'x' }), 'chat')
  assert.equal(reasoningEntries.value.length, 0)
})

test('辩论发言逐 token 写入同一条辩论区块，且不同发言不串字', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent(streamEvent('text_start', 'debate:1:需求分析智能体'), 'chat')
  appendReasoningEvent(streamEvent('text_start', 'debate:1:医学影像分析智能体'), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'debate:1:需求分析智能体', { delta: '我主张' }), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'debate:1:医学影像分析智能体', { delta: '我反对' }), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'debate:1:需求分析智能体', { delta: '先讲机制' }), 'chat')

  assert.equal(reasoningEntries.value.length, 1)
  const debate = reasoningEntries.value[0].debate
  assert.equal(debate.rounds, 1)
  assert.equal(debate.history.length, 2)
  assert.equal(debate.history.find((h) => h.role === '需求分析智能体').content, '我主张先讲机制')
  assert.equal(debate.history.find((h) => h.role === '医学影像分析智能体').content, '我反对')
  assert.equal(reasoningEntries.value[0].streaming, true)

  appendReasoningEvent(streamEvent('text_end', 'debate:1:需求分析智能体', { content: '我主张先讲机制' }), 'chat')
  assert.equal(reasoningEntries.value[0].streaming, true, '另一位仍在生成，区块应保持生成中')
  appendReasoningEvent(streamEvent('text_end', 'debate:1:医学影像分析智能体', { content: '我反对' }), 'chat')
  assert.equal(reasoningEntries.value[0].streaming, false)
})

test('权威 debate 事件就地覆盖流式辩论条目，不产生第二块', () => {
  const { reasoningEntries, appendReasoningEvent } = useReasoningTrace()
  appendReasoningEvent(streamEvent('text_start', 'debate:1:A'), 'chat')
  appendReasoningEvent(streamEvent('text_delta', 'debate:1:A', { delta: '草稿' }), 'chat')
  appendReasoningEvent(streamEvent('text_end', 'debate:1:A', { content: '草稿' }), 'chat')
  appendReasoningEvent({
    phase: 'debate', step: 'reason',
    debate: { rounds: 2, history: [{ round: 1, role: 'A', content: '权威全文' }], arbitration: '裁决', skipped: false },
  }, 'chat')

  assert.equal(reasoningEntries.value.length, 1)
  const entry = reasoningEntries.value[0]
  assert.equal(entry.debate.rounds, 2)
  assert.equal(entry.debate.history[0].content, '权威全文')
  assert.equal(entry.debate.arbitration, '裁决')
  assert.equal(entry.streaming, false)
})
