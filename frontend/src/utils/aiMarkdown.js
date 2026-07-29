const FENCE_PATTERN = /^\s*(```|~~~)/
const ORDERED_ITEM_PATTERN = /^(\s*)(\d{1,2})[.、)）](?!\d)\s*/
const INLINE_ORDERED_ITEM_PATTERN = /([。；！？])\s*(\d{1,2})[.、)）](?!\d)\s*/g

function normalizeOrderedLine(line) {
  return line
    .replace(INLINE_ORDERED_ITEM_PATTERN, '$1\n$2. ')
    .split('\n')
    .map(part => part.replace(ORDERED_ITEM_PATTERN, '$1$2. '))
}

export function normalizeAiMarkdown(source) {
  if (!source) return ''

  const output = []
  let inCodeFence = false

  for (const originalLine of String(source).replace(/\r\n?/g, '\n').split('\n')) {
    if (FENCE_PATTERN.test(originalLine)) {
      output.push(originalLine)
      inCodeFence = !inCodeFence
      continue
    }

    if (inCodeFence) {
      output.push(originalLine)
      continue
    }

    for (const line of normalizeOrderedLine(originalLine)) {
      const isOrderedItem = ORDERED_ITEM_PATTERN.test(line)
      const previousLine = output.at(-1) || ''
      const previousIsListItem = ORDERED_ITEM_PATTERN.test(previousLine)
        || /^\s*[-*+]\s+/.test(previousLine)

      if (isOrderedItem && previousLine && !previousIsListItem) {
        output.push('')
      }
      output.push(line)
    }
  }

  return output.join('\n')
}
