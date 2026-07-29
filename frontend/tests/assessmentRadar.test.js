import test from 'node:test'
import assert from 'node:assert/strict'

import { buildAssessmentRadar, normalizeScore } from '../src/utils/assessmentRadar.js'

test('将评估数据转换为固定的五维雷达轴', () => {
  const result = buildAssessmentRadar({
    知识掌握: 88,
    临床应用: 76,
    学习效率: 64,
    学习进度: 92,
    学习投入: 70,
  })

  assert.deepEqual(
    result.map(({ label, score }) => ({ label, score })),
    [
      { label: '知识掌握', score: 88 },
      { label: '临床应用', score: 76 },
      { label: '学习效率', score: 64 },
      { label: '学习进度', score: 92 },
      { label: '学习投入', score: 70 },
    ],
  )
})

test('兼容 JSON 字符串、按优先级选取同义维度并限制异常分数', () => {
  const result = buildAssessmentRadar(JSON.stringify({
    测验表现: '82',
    技能应用: 74,
    临床技能: 66,
    复盘质量: 120,
    学习进度: -8,
    学习活跃度: 90,
    自主学习: 70,
  }))

  assert.deepEqual(result.map(item => item.score), [82, 74, 100, 0, 90])
})

test('缺失维度保持为空且不使用综合分填充', () => {
  const result = buildAssessmentRadar({ 综合: 90, 知识掌握: 85 })

  assert.deepEqual(result.map(item => item.score), [85, null, null, null, null])
  assert.equal(result.filter(item => item.hasData).length, 1)
})

test('空综合分保持为空，不转换为零分', () => {
  assert.equal(normalizeScore(null), null)
  assert.equal(normalizeScore(''), null)
  assert.equal(normalizeScore('88.6'), 88.6)
})
