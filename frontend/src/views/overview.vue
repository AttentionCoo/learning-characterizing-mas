<script setup>
import { ref, computed, onMounted } from 'vue'
import request from '@/utils/request'

const overview = ref(null)
const loading = ref(true)

async function fetchOverview() {
  loading.value = true
  try {
    const res = await request.get('/user/overview')
    overview.value = res.data || {}
  } catch {
    overview.value = null
  } finally {
    loading.value = false
  }
}

onMounted(fetchOverview)

// 闭环四步：画像 → 资源/路径 → 评估 → 反馈
const STEPS = [
  { key: 'profile', title: '构建画像', desc: '对话生成学习画像', icon: '🧭' },
  { key: 'learn', title: '学习实践', desc: '资源 + 路径 + 辅导', icon: '📚' },
  { key: 'assess', title: '效果评估', desc: '多维评估与薄弱点', icon: '📊' },
  { key: 'adapt', title: '反馈优化', desc: '回流画像 + 路径调整', icon: '🔄' },
]

const profileReady = computed(() => Boolean(overview.value?.profile?.built))
const pathProgress = computed(() => overview.value?.learningPath?.progress ?? 0)
const hasAssessment = computed(() => overview.value?.assessment?.latestScore != null)
const stage = computed(() => overview.value?.stage || 'not_started')

const stageLabel = computed(() => ({
  not_started: '尚未开始——先构建你的学习画像',
  learning: '学习中——继续学习并完成评估',
  assessed: '已评估——评估结果已回流画像并优化路径',
  completed: '已完成一轮闭环——开启新目标继续学习',
}[stage.value] || ''))

function scoreColor(score) {
  if (score == null) return '#94a3b8'
  if (score >= 80) return '#10b981'
  if (score >= 60) return '#f59e0b'
  return '#ef4444'
}
</script>

<template>
  <div class="overview-page">
    <div class="page-header">
      <div class="header-content">
        <h1>学习总览</h1>
        <p>你的脑卒中个性化学习闭环</p>
      </div>
      <div class="header-badge">闭环 · 画像 → 学习 → 评估 → 优化</div>
    </div>

    <div v-if="loading" class="overview-loading">
      <div class="loading-spinner"></div>
      <span>正在汇总学习数据...</span>
    </div>

    <div v-else-if="!overview" class="overview-empty">
      <p>暂时无法获取学习数据，请稍后刷新。</p>
      <button class="retry-btn" @click="fetchOverview">重新加载</button>
    </div>

    <div v-else class="overview-body">
      <!-- 闭环进度条 -->
      <div class="loop-card">
        <div class="loop-title">学习闭环进度</div>
        <div class="loop-steps">
          <div
            v-for="(step, i) in STEPS"
            :key="step.key"
            class="loop-step"
            :class="{
              done: i === 0 ? profileReady : (i === 1 ? (pathProgress > 0 || overview.resources?.count > 0) : (i === 2 ? hasAssessment : hasAssessment)),
            }"
          >
            <div class="loop-icon">{{ step.icon }}</div>
            <div class="loop-label">{{ step.title }}</div>
            <div class="loop-desc">{{ step.desc }}</div>
          </div>
        </div>
        <div class="loop-status">
          <span class="status-pulse" :class="stage"></span>
          {{ stageLabel }}
        </div>
      </div>

      <!-- 数据卡片 -->
      <div class="stat-grid">
        <router-link to="/profile" class="stat-card">
          <div class="stat-icon">🧭</div>
          <div class="stat-info">
            <div class="stat-label">学习画像</div>
            <div class="stat-value">
              {{ overview.profile?.built ? `${overview.profile.dimensionCount} 个维度` : '未构建' }}
            </div>
            <div class="stat-sub">{{ overview.profile?.built ? '画像已就绪，贯穿全部模块' : '点击开始对话构建画像' }}</div>
          </div>
        </router-link>

        <router-link to="/learning-path" class="stat-card">
          <div class="stat-icon">🗺️</div>
          <div class="stat-info">
            <div class="stat-label">学习路径</div>
            <div class="stat-value">{{ overview.learningPath?.progress || 0 }}%</div>
            <div class="stat-progress-bar">
              <div class="stat-progress-fill" :style="{ width: `${overview.learningPath?.progress || 0}%` }"></div>
            </div>
            <div class="stat-sub">
              {{ overview.learningPath?.completedSteps || 0 }}/{{ overview.learningPath?.totalSteps || 0 }} 步完成
            </div>
          </div>
        </router-link>

        <router-link to="/resources" class="stat-card">
          <div class="stat-icon">📚</div>
          <div class="stat-info">
            <div class="stat-label">学习资源</div>
            <div class="stat-value">{{ overview.resources?.count || 0 }}</div>
            <div class="stat-sub">已生成个性化学习资源</div>
          </div>
        </router-link>

        <router-link to="/assessment" class="stat-card">
          <div class="stat-icon">📊</div>
          <div class="stat-info">
            <div class="stat-label">学习评估</div>
            <div class="stat-value" :style="{ color: scoreColor(overview.assessment?.latestScore) }">
              {{ overview.assessment?.latestScore != null ? `${overview.assessment.latestScore} 分` : '未评估' }}
            </div>
            <div class="stat-sub">
              {{ overview.assessment?.latestScore != null
                ? `共 ${overview.assessment.reportCount} 份报告，薄弱点已回流画像`
                : '完成学习后发起效果评估' }}
            </div>
          </div>
        </router-link>

        <router-link to="/tutor" class="stat-card">
          <div class="stat-icon">💬</div>
          <div class="stat-info">
            <div class="stat-label">智能辅导</div>
            <div class="stat-value">{{ overview.tutor?.talkCount || 0 }}</div>
            <div class="stat-sub">次辅导对话，专家会诊随时可用</div>
          </div>
        </router-link>
      </div>

      <!-- 闭环说明 -->
      <div class="loop-explain">
        <div class="explain-title">闭环如何运转</div>
        <div class="explain-grid">
          <div class="explain-item">
            <strong>① 画像构建</strong>
            <span>通过对话生成你的学习画像（知识基础、认知风格、薄弱点等）</span>
          </div>
          <div class="explain-item">
            <strong>② 个性化学习</strong>
            <span>画像注入资源生成、路径规划与智能辅导，内容贴合你的水平与偏好</span>
          </div>
          <div class="explain-item">
            <strong>③ 效果评估</strong>
            <span>基于真实学习数据多维评估，识别薄弱环节与进度瓶颈</span>
          </div>
          <div class="explain-item">
            <strong>④ 反馈优化</strong>
            <span>评估薄弱点自动回流画像，路径按评估结果动态调整，开启下一轮学习</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.overview-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 28px 16px;
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.header-content {
  h1 { margin: 0; font-size: 1.5rem; font-weight: 800; color: var(--color-text-strong); }
  p { margin: 4px 0 0; font-size: 13px; color: var(--color-text-medium); }
}

.header-badge {
  padding: 5px 14px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 700;
  background: rgba(17, 150, 127, 0.1);
  color: var(--color-primary-dark);
}

.overview-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 28px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.overview-loading, .overview-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-text-medium);
}

.loading-spinner {
  width: 28px; height: 28px;
  border: 3px solid var(--color-border-light);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.retry-btn {
  padding: 8px 20px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-primary-dark);
  cursor: pointer;
}

.loop-card {
  padding: 18px 20px;
  border: 1px solid var(--color-border-light);
  border-radius: 12px;
  background: var(--color-bg-light);
}

.loop-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-strong);
  margin-bottom: 14px;
}

.loop-steps {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.loop-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  border-radius: 10px;
  background: var(--color-bg-base);
  border: 1px solid var(--color-border-light);
  opacity: 0.55;
  transition: all 0.25s ease;

  &.done {
    opacity: 1;
    border-color: var(--color-primary);
    box-shadow: 0 0 0 1px var(--color-primary);
  }
}

.loop-icon { font-size: 22px; }
.loop-label { font-size: 13px; font-weight: 700; color: var(--color-text-strong); }
.loop-desc { font-size: 11px; color: var(--color-text-medium); text-align: center; }

.loop-status {
  margin-top: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-primary-dark);
  font-weight: 600;
}

.status-pulse {
  width: 9px; height: 9px;
  border-radius: 50%;
  background: var(--color-primary);
  animation: pulse 1.6s ease-in-out infinite;

  &.assessed, &.completed { background: #10b981; }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
}

.stat-card {
  display: flex;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--color-border-light);
  border-radius: 12px;
  background: var(--color-bg-light);
  text-decoration: none;
  transition: all 0.2s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: var(--glow-dreamy);
    border-color: var(--color-primary);
  }
}

.stat-icon {
  flex: none;
  width: 42px; height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  border-radius: 10px;
  background: rgba(17, 150, 127, 0.08);
}

.stat-info { flex: 1; min-width: 0; }
.stat-label { font-size: 12px; color: var(--color-text-medium); }
.stat-value { font-size: 20px; font-weight: 800; color: var(--color-text-strong); margin: 2px 0; }
.stat-sub { font-size: 11px; color: var(--color-text-light); line-height: 1.5; }

.stat-progress-bar {
  height: 5px;
  border-radius: 3px;
  background: var(--color-border-light);
  overflow: hidden;
  margin: 4px 0;
}

.stat-progress-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--gradient-aurora);
  transition: width 0.6s ease;
}

.loop-explain {
  padding: 18px 20px;
  border: 1px solid var(--color-border-light);
  border-radius: 12px;
  background: var(--color-bg-light);
}

.explain-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-strong);
  margin-bottom: 12px;
}

.explain-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.explain-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--color-bg-base);

  strong { font-size: 13px; color: var(--color-primary-dark); }
  span { font-size: 12px; color: var(--color-text-medium); line-height: 1.6; }
}

@media (max-width: 768px) {
  .overview-body { padding: 16px; }
  .loop-steps { grid-template-columns: repeat(2, 1fr); }
  .stat-grid { grid-template-columns: 1fr; }
}
</style>
