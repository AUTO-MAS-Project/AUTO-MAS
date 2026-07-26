<template>
  <div ref="containerRef" class="log-line-list" tabindex="0" @scroll="onScroll">
    <div class="log-line-list__sizer" :style="{ height: `${totalHeight}px` }">
      <div class="log-line-list__viewport" :style="{ transform: `translateY(${groupOffset}px)` }">
        <div
          v-for="item in visibleItems"
          :key="item.index"
          class="log-line"
          :style="{ height: `${lineHeight}px` }"
        >
          <span class="log-line__index" :style="{ minWidth: `${indexWidth}px` }">
            {{ item.index + 1 }}
          </span>
          <!-- 日志内容已经过 escapeHtml 处理，仅高亮时间戳/级别/关键词，允许 v-html -->
          <!-- eslint-disable-next-line vue/no-v-html -->
          <span class="log-line__content" v-html="highlightLine(item.line)" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

interface Props {
  lines: string[]
  lineHeight?: number
  keyword?: string
  paused?: boolean
  autoScroll?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  lineHeight: 20,
  keyword: '',
  paused: false,
  autoScroll: true,
})

const containerRef = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const containerHeight = ref(0)
const OVERSCAN = 5

const totalHeight = computed(() => props.lines.length * props.lineHeight)
const indexWidth = computed(() => String(props.lines.length).length * 8 + 16)

const startIndex = computed(() =>
  Math.max(0, Math.floor(scrollTop.value / props.lineHeight) - OVERSCAN)
)
const visibleCount = computed(
  () => Math.ceil(containerHeight.value / props.lineHeight) + OVERSCAN * 2
)
const endIndex = computed(() => Math.min(props.lines.length, startIndex.value + visibleCount.value))
const visibleItems = computed(() =>
  props.lines
    .slice(startIndex.value, endIndex.value)
    .map((line, i) => ({ index: startIndex.value + i, line }))
)
const groupOffset = computed(() => startIndex.value * props.lineHeight)

const onScroll = () => {
  if (!containerRef.value) return
  scrollTop.value = containerRef.value.scrollTop
  containerHeight.value = containerRef.value.clientHeight
}

const scrollToBottom = () => {
  const el = containerRef.value
  if (!el) return
  el.scrollTop = el.scrollHeight
  scrollTop.value = el.scrollTop
}

const scrollToTop = () => {
  const el = containerRef.value
  if (!el) return
  el.scrollTop = 0
  scrollTop.value = 0
}

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

const TIMESTAMP_RE = /\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(\.\d{1,6})?([+-]\d{2}:?\d{2}|Z)?/g
const LEVEL_RE = /\b(ERROR|FATAL|CRITICAL|SEVERE|WARN|WARNING|INFO|NOTICE|DEBUG|TRACE|VERBOSE)\b/gi

interface TokenRange {
  start: number
  end: number
  /** 优先级：0=timestamp, 1=level, 2=keyword（数值越小越优先） */
  priority: number
  wrap: (text: string) => string
}

/**
 * 收集所有匹配范围（timestamp、level、keyword），
 * 按优先级排序后去重叠，避免关键词高亮破坏已生成的 HTML 标签。
 */
const collectRanges = (escaped: string, keyword: string): TokenRange[] => {
  const ranges: TokenRange[] = []

  // 时间戳范围（优先级最高 = 0）
  let match: RegExpExecArray | null
  const tsRe = new RegExp(TIMESTAMP_RE.source, 'g')
  while ((match = tsRe.exec(escaped)) !== null) {
    ranges.push({
      start: match.index,
      end: match.index + match[0].length,
      priority: 0,
      wrap: text => `<span class="log-line__token log-line__token--timestamp">${text}</span>`,
    })
  }

  // 级别范围（优先级次高 = 1）
  const lvRe = new RegExp(LEVEL_RE.source, 'gi')
  while ((match = lvRe.exec(escaped)) !== null) {
    ranges.push({
      start: match.index,
      end: match.index + match[0].length,
      priority: 1,
      wrap: text => `<span class="log-line__token log-line__token--level">${text}</span>`,
    })
  }

  // 关键词范围（优先级最低 = 2）
  const kw = keyword.trim()
  if (kw) {
    const kwRe = new RegExp(escapeRegExp(kw), 'gi')
    while ((match = kwRe.exec(escaped)) !== null) {
      ranges.push({
        start: match.index,
        end: match.index + match[0].length,
        priority: 2,
        wrap: text => `<mark class="log-line__keyword">${text}</mark>`,
      })
    }
  }

  return ranges
}

/**
 * 按优先级排序并去重叠：
 * - timestamp(0) > level(1) > keyword(2)
 * - 重叠时保留优先级高的，裁剪优先级低的
 */
const mergeRanges = (ranges: TokenRange[]): TokenRange[] => {
  if (ranges.length === 0) return []

  // 按 start 升序，同 start 按 priority 升序
  const sorted = [...ranges].sort((a, b) => {
    if (a.start !== b.start) return a.start - b.start
    return a.priority - b.priority
  })

  const merged: TokenRange[] = [sorted[0]]

  for (let i = 1; i < sorted.length; i++) {
    const curr = sorted[i]
    const last = merged[merged.length - 1]

    if (curr.start >= last.end) {
      // 无重叠
      merged.push(curr)
    } else if (curr.end <= last.end) {
      // curr 完全被 last 覆盖，跳过
      continue
    } else {
      // 部分重叠
      if (curr.priority < last.priority) {
        // curr 优先级更高，截断 last
        last.end = curr.start
        merged.push(curr)
      } else {
        // last 优先级更高或相同，裁剪 curr
        curr.start = last.end
        if (curr.start < curr.end) {
          merged.push(curr)
        }
      }
    }
  }

  return merged
}

const highlightLine = (line: string): string => {
  const escaped = escapeHtml(line)
  const kw = props.keyword.trim()

  const ranges = collectRanges(escaped, kw)
  const merged = mergeRanges(ranges)

  if (merged.length === 0) return escaped

  // 按范围拼接 HTML
  let result = ''
  let pos = 0
  for (const r of merged) {
    if (r.start > pos) {
      result += escaped.slice(pos, r.start)
    }
    result += r.wrap(escaped.slice(r.start, r.end))
    pos = r.end
  }
  if (pos < escaped.length) {
    result += escaped.slice(pos)
  }

  return result
}

onMounted(() => {
  containerHeight.value = containerRef.value?.clientHeight ?? 0
})

watch(
  () => props.lines.length,
  (next, prev) => {
    if (next > prev && props.autoScroll && !props.paused) {
      requestAnimationFrame(scrollToBottom)
    }
  }
)

defineExpose({ scrollToBottom, scrollToTop })
</script>

<style scoped>
.log-line-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 0;
  border-radius: 0;
  background: transparent;
  font-family: var(--v6-font-mono);
  font-size: var(--v6-font-size-sm);
  line-height: 20px;
  scroll-behavior: auto;
}

.log-line-list__sizer {
  position: relative;
  width: 100%;
}

.log-line-list__viewport {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  will-change: transform;
}

.log-line {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  padding: 0 var(--v6-space-3);
  white-space: pre;
  box-sizing: border-box;
}

.log-line:nth-child(even) {
  background: rgb(0 0 0 / 2%);
}

.log-line__index {
  flex-shrink: 0;
  text-align: right;
  color: var(--v6-color-text-quaternary);
  user-select: none;
}

.log-line__content {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--v6-color-text);
}

.log-line__token--timestamp {
  color: var(--v6-color-info);
}

.log-line__token--level {
  font-weight: var(--v6-font-weight-semibold);
}

.log-line__keyword {
  background: var(--v6-color-warning-bg);
  color: var(--v6-color-text);
  border-radius: var(--v6-radius-xs);
  padding: 0 1px;
}

/* 深色模式 */
:global(.dark) .log-line:nth-child(even) {
  background: rgb(255 255 255 / 3%);
}

/* 低性能模式 / reduced-motion */
:root[data-perf-mode='low'] .log-line-list__viewport {
  will-change: auto;
}

@media (prefers-reduced-motion: reduce) {
  .log-line-list__viewport {
    will-change: auto;
  }
}
</style>
