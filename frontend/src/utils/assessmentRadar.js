export const ASSESSMENT_RADAR_DIMENSIONS = Object.freeze([
  { key: 'knowledge', label: '知识掌握度', aliases: ['knowledgeMastery', '知识掌握度', '知识掌握', '测验表现'] },
  { key: 'efficiency', label: '学习效率', aliases: ['learningEfficiency', '学习效率', '复盘质量'] },
  { key: 'skill', label: '技能应用', aliases: ['skillApplication', '技能应用', '临床应用', '临床技能'] },
  { key: 'consistency', label: '学习一致性', aliases: ['learningConsistency', '学习一致性', '学习投入', '学习活跃度', '自主学习'] },
  { key: 'progress', label: '进度对齐度', aliases: ['progressAlignment', '进度对齐度', '学习进度'] },
])

function parseDimensions(source) {
  if (!source) return {}
  if (typeof source === 'object' && !Array.isArray(source)) return source
  if (typeof source !== 'string') return {}

  try {
    const parsed = JSON.parse(source)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return source
  }
}

export function normalizeScore(value) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'object' && !Array.isArray(value)) {
    return normalizeScore(value.score ?? value.value)
  }
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return null
  return Math.max(0, Math.min(100, numeric))
}

function readDimensionScore(dimensions, alias) {
  if (typeof dimensions === 'object') {
    return normalizeScore(dimensions[alias])
  }

  const escapedAlias = alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = dimensions.match(
    new RegExp(`${escapedAlias}[^0-9\\n]{0,16}(\\d{1,3})(?:\\s*分|\\s*%|\\s*\\/100)?`, 'i'),
  )
  return normalizeScore(match?.[1])
}

export function buildAssessmentRadar(source) {
  const dimensions = parseDimensions(source)

  return ASSESSMENT_RADAR_DIMENSIONS.map((dimension) => {
    const score = dimension.aliases
      .map((alias) => readDimensionScore(dimensions, alias))
      .find((value) => value !== null) ?? null

    return {
      key: dimension.key,
      label: dimension.label,
      score: score === null ? null : Math.round(score),
      hasData: score !== null,
    }
  })
}
