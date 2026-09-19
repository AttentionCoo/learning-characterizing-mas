<script setup>
/**
 * 临时预览页：AI 推理轨迹设计沙盒。
 * 用真实 <ReasoningTrace> 渲染覆盖全部块类型的 mock 数据，
 * 供设计迭代与截图比对；确认设计后本页与路由一并删除。
 */
import { useThemeStore } from '@/stores/theme'
import ReasoningTrace from '@/components/ReasoningTrace.vue'

// 深色开关走全局主题 store，与全局主题同步并持久化（原先本地 ref 会绕过它）
const theme = useThemeStore()
function toggleDark() {
  theme.toggle()
}
// 支持 ?dark=1 直接进入深色模式，便于无头截图比对
if (new URLSearchParams(window.location.search).get('dark') === '1' && !theme.dark) {
  theme.toggle()
}

const runningEntries = [
  {
    key: 'r1', scope: 'preview', step: 'intent', phase: 'start',
    title: '意图识别完成：脑卒中静脉溶栓答疑',
    content: '已将本次请求识别为 tutor，进入多专家会诊链路。',
    sources: [], debate: null, experts: null, messages: null, blackboard: null,
  },
  {
    key: 'r2', scope: 'preview', step: 'evidence', phase: 'progress',
    title: '循证检索完成（Hybrid RAG 三阶漏斗）',
    content: '召回 40 条 → RRF 融合 20 条 → 精排保留 3 条权威指南证据。',
    sources: [
      {
        guide: '中国急性缺血性脑卒中诊治指南 2023',
        page: '42',
        score: '0.91',
        query: '静脉溶栓时间窗 4.5 小时 适应证',
        excerpt: '对发病 4.5 小时内的急性缺血性脑卒中患者，应尽快给予静脉阿替普酶溶栓治疗（I 类推荐，A 级证据）。给药剂量按 0.9 mg/kg 计算（最大 90 mg），其中 10% 在 1 分钟内静脉推注，其余 90% 在 60 分钟内持续静脉滴注。溶栓后 24 小时内应严密监测生命体征与神经功能变化，复查头颅 CT 排除出血转化。',
      },
      {
        guide: 'AHA/ASA 急性缺血性卒中早期管理指南 2019',
        page: '18',
        score: '0.87',
        query: 'rt-PA 禁忌证 血压阈值',
        excerpt: '溶栓前血压应控制在 185/110 mmHg 以下；活动性内出血、近期颅内出血为绝对禁忌。',
      },
    ],
    debate: null, experts: null, messages: null, blackboard: null,
  },
  {
    key: 'r3', scope: 'preview', step: 'reason', phase: 'experts',
    title: '多专家协同（3 位）',
    content: '',
    sources: [],
    experts: {
      active: ['需求分析智能体', '医学影像分析智能体', '学习激励智能体'],
      selectionReason: '意图 + 难度规则编排（难度 0.52）：需要需求拆解、影像-临床关联与情绪支持',
      debateRounds: 0,
      advices: [
        {
          role: '需求分析智能体',
          // 流式中间态：已送达部分 token，展示「生成中」光标与不截断的全文滚动
          content: '学生问的是时间窗，但真正的理解障碍在"为什么是 4.5 小时"。建议先讲清再灌注时间依赖的病理生理，再落到时间窗数字。',
          streaming: true,
        },
        {
          role: '医学影像分析智能体',
          content: '影像侧应强调：NCCT 排除出血是溶栓前提，',
          streaming: true,
        },
      ],
      arbitration: '',
    },
    messages: null, blackboard: null, debate: null,
  },
  {
    key: 'r4', scope: 'preview', step: 'reason', phase: 'verdict',
    verdictKind: 'synthesis', verdictLabel: '综合提案',
    verdictText: '正在综合三位专家的意见：教学主线按「再灌注时间依赖 → 4.5 小时锚点 → 记忆锚',
    title: '综合提案',
    content: '',
    sources: [],
    debate: null, experts: null, messages: null, blackboard: null,
    streaming: true,
  },
]

const doneEntries = [
  {
    key: 'd1', scope: 'preview', step: 'intent', phase: 'start',
    title: '意图识别完成：脑卒中静脉溶栓综合学习分析',
    content: '识别为 tutor；输入守卫通过（命中脑卒中领域关键词）。',
    sources: [], debate: null, experts: null, messages: null, blackboard: null,
  },
  {
    key: 'd2', scope: 'preview', step: 'planner', phase: 'progress',
    title: '规划完成（3 步）',
    content: '需求分析 → 多专家推理与会诊 → 汇总生成最终报告',
    sources: [],
    sources_note: '',
    debate: null, experts: null, messages: null, blackboard: null,
  },
  {
    key: 'd3', scope: 'preview', step: 'evidence', phase: 'progress',
    title: '循证检索完成',
    content: '召回 40 条 → RRF 融合 20 条 → 精排保留 3 条权威指南证据。',
    sources: [
      {
        guide: '中国急性缺血性脑卒中诊治指南 2023',
        page: '42',
        score: '0.91',
        query: '静脉溶栓时间窗 4.5 小时 适应证',
        excerpt: '对发病 4.5 小时内的急性缺血性脑卒中患者，应尽快给予静脉阿替普酶溶栓治疗（I 类推荐，A 级证据）。给药剂量按 0.9 mg/kg 计算（最大 90 mg），其中 10% 在 1 分钟内静脉推注，其余 90% 在 60 分钟内持续静脉滴注。溶栓后 24 小时内应严密监测生命体征与神经功能变化，复查头颅 CT 排除出血转化。',
      },
      {
        guide: 'AHA/ASA 急性缺血性卒中早期管理指南 2019',
        page: '18',
        score: '0.87',
        query: 'rt-PA 禁忌证 血压阈值',
        excerpt: '溶栓前血压应控制在 185/110 mmHg 以下；活动性内出血、近期颅内出血为绝对禁忌。',
      },
      {
        guide: '中国脑卒中防治指导规范 2021',
        page: '7',
        score: '0.79',
        query: 'NIHSS 评分 溶栓决策',
        excerpt: 'NIHSS ≥ 4 分且无禁忌者获益更显著；轻型卒中（NIHSS 0–3）溶栓需个体化评估。',
      },
    ],
    debate: null, experts: null, messages: null, blackboard: null,
  },
  {
    key: 'd4', scope: 'preview', step: 'reason', phase: 'experts',
    title: '多专家协同（3 位）',
    content: '',
    sources: [],
    experts: {
      active: ['需求分析智能体', '医学影像分析智能体', '学习激励智能体'],
      selectionReason: '意图 + 难度规则编排（难度 0.58）：需影像-临床关联解读与学习节奏建议',
      debateRounds: 2,
      advices: [
        {
          role: '需求分析智能体',
          content: '核心难点是"时间窗不是固定常数"。建议以再灌注时间依赖为主线，配合一个 4.5 小时内外对比病例，让学生看到获益差异。具体顺序：先建立"时间就是脑组织"的直觉，再给出 4.5 小时的数字锚点，最后补充 4.5–6 小时需结合多模影像筛选的例外情形，避免学生把数字当成绝对分界线。',
        },
        {
          role: '医学影像分析智能体',
          content: '影像侧应强调：NCCT 排除出血是溶栓前提，ASPECTS 评分影响决策；可展示早期缺血改变（岛带征、豆状核模糊）的识别。',
        },
      ],
      arbitration: '',
    },
    messages: null, blackboard: null, debate: null,
  },
  {
    key: 'd5', scope: 'preview', step: 'reason', phase: 'agent_msg',
    title: '专家会诊对话（4 条消息）',
    content: '',
    sources: [],
    debate: null, experts: null, blackboard: null,
    messages: [
      {
        from: '医学影像分析智能体', to: '需求分析智能体', round: 1, kind: 'question',
        content: '你建议用 4.5 小时内外对比病例，但如果学生还没掌握 ASPECTS，会不会反而增加认知负担？',
      },
      {
        from: '需求分析智能体', to: '医学影像分析智能体', round: 1, kind: 'object',
        content: '同意存在这个风险，但我认为对比病例的价值在于建立"时间=脑组织"的直觉，ASPECTS 可以放到第二步。',
        evidence: '学生画像显示 knowledgeBase.ischemic_core 为 weak，但未评估 ASPECTS。',
      },
      {
        from: '医学影像分析智能体', to: '__all__', round: 2, kind: 'revise',
        content: '接受。修正意见：第一层只讲 NCCT 排出血 + 时间窗，ASPECTS 作为进阶内容在第二层展开。',
        evidence: '依据指南：ASPECTS 主要用于 4.5–6 小时及取栓决策分层。',
      },
      {
        from: '学习激励智能体', to: '__all__', round: 2, kind: 'finding',
        content: '补充一条观察：学生在连续追问时间窗数字，可能反映对"记不住"的焦虑。建议在回答中显式给出记忆锚点（"4.5 小时 = 再灌注的黄金线"）。',
        evidence: '无',
      },
    ],
  },
  {
    key: 'd6', scope: 'preview', step: 'reason', phase: 'blackboard',
    title: '会诊黑板（3 条发现）',
    content: '',
    sources: [],
    debate: null, experts: null, messages: null,
    blackboard: {
      entries: [
        { role: '需求分析智能体', round: 1, content: '教学主线：再灌注时间依赖 → 时间窗数字 → 获益/风险权衡' },
        { role: '医学影像分析智能体', round: 1, content: '必须先排出血：NCCT 是溶栓前提，ASPECTS 属进阶内容' },
        { role: '学习激励智能体', round: 2, content: '给出记忆锚点，缓解"记不住数字"的焦虑' },
      ],
      convergence: '三层递进：先建立"时间=脑组织"的直觉，再落到 4.5 小时数字，最后给记忆锚点。ASPECTS 移至进阶层。',
      arbitration: '采纳收敛结论。需求分析智能体的对比病例方案修订为"第一层仅 NCCT + 时间窗"，医学影像分析智能体的 ASPECTS 建议归入进阶层。',
    },
  },
  {
    key: 'd7', scope: 'preview', step: 'reason', phase: 'debate',
    title: '多专家辩论与仲裁',
    content: '',
    sources: [],
    experts: null, messages: null, blackboard: null,
    debate: {
      rounds: 3,
      skipped: false,
      skipReason: '',
      history: [
        { round: 1, role: '需求分析智能体', content: '主张先建立时间依赖直觉，反对一上来给数字。' },
        { round: 1, role: '医学影像分析智能体', content: '反对：临床决策的入口是影像排出血，跳过影像会养成错误习惯。' },
        { round: 2, role: '需求分析智能体', content: '修正：影像排出血放在最前，但 ASPECTS 分层放到进阶。' },
      ],
      arbitration: '### ARBITRATION ###\n采纳双方修正意见：顺序为 NCCT 排出血 → 时间窗与时间依赖 → ASPECTS 进阶。\n### REASONING ###\n影像排出血是溶栓的安全前提，不可后置；ASPECTS 的分层价值主要在延长时间窗决策，属进阶内容。',
    },
  },
  {
    key: 'd8', scope: 'preview', step: 'reason', phase: 'debate',
    title: '多专家辩论与仲裁',
    content: '',
    sources: [],
    experts: null, messages: null, blackboard: null,
    debate: {
      rounds: 0, skipped: true,
      skipReason: '分歧检测：专家意见无明显分歧。三者在讲解顺序上一致，仅在表述详略上有差异。',
      history: [], arbitration: '',
    },
  },
  {
    key: 'd9', scope: 'preview', step: 'validate', phase: 'done',
    title: '质量校验完成',
    content: '规则引擎与 LLM 双层校验通过：无绝对剂量表述、无确诊语气、证据可回溯。',
    sources: [], debate: null, experts: null, messages: null, blackboard: null,
  },
  {
    key: 'd10', scope: 'preview', step: 'reason', phase: 'verdict',
    verdictKind: 'convergence', verdictLabel: '收敛结论',
    verdictText: '三层递进：先建立"时间=脑组织"的直觉，再落到 4.5 小时数字，最后给记忆锚点。ASPECTS 移至进阶层。',
    title: '收敛结论',
    content: '',
    sources: [],
    debate: null, experts: null, messages: null, blackboard: null,
  },
  {
    key: 'd11', scope: 'preview', step: 'reason', phase: 'verdict',
    verdictKind: 'arbitration', verdictLabel: '仲裁裁决',
    verdictText: '采纳收敛结论。需求分析智能体的对比病例方案修订为"第一层仅 NCCT + 时间窗"，医学影像分析智能体的 ASPECTS 建议归入进阶层。',
    title: '仲裁裁决',
    content: '',
    sources: [],
    debate: null, experts: null, messages: null, blackboard: null,
  },
]
</script>

<template>
  <div class="preview-page">
    <header class="preview-bar">
      <strong>AI 推理轨迹 · 设计预览</strong>
      <span class="preview-hint">临时页面，仅用于设计评审</span>
      <button type="button" class="preview-toggle" @click="toggleDark">
        切换到{{ theme.dark ? '浅色' : '深色' }}模式
      </button>
    </header>

    <main class="preview-stage">
      <section class="preview-case">
        <div class="case-label">① 进行中（推理中）</div>
        <div class="bubble">
          <ReasoningTrace :entries="runningEntries" :running="true" />
        </div>
      </section>

      <section class="preview-case">
        <div class="case-label">② 已完成（含专家/对话/黑板/辩论/跳过辩论）</div>
        <div class="bubble">
          <ReasoningTrace :entries="doneEntries" :running="false" />
          <div class="answer-stub">……以下是 AI 的正式回答内容（消息气泡正文）。</div>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.preview-page {
  min-height: 100vh;
  background: var(--color-bg-light);
  color: var(--color-text-strong);
}

.preview-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 24px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-base);
  position: sticky;
  top: 0;
  z-index: 5;
}

.preview-hint {
  color: var(--color-text-light);
  font-size: 12px;
}

.preview-toggle {
  margin-left: auto;
  padding: 6px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-bg-base);
  color: var(--color-text-medium);
  font-size: 13px;
  cursor: pointer;
}

.preview-stage {
  max-width: 880px;
  margin: 0 auto;
  padding: 26px 20px 80px;
}

.preview-case + .preview-case {
  margin-top: 34px;
}

.case-label {
  margin-bottom: 10px;
  color: var(--color-text-light);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.bubble {
  padding: 16px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  background: var(--color-bg-base);
}

.answer-stub {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--color-message-bg);
  color: var(--color-text-medium);
  font-size: 14px;
}
</style>
