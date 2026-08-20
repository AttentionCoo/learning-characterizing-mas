import { ref } from 'vue'

/**
 * 跟随式自动滚动（参考 ChatGPT / DeepSeek / Claude 的滚动交互）：
 * - 跟随模式：距底 < threshold 时视为在底部，新内容到达自动（瞬时）滚到底部；
 * - 暂停模式：用户上翻（距底 ≥ threshold）时停止跟随，新内容到达累计未读数；
 * - 悬浮按钮：暂停时显示"回到最新"，点击平滑滚回底部并恢复跟随、清空未读。
 */
export function useAutoScroll(containerRef, { threshold = 80 } = {}) {
  const isFollowing = ref(true)
  const unread = ref(0)
  const showBackToLatest = ref(false)

  const reduceMotion = typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  let lastUnreadAt = 0

  function distanceToBottom(el) {
    return el.scrollHeight - el.scrollTop - el.clientHeight
  }

  /** 滚到最新位置（smooth 仅用于用户主动点击；流式期间用瞬时滚动避免动画积压抖动） */
  function scrollToLatest({ smooth = false } = {}) {
    const el = containerRef.value
    if (!el) return
    el.scrollTo({
      top: el.scrollHeight,
      behavior: smooth && !reduceMotion ? 'smooth' : 'auto',
    })
    unread.value = 0
    isFollowing.value = true
    showBackToLatest.value = false
  }

  /** 容器 scroll 事件处理器：距底 < threshold 视为跟随，否则暂停并显示"回到最新"按钮 */
  function onScroll() {
    const el = containerRef.value
    if (!el) return
    const dist = distanceToBottom(el)
    isFollowing.value = dist < threshold
    showBackToLatest.value = dist >= threshold
    if (isFollowing.value) unread.value = 0
  }

  /** 新内容到达：跟随中瞬时滚底；暂停中累计未读（节流，约每秒一次，避免逐字计数） */
  function notifyNewContent() {
    const el = containerRef.value
    if (!el) return
    if (isFollowing.value) {
      scrollToLatest({ smooth: false })
    } else {
      const now = Date.now()
      if (now - lastUnreadAt > 1000) {
        unread.value = Math.min(unread.value + 1, 99)
        lastUnreadAt = now
      }
      showBackToLatest.value = true
    }
  }

  /** 重置状态（新一轮生成开始时调用） */
  function reset() {
    isFollowing.value = true
    unread.value = 0
    showBackToLatest.value = false
  }

  return {
    isFollowing,
    unread,
    showBackToLatest,
    onScroll,
    scrollToLatest,
    notifyNewContent,
    reset,
  }
}
