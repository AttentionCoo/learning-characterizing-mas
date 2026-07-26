import { ref } from 'vue'

export function useReasoningTrace() {
  const reasoningEntries = ref([])

  function resetReasoningTrace() {
    reasoningEntries.value = []
  }

  function appendReasoningEvent(event, scope = '') {
    if (!event) return

    const step = event.step || 'progress'
    const key = `${scope}:${step}`
    const existingIndex = reasoningEntries.value.findIndex(item => item.key === key)
    const existing = existingIndex >= 0 ? reasoningEntries.value[existingIndex] : null
    const entry = {
      key,
      step,
      title: event.title || existing?.title || 'AI 正在处理',
      content: event.content || existing?.content || '',
      sources: event.sources?.length ? event.sources : (existing?.sources || []),
      status: event.phase === 'done' ? 'done' : 'running',
    }

    if (existingIndex >= 0) {
      reasoningEntries.value.splice(existingIndex, 1, entry)
    } else {
      reasoningEntries.value.push(entry)
    }
  }

  return {
    reasoningEntries,
    resetReasoningTrace,
    appendReasoningEvent,
  }
}
