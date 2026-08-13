import { ref } from 'vue'

export function useReasoningTrace() {
  const reasoningEntries = ref([])
  let eventSequence = 0

  function resetReasoningTrace() {
    reasoningEntries.value = []
    eventSequence = 0
  }

  function appendReasoningEvent(event, scope = '') {
    if (!event) return

    const step = event.step || 'progress'
    reasoningEntries.value.push({
      key: `${scope}:${step}:${eventSequence++}`,
      step,
      phase: event.phase || 'progress',
      title: event.title || 'AI 正在处理',
      content: event.content || '',
      sources: event.sources || [],
      debate: event.debate || null,
    })
  }

  return {
    reasoningEntries,
    resetReasoningTrace,
    appendReasoningEvent,
  }
}
