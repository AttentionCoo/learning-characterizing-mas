<script setup>
import { computed } from 'vue'
import { buildAssessmentRadar, normalizeScore } from '@/utils/assessmentRadar'

const props = defineProps({
  dimensions: {
    type: [Object, String],
    default: () => ({}),
  },
  overallScore: {
    type: [Number, String],
    default: null,
  },
})

const center = { x: 210, y: 170 }
const radius = 104
const levels = [0.2, 0.4, 0.6, 0.8, 1]

const radarData = computed(() => buildAssessmentRadar(props.dimensions))
const availableScores = computed(() => radarData.value.filter((item) => item.hasData))
const hasData = computed(() => availableScores.value.length > 0)
const averageScore = computed(() => {
  if (!availableScores.value.length) return null
  const total = availableScores.value.reduce((sum, item) => sum + item.score, 0)
  return Math.round(total / availableScores.value.length)
})
const normalizedOverallScore = computed(() => {
  const score = normalizeScore(props.overallScore)
  return score === null ? null : Math.round(score)
})

function pointAt(index, scale) {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / radarData.value.length
  return {
    x: center.x + Math.cos(angle) * radius * scale,
    y: center.y + Math.sin(angle) * radius * scale,
  }
}

function polygonPoints(scale) {
  return radarData.value
    .map((_, index) => pointAt(index, scale))
    .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
    .join(' ')
}

const dataPoints = computed(() => radarData.value
  .map((item, index) => item.hasData
    ? { ...pointAt(index, item.score / 100), ...item }
    : null)
  .filter(Boolean))

const hasRadarArea = computed(() => dataPoints.value.length >= 3)

const dataPolygon = computed(() => dataPoints.value
  .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
  .join(' '))

const labels = computed(() => radarData.value.map((item, index) => {
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / radarData.value.length
  const x = center.x + Math.cos(angle) * (radius + 38)
  const y = center.y + Math.sin(angle) * (radius + 34)
  const cosine = Math.cos(angle)
  return {
    ...item,
    x,
    y,
    anchor: cosine > 0.25 ? 'start' : cosine < -0.25 ? 'end' : 'middle',
  }
}))

function scoreColor(score) {
  if (score === null) return 'var(--color-text-weak)'
  if (score >= 80) return '#11967f'
  if (score >= 60) return '#d99a24'
  return '#d85b53'
}
</script>

<template>
  <section class="radar-analysis" aria-labelledby="radar-title">
    <div class="radar-heading">
      <div>
        <h3 id="radar-title">五维评估量化雷达图</h3>
        <p>{{ hasData ? '基于当前评估数据' : '完成评估后将在此显示量化结果' }}</p>
      </div>
      <div class="radar-summary">
        <span v-if="normalizedOverallScore !== null">综合 {{ normalizedOverallScore }}</span>
        <span v-if="averageScore !== null">五维均值 {{ averageScore }}</span>
        <span v-else>暂无量化分数</span>
      </div>
    </div>

    <div class="radar-layout">
      <figure class="radar-figure">
        <svg viewBox="0 0 420 340" role="img" :aria-label="hasData ? `五维评估量化雷达图，平均分 ${averageScore}` : '五维评估量化雷达图，暂无数据'">
          <g class="radar-grid">
            <polygon v-for="level in levels" :key="level" :points="polygonPoints(level)" />
            <line
              v-for="(_, index) in radarData"
              :key="index"
              :x1="center.x"
              :y1="center.y"
              :x2="pointAt(index, 1).x"
              :y2="pointAt(index, 1).y"
            />
          </g>

          <polygon v-if="hasRadarArea" class="radar-area" :points="dataPolygon" />

          <text v-if="!hasData" class="radar-empty" :x="center.x" :y="center.y + 5" text-anchor="middle">
            暂无量化数据
          </text>

          <g class="radar-points">
            <circle
              v-for="point in dataPoints"
              :key="point.key"
              :cx="point.x"
              :cy="point.y"
              r="4"
              :fill="scoreColor(point.score)"
            >
              <title>{{ point.label }}：{{ point.hasData ? `${point.score}分` : '暂无数据' }}</title>
            </circle>
          </g>

          <g v-for="label in labels" :key="label.key" class="radar-label">
            <text :x="label.x" :y="label.y" :text-anchor="label.anchor">{{ label.label }}</text>
            <text
              class="radar-label-score"
              :x="label.x"
              :y="label.y + 17"
              :text-anchor="label.anchor"
              :fill="scoreColor(label.score)"
            >
              {{ label.hasData ? label.score : '暂无' }}
            </text>
          </g>
        </svg>
        <figcaption>分值范围 0–100，缺失维度不计入均值</figcaption>
      </figure>

      <div class="dimension-metrics">
        <div v-for="item in radarData" :key="item.key" class="dimension-metric">
          <div class="metric-row">
            <span>{{ item.label }}</span>
            <strong :style="{ color: scoreColor(item.score) }">
              {{ item.hasData ? `${item.score}分` : '暂无数据' }}
            </strong>
          </div>
          <div class="metric-track" aria-hidden="true">
            <span
              :style="{
                width: `${item.score ?? 0}%`,
                backgroundColor: scoreColor(item.score),
              }"
            ></span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
.radar-analysis {
  margin: 4px 0 22px;
  padding: 18px 0 20px;
  border-top: 1px solid var(--color-border-light);
  border-bottom: 1px solid var(--color-border-light);
}

.radar-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 8px;

  h3 {
    margin: 0;
    color: var(--color-text-strong);
    font-size: 15px;
  }

  p {
    margin: 4px 0 0;
    color: var(--color-text-weak);
    font-size: 12px;
  }
}

.radar-summary {
  display: flex;
  gap: 14px;
  color: var(--color-text-medium);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;

  span:last-child { color: var(--color-primary-dark); }
}

.radar-layout {
  display: grid;
  grid-template-columns: minmax(300px, 1.25fr) minmax(210px, 0.75fr);
  align-items: center;
  gap: 26px;
}

.radar-figure {
  min-width: 0;
  margin: 0;

  svg {
    display: block;
    width: 100%;
    max-height: 350px;
  }

  figcaption {
    margin-top: -8px;
    color: var(--color-text-weak);
    font-size: 11px;
    text-align: center;
  }
}

.radar-grid {
  color: var(--color-border);

  polygon {
    fill: none;
    stroke: currentColor;
    stroke-width: 1;
  }

  polygon:last-of-type { stroke-width: 1.5; }

  line {
    stroke: currentColor;
    stroke-width: 1;
  }
}

.radar-area {
  fill: rgba(17, 150, 127, 0.2);
  stroke: var(--color-primary);
  stroke-width: 2.5;
  stroke-linejoin: round;
  transition: points 0.45s ease;
}

.radar-points circle {
  stroke: var(--color-bg-base);
  stroke-width: 2;
}

.radar-empty {
  fill: var(--color-text-weak);
  font-size: 13px;
  font-weight: 700;
}

.radar-label {
  font-size: 12px;
  font-weight: 700;
  fill: var(--color-text-medium);
}

.radar-label-score {
  font-size: 13px;
  font-weight: 800;
}

.dimension-metrics {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.metric-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 6px;
  color: var(--color-text-medium);
  font-size: 13px;

  strong {
    font-size: 13px;
    white-space: nowrap;
  }
}

.metric-track {
  height: 6px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--color-border-light);

  span {
    display: block;
    height: 100%;
    border-radius: inherit;
    transition: width 0.5s ease;
  }
}

@media (max-width: 720px) {
  .radar-heading { align-items: flex-start; }
  .radar-summary { flex-direction: column; gap: 4px; text-align: right; }
  .radar-layout { grid-template-columns: 1fr; gap: 12px; }
  .radar-figure svg { max-height: none; }
}
</style>
