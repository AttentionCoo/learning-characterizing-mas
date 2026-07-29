export const ASSESSMENT_RADAR_DIMENSIONS = Object.freeze([
  { key: 'knowledge', label: '知识掌握', aliases: ['知识掌握', '测验表现'] },
  { key: 'clinical', label: '临床应用', aliases: ['临床应用', '技能应用', '临床技能'] },
  { key: 'efficiency', label: '学习效率', aliases: ['学习效率', '复盘质量'] },
  { key: 'progress', label: '学习进度', aliases: ['学习进度'] },
  { key: 'engagement', label: '学习投入', aliases: ['学习投入', '学习活跃度', '自主学习'] },
])

function parseDimensions(source) {
  if (!source) return {}
  if (typeof source === 'object' && !Array.isArray(source)) return source
  if (typeof source !== 'string') return {}

  try {
    const parsed = JSON.parse(source)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

export function normalizeScore(value) {
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return null
  return Math.max(0, Math.min(100, numeric))
}

export function buildAssessmentRadar(source) {
  const dimensions = parseDimensions(source)

  return ASSESSMENT_RADAR_DIMENSIONS.map((dimension) => {
    const score = dimension.aliases
      .map((alias) => normalizeScore(dimensions[alias]))
      .find((value) => value !== null) ?? null

    return {
      key: dimension.key,
      label: dimension.label,
      score: score === null ? null : Math.round(score),
      hasData: score !== null,
    }
  })
}
