<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { BookOutlined } from '@ant-design/icons-vue'
import splitDocRaw from './docs/split-doc.md?raw'
import regexDocRaw from './docs/regex-doc.md?raw'
import expressionDocRaw from './docs/expression-doc.md?raw'
import multilineDocRaw from './docs/multiline-doc.md?raw'

type DocKey = 'split' | 'regex' | 'expression' | 'multiline'

interface Props {
  open: boolean
  activeKey?: DocKey
}
const props = withDefaults(defineProps<Props>(), { activeKey: 'regex' })
const emit = defineEmits<{
  'update:open': [value: boolean]
  'update:activeKey': [value: DocKey]
}>()

const open = computed({
  get: () => props.open,
  set: (v: boolean) => emit('update:open', v),
})
const activeKey = computed({
  get: () => props.activeKey,
  set: (v: DocKey) => emit('update:activeKey', v),
})

// ==================== Markdown 渲染器 ====================
// 给标题加 id（供左侧目录点击跳转）；未登记 SYNTAX 不会在这里处理
const slugify = (s: string): string => {
  return s
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, '')
    .replace(/\s+/g, '-')
}

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
})

md.renderer.rules.heading_open = (tokens, idx, options, _env, self) => {
  const token = tokens[idx]
  const next = tokens[idx + 1]
  let title = ''
  if (next && next.type === 'inline') {
    title = next.content
  }
  if (title) {
    token.attrSet('id', slugify(title))
  }
  return self.renderToken(tokens, idx, options)
}

// ==================== 文档源 ====================
const DOC_SOURCE: Record<DocKey, string> = {
  split: splitDocRaw,
  regex: regexDocRaw,
  expression: expressionDocRaw,
  multiline: multilineDocRaw,
}

// ==================== 目录解析 ====================
interface TocItem {
  level: number
  title: string
  id: string
}

const parseToc = (src: string): TocItem[] => {
  const items: TocItem[] = []
  const lines = src.split('\n')
  let inCodeBlock = false
  for (const line of lines) {
    if (/^```/.test(line.trim())) {
      inCodeBlock = !inCodeBlock
      continue
    }
    if (inCodeBlock) continue
    const m = /^(#{1,3})\s+(.+)$/.exec(line)
    if (m) {
      const title = m[2].trim()
      // 跳过文档主标题（H1），目录只收 H2/H3
      if (m[1].length === 1) continue
      items.push({
        level: m[1].length,
        title,
        id: slugify(title),
      })
    }
  }
  return items
}

// ==================== 渲染内容与目录 ====================
const renderedHtml = computed(() => md.render(DOC_SOURCE[activeKey.value]))
const tocItems = computed(() => parseToc(DOC_SOURCE[activeKey.value]))

const contentRef = ref<HTMLDivElement | null>(null)
const activeAnchor = ref('')

const scrollToHeading = (id: string) => {
  activeAnchor.value = id
  nextTick(() => {
    const container = contentRef.value
    if (!container) return
    const el = container.querySelector(`[id="${id}"]`) as HTMLElement | null
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  })
}

// 切换 Tab 时重置滚动与高亮
watch(activeKey, () => {
  activeAnchor.value = ''
  nextTick(() => {
    if (contentRef.value) {
      contentRef.value.scrollTop = 0
    }
  })
})

// 弹窗打开时默认滚动到顶部
watch(
  () => props.open,
  v => {
    if (v) {
      activeAnchor.value = ''
      nextTick(() => {
        if (contentRef.value) {
          contentRef.value.scrollTop = 0
        }
      })
    }
  }
)
</script>

<template>
  <a-modal
    v-model:open="open"
    title="日志提取表达式参考"
    width="1000px"
    :footer="null"
    :destroy-on-close="false"
    wrap-class-name="log-pattern-docs-modal"
  >
    <template #title>
      <span class="modal-title">
        <BookOutlined />
        日志提取表达式参考
      </span>
    </template>

    <a-tabs v-model:active-key="activeKey" size="small" class="docs-tabs">
      <a-tab-pane key="split" tab="字符串切割指南" />
      <a-tab-pane key="regex" tab="正则指南" />
      <a-tab-pane key="expression" tab="表达式指南" />
      <a-tab-pane key="multiline" tab="多行聚合指南" />
    </a-tabs>

    <div class="docs-body">
      <aside class="docs-toc">
        <div class="docs-toc-title">目录</div>
        <ul class="docs-toc-list">
          <li
            v-for="item in tocItems"
            :key="item.id"
            :class="['docs-toc-item', `level-${item.level}`, { active: activeAnchor === item.id }]"
            @click="scrollToHeading(item.id)"
          >
            {{ item.title }}
          </li>
        </ul>
      </aside>
      <div ref="contentRef" class="docs-content markdown-content" v-html="renderedHtml"></div>
    </div>
  </a-modal>
</template>

<style scoped>
.modal-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.log-pattern-docs-modal :deep(.ant-modal-body) {
  padding: 0 16px 16px;
}

.docs-tabs {
  margin-bottom: 8px;
}

.docs-body {
  display: flex;
  gap: 16px;
  height: 65vh;
  min-height: 400px;
}

.docs-toc {
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--ant-color-border-secondary);
  padding-right: 12px;
  overflow-y: auto;
}

.docs-toc-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
  margin-bottom: 8px;
  padding-left: 4px;
}

.docs-toc-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.docs-toc-item {
  font-size: 12.5px;
  line-height: 1.5;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  color: var(--ant-color-text-secondary);
  transition: all 0.15s ease;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.docs-toc-item:hover {
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-primary);
}

.docs-toc-item.active {
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 500;
}

.docs-toc-item.level-3 {
  padding-left: 20px;
  font-size: 12px;
}

.docs-content {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 4px 8px 4px 12px;
}

/* ==================== Markdown 内容样式 ==================== */
.markdown-content :deep(h1) {
  font-size: 22px;
  font-weight: 600;
  margin: 8px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  color: var(--ant-color-text);
}

.markdown-content :deep(h2) {
  font-size: 17px;
  font-weight: 600;
  margin: 22px 0 10px;
  color: var(--ant-color-text);
  scroll-margin-top: 12px;
}

.markdown-content :deep(h3) {
  font-size: 14px;
  font-weight: 600;
  margin: 16px 0 8px;
  color: var(--ant-color-text);
  scroll-margin-top: 12px;
}

.markdown-content :deep(p) {
  font-size: 13px;
  line-height: 1.7;
  color: var(--ant-color-text);
  margin: 6px 0;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  font-size: 13px;
  line-height: 1.7;
  color: var(--ant-color-text);
  padding-left: 22px;
  margin: 6px 0;
}

.markdown-content :deep(li) {
  margin: 2px 0;
}

.markdown-content :deep(strong) {
  font-weight: 600;
  color: var(--ant-color-text);
}

.markdown-content :deep(code) {
  padding: 1px 6px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 4px;
  font-family:
    ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New',
    monospace;
  font-size: 12px;
  color: var(--ant-color-primary);
}

.markdown-content :deep(pre) {
  margin: 8px 0;
  padding: 10px 14px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 6px;
  overflow-x: auto;
}

.markdown-content :deep(pre code) {
  padding: 0;
  background: transparent;
  color: var(--ant-color-text);
  font-size: 12px;
  line-height: 1.6;
}

.markdown-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 12.5px;
}

.markdown-content :deep(th),
.markdown-content :deep(td) {
  border: 1px solid var(--ant-color-border-secondary);
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
}

.markdown-content :deep(th) {
  background: var(--ant-color-fill-quaternary);
  font-weight: 600;
  color: var(--ant-color-text);
}

.markdown-content :deep(td) {
  color: var(--ant-color-text);
}

.markdown-content :deep(td code),
.markdown-content :deep(th code) {
  white-space: nowrap;
}

.markdown-content :deep(a) {
  color: var(--ant-color-primary);
  text-decoration: none;
}

.markdown-content :deep(a:hover) {
  text-decoration: underline;
}

.markdown-content :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--ant-color-primary);
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text-secondary);
  font-size: 12.5px;
}

.markdown-content :deep(hr) {
  border: none;
  border-top: 1px solid var(--ant-color-border-secondary);
  margin: 16px 0;
}

/* 暗色模式适配 */
@media (prefers-color-scheme: dark) {
  .docs-toc {
    border-right-color: var(--ant-color-border);
  }
}
</style>
