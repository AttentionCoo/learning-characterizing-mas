const FENCE_PATTERN = /^\s*(```|~~~)/
const SECTION_BREAK_PATTERN = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/
const ORDERED_ITEM_PATTERN = /^(\s*)(\d{1,2})[.、)）](?!\d)\s*/
const INLINE_ORDERED_ITEM_PATTERN = /([。；！？])\s*(\d{1,2})[.、)）](?!\d)\s*/g
const CHINESE_NUMERAL_CHARS = '零〇一二三四五六七八九十百两'
const CHINESE_ORDERED_ITEM_PATTERN = new RegExp(
  `^(\\s*)([${CHINESE_NUMERAL_CHARS}]+)[.、．)）]\\s*`,
)
const CHINESE_HEADING_PATTERN = new RegExp(
  `^(\\s*#{1,6}\\s+)([${CHINESE_NUMERAL_CHARS}]+)[.、．)）]\\s*(.*)$`,
)
const INLINE_CHINESE_ORDERED_ITEM_PATTERN = new RegExp(
  `([。；！？：])\\s*([${CHINESE_NUMERAL_CHARS}]+)[.、．)）]\\s*`,
  'g',
)

const CHINESE_DIGITS = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九']

function toChineseOrdinal(value) {
  if (value === 10) return '十'
  if (value < 10) return CHINESE_DIGITS[value]
  if (value < 20) return `十${CHINESE_DIGITS[value % 10]}`
  if (value < 100) {
    return `${CHINESE_DIGITS[Math.floor(value / 10)]}十${CHINESE_DIGITS[value % 10]}`
  }
  if (value < 1000) {
    const remainder = value % 100
    const suffix = remainder === 0
      ? ''
      : remainder < 10
        ? `零${CHINESE_DIGITS[remainder]}`
        : toChineseOrdinal(remainder)
    return `${CHINESE_DIGITS[Math.floor(value / 100)]}百${suffix}`
  }
  return String(value)
}

function normalizeOrderedLine(line) {
  return line
    .replace(INLINE_ORDERED_ITEM_PATTERN, '$1\n$2. ')
    .replace(INLINE_CHINESE_ORDERED_ITEM_PATTERN, '$1\n$2、')
    .split('\n')
    .map(part => part.replace(ORDERED_ITEM_PATTERN, '$1$2. '))
}

function normalizeChineseHeading(line, counters) {
  const match = line.match(CHINESE_HEADING_PATTERN)
  if (!match) {
    const heading = line.match(/^\s*(#{1,6})\s+/)
    if (heading) {
      const level = heading[1].length
      counters.fill(0, level + 1)
    }
    return null
  }

  const level = (match[1].match(/#{1,6}/) || [''])[0].length
  counters[level] += 1
  counters.fill(0, level + 1)
  return `${match[1]}${toChineseOrdinal(counters[level])}、${match[3]}`
}

export function normalizeAiMarkdown(source) {
  if (!source) return ''

  const output = []
  let inCodeFence = false
  const headingCounters = Array(7).fill(0)
  const chineseListCounters = new Map()

  for (const originalLine of String(source).replace(/\r\n?/g, '\n').split('\n')) {
    if (FENCE_PATTERN.test(originalLine)) {
      output.push(originalLine)
      inCodeFence = !inCodeFence
      chineseListCounters.clear()
      continue
    }

    if (inCodeFence) {
      output.push(originalLine)
      continue
    }

    const chineseHeading = normalizeChineseHeading(originalLine, headingCounters)
    if (chineseHeading !== null) {
      chineseListCounters.clear()
      output.push(chineseHeading)
      continue
    }

    if (/^\s*#{1,6}\s+/.test(originalLine) || SECTION_BREAK_PATTERN.test(originalLine)) {
      chineseListCounters.clear()
    }

    for (const line of normalizeOrderedLine(originalLine)) {
      const chineseItem = line.match(CHINESE_ORDERED_ITEM_PATTERN)
      let normalizedLine = line
      if (chineseItem) {
        const indent = chineseItem[1]
        const indentSize = indent.length
        const nextNumber = (chineseListCounters.get(indentSize) || 0) + 1
        chineseListCounters.set(indentSize, nextNumber)
        for (const key of chineseListCounters.keys()) {
          if (key > indentSize) chineseListCounters.delete(key)
        }
        normalizedLine = line.replace(
          CHINESE_ORDERED_ITEM_PATTERN,
          `${indent}${toChineseOrdinal(nextNumber)}、`,
        )
      }

      const isOrderedItem = ORDERED_ITEM_PATTERN.test(normalizedLine)
      const previousLine = output.at(-1) || ''
      const previousIsListItem = ORDERED_ITEM_PATTERN.test(previousLine)
        || /^\s*[-*+]\s+/.test(previousLine)

      if (isOrderedItem && previousLine && !previousIsListItem) {
        output.push('')
      }
      output.push(normalizedLine)
    }
  }

  return output.join('\n')
}
