<template>
  <div class="medical-image-viewer" :class="{ 'comparison-mode': isComparisonMode }">
    <!-- 工具栏 -->
    <div class="viewer-toolbar" v-if="images.length > 0">
      <span class="image-type-badge" v-if="imageType">
        {{ imageTypeLabel }}
      </span>
      <button class="tool-btn" @click="zoomIn" title="放大">🔍+</button>
      <button class="tool-btn" @click="zoomOut" title="缩小">🔍-</button>
      <button class="tool-btn" @click="resetZoom" title="重置">↺</button>
      <button
        class="tool-btn"
        v-if="images.length >= 2"
        @click="toggleComparison"
        :class="{ active: isComparisonMode }"
        title="对比模式"
      >
        ⇶ 对比
      </button>
      <button class="tool-btn" @click="$emit('close')" title="关闭">✕</button>
    </div>

    <!-- 主显示区 -->
    <div class="viewer-content" ref="contentRef">
      <!-- 单图/默认模式 -->
      <div v-if="!isComparisonMode && currentImage" class="single-view">
        <img
          :src="currentImage"
          :style="imageStyle"
          @load="onImageLoad"
          @error="onImageError"
          alt="医学影像"
        />
      </div>

      <!-- 对比模式 -->
      <div v-else-if="isComparisonMode" class="comparison-view">
        <div
          v-for="(img, idx) in images.slice(0, 2)"
          :key="idx"
          class="comparison-pane"
        >
          <div class="pane-label">{{ idx === 0 ? '影像A' : '影像B' }}</div>
          <img :src="img" :style="imageStyle" alt="对比影像" />
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else class="viewer-empty">
        <p>📷 请上传医学影像</p>
      </div>
    </div>

    <!-- 结构化发现面板 -->
    <div class="findings-panel" v-if="findings">
      <div class="findings-header" @click="showFindings = !showFindings">
        <span>🔬 影像分析结果</span>
        <span class="toggle-icon">{{ showFindings ? '▼' : '▶' }}</span>
      </div>
      <div class="findings-body" v-if="showFindings">
        <!-- 基本信息 -->
        <div class="finding-row">
          <span class="label">影像类型：</span>
          <span class="value">{{ imageTypeLabel }}</span>
        </div>
        <div class="finding-row" v-if="findings.anatomical_region">
          <span class="label">解剖区域：</span>
          <span class="value">{{ findings.anatomical_region }}</span>
        </div>

        <!-- 关键发现 -->
        <div class="finding-section" v-if="findings.key_findings?.length">
          <h4>🔑 关键发现</h4>
          <ul>
            <li v-for="(f, i) in findings.key_findings" :key="i">{{ f }}</li>
          </ul>
        </div>

        <!-- 异常发现 -->
        <div class="finding-section" v-if="findings.abnormalities?.length">
          <h4>⚠️ 异常发现（{{ findings.abnormalities.length }} 处）</h4>
          <div class="abnormality-card" v-for="(ab, i) in findings.abnormalities" :key="i">
            <div><strong>位置：</strong>{{ ab.location }}</div>
            <div><strong>描述：</strong>{{ ab.description }}</div>
            <div v-if="ab.significance"><strong>临床意义：</strong>{{ ab.significance }}</div>
            <div class="confidence-bar">
              <span>置信度：</span>
              <div class="bar-bg">
                <div class="bar-fill" :style="{ width: (ab.confidence * 100) + '%' }"></div>
              </div>
              <span>{{ (ab.confidence * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>

        <!-- 鉴别诊断 -->
        <div class="finding-section" v-if="findings.differential_diagnosis?.length">
          <h4>🩺 鉴别诊断</h4>
          <ol>
            <li v-for="(dd, i) in findings.differential_diagnosis" :key="i">{{ dd }}</li>
          </ol>
        </div>

        <!-- 建议检查 -->
        <div class="finding-section" v-if="findings.recommended_confirmatory_tests?.length">
          <h4>📋 建议确认性检查</h4>
          <ul>
            <li v-for="(t, i) in findings.recommended_confirmatory_tests" :key="i">{{ t }}</li>
          </ul>
        </div>

        <!-- 紧急程度 -->
        <div class="finding-row urgency" :class="findings.urgency_level">
          <span class="label">紧急程度：</span>
          <span class="value">{{ urgencyLabel }}</span>
        </div>

        <!-- 置信度 -->
        <div class="finding-row">
          <span class="label">整体置信度：</span>
          <div class="confidence-bar">
            <div class="bar-bg">
              <div class="bar-fill" :style="{ width: (findings.confidence * 100) + '%' }"></div>
            </div>
            <span>{{ (findings.confidence * 100).toFixed(0) }}%</span>
          </div>
        </div>

        <!-- 局限性 -->
        <div class="finding-section disclaimer" v-if="findings.limitations">
          <p>⚠️ {{ findings.limitations }}</p>
        </div>

        <!-- PubMed证据 -->
        <div class="finding-section pubmed" v-if="pubmedEvidence?.length">
          <h4>📚 PubMed 循证文献</h4>
          <div class="pubmed-card" v-for="(paper, i) in pubmedEvidence" :key="i">
            <a :href="paper.url" target="_blank" class="pubmed-title">{{ paper.title }}</a>
            <div class="pubmed-meta">{{ paper.authors }} | {{ paper.journal }} | {{ paper.pub_date }}</div>
            <div class="pubmed-abstract">{{ paper.abstract?.substring(0, 150) }}...</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部免责声明 -->
    <div class="viewer-disclaimer" v-if="findings">
      <p>⚠️ AI辅助教育工具 — 以上分析仅供医学教育参考，所有AI判读结果须经专业医生确认，不可用于临床决策。</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  images: { type: Array, default: () => [] },
  findings: { type: Object, default: null },
  pubmedEvidence: { type: Array, default: () => [] },
  imageType: { type: String, default: '' },
})

defineEmits(['close', 'analyze'])

const IMAGE_TYPE_LABELS = {
  neuroimaging_ct: '头部CT',
  neuroimaging_mri: '头部MRI',
  neuroimaging_angiography: '脑血管造影',
  pathology_slide: '病理切片',
  ecg_waveform: '心电图/脑电图',
  clinical_photo: '临床照片',
  lab_report: '检验报告',
  radiology_report: '影像报告',
  medical_illustration: '医学图解',
  courseware_image: '课件资料',
}

const URGENCY_LABELS = {
  routine: '常规',
  urgent: '紧急 ⚡',
  critical: '危急 🚨',
}

const zoom = ref(1)
const isComparisonMode = ref(false)
const showFindings = ref(true)
const loadError = ref(false)

const currentImage = computed(() => props.images[0] || null)
const imageTypeLabel = computed(() => IMAGE_TYPE_LABELS[props.imageType] || props.imageType || '医学影像')
const urgencyLabel = computed(() => URGENCY_LABELS[props.findings?.urgency_level] || '常规')

const imageStyle = computed(() => ({
  transform: `scale(${zoom.value})`,
  transition: 'transform 0.2s ease',
}))

function zoomIn() { zoom.value = Math.min(zoom.value + 0.25, 4) }
function zoomOut() { zoom.value = Math.max(zoom.value - 0.25, 0.25) }
function resetZoom() { zoom.value = 1 }
function toggleComparison() { isComparisonMode.value = !isComparisonMode.value }
function onImageLoad() { loadError.value = false }
function onImageError() { loadError.value = true }
</script>

<style scoped>
.medical-image-viewer {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--color-bg-base);
  box-shadow: var(--shadow-card);
  transition: box-shadow var(--transition-normal);
}
.medical-image-viewer:hover {
  box-shadow: var(--glow-primary);
}

/* ── 工具栏 ── */
.viewer-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--color-bg-light);
  border-bottom: 1px solid var(--color-border-light);
  backdrop-filter: blur(8px);
}
.image-type-badge {
  padding: 3px 12px;
  background: var(--gradient-aurora);
  color: #fff;
  border-radius: var(--radius-pill);
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  margin-right: auto;
  box-shadow: var(--glow-primary);
}
.tool-btn {
  padding: 5px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-base);
  color: var(--color-text-medium);
  cursor: pointer;
  font-size: 0.82rem;
  transition: all var(--transition-fast);
}
.tool-btn:hover {
  background: var(--color-active-bg);
  color: var(--color-primary);
  border-color: var(--color-primary);
}
.tool-btn.active {
  background: var(--gradient-aurora);
  color: #fff;
  border-color: transparent;
  box-shadow: var(--glow-primary);
}

/* ── 主显示区 ── */
.viewer-content {
  position: relative;
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-light);
  padding: 16px;
}
.single-view img {
  max-width: 100%;
  max-height: 500px;
  object-fit: contain;
  border-radius: var(--radius-md);
}
.comparison-view {
  display: flex;
  gap: 10px;
  width: 100%;
}
.comparison-pane {
  flex: 1;
  background: var(--color-bg-base);
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--color-border-light);
}
.comparison-pane img {
  width: 100%;
  max-height: 400px;
  object-fit: contain;
  display: block;
}
.pane-label {
  text-align: center;
  font-weight: 600;
  font-size: 0.82rem;
  padding: 6px 12px;
  background: var(--color-bg-light);
  color: var(--color-text-medium);
  border-bottom: 1px solid var(--color-border-light);
}
.viewer-empty {
  padding: 60px;
  text-align: center;
  color: var(--color-text-weak);
  font-size: 0.95rem;
}

/* ── 发现面板 ── */
.findings-panel {
  border-top: 1px solid var(--color-border-light);
}
.findings-header {
  padding: 12px 18px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 0.93rem;
  color: var(--color-text-strong);
  background: var(--color-bg-light);
  user-select: none;
  transition: background var(--transition-fast);
}
.findings-header:hover {
  background: var(--color-hover-bg);
}
.toggle-icon {
  font-size: 0.7rem;
  color: var(--color-text-weak);
}
.findings-body {
  padding: 14px 18px;
  max-height: 600px;
  overflow-y: auto;
}

/* ── 发现行 ── */
.finding-row {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 0.9rem;
}
.finding-row .label {
  font-weight: 600;
  color: var(--color-text-label);
  min-width: 80px;
}
.finding-row .value {
  color: var(--color-text-medium);
}

/* ── 发现分区 ── */
.finding-section {
  margin-top: 16px;
}
.finding-section h4 {
  margin: 0 0 8px 0;
  color: var(--color-primary-dark);
  font-size: 0.92rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}
.finding-section ul, .finding-section ol {
  margin: 4px 0;
  padding-left: 20px;
  color: var(--color-text-medium);
  font-size: 0.88rem;
  line-height: 1.7;
}
.finding-section li {
  margin-bottom: 2px;
}

/* ── 异常卡片 ── */
.abnormality-card {
  background: var(--color-active-bg);
  border-left: 3px solid var(--color-primary);
  padding: 10px 14px;
  margin-bottom: 8px;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  font-size: 0.88rem;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}
.abnormality-card:hover {
  transform: translateX(2px);
  box-shadow: 0 2px 8px rgba(17, 150, 127, 0.1);
}
.abnormality-card div {
  margin-bottom: 3px;
  color: var(--color-text-medium);
}
.abnormality-card strong {
  color: var(--color-text-strong);
}

/* ── 置信度条 ── */
.confidence-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.confidence-bar span {
  font-size: 0.82rem;
  color: var(--color-text-weak);
}
.bar-bg {
  flex: 1;
  height: 6px;
  background: var(--color-border-light);
  border-radius: 3px;
  overflow: hidden;
  max-width: 120px;
}
.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary-light), var(--color-primary));
  border-radius: 3px;
  transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 0 6px rgba(17, 150, 127, 0.3);
}

/* ── 紧急程度 ── */
.urgency.routine .value { color: var(--color-primary); }
.urgency.urgent .value { color: var(--color-orange); font-weight: 600; }
.urgency.critical .value { color: var(--color-red); font-weight: 700; }

/* ── 局限性声明 ── */
.disclaimer {
  background: var(--color-active-bg);
  border: 1px solid var(--color-border-light);
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 0.84rem;
  color: var(--color-text-medium);
}
.disclaimer p { margin: 0; }

/* ── PubMed 文献区 ── */
.pubmed {
  background: var(--color-bg-light);
  padding: 10px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-light);
}
.pubmed-card {
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--color-border-light);
}
.pubmed-card:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}
.pubmed-title {
  color: var(--color-primary-dark);
  font-weight: 600;
  text-decoration: none;
  font-size: 0.88rem;
  transition: color var(--transition-fast);
}
.pubmed-title:hover {
  color: var(--color-primary);
  text-decoration: underline;
}
.pubmed-meta {
  font-size: 0.78rem;
  color: var(--color-text-weak);
  margin-top: 2px;
}
.pubmed-abstract {
  font-size: 0.83rem;
  color: var(--color-text-medium);
  margin-top: 4px;
  line-height: 1.5;
}

/* ── 底部免责声明 ── */
.viewer-disclaimer {
  padding: 10px 18px;
  background: var(--color-active-bg);
  border-top: 1px solid rgba(17, 150, 127, 0.15);
  font-size: 0.78rem;
  text-align: center;
  color: var(--color-text-weak);
}
.viewer-disclaimer p { margin: 0; }
</style>
