<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { SearchOutlined } from '@ant-design/icons-vue'
import { useRouteLock } from '@/composables/useRouteLock.ts'
import { OpenAPI } from '@/api'
import { authenticatedApiFetch } from '@/utils/httpSecurity'
import type { PageDeclaration } from '@/router/pageDeclarations.ts'
import {
  buildGlobalSearchGroups,
  createGlobalSearchSession,
  type GlobalSearchItem,
  type PluginInstanceLike,
} from './globalSearch.ts'

const props = defineProps<{
  pages: PageDeclaration[]
  collapsed: boolean
}>()

const emit = defineEmits<{
  /** 保留原有脚本搜索链路：由 AppSider → AppLayout 跳转 /scripts */
  (e: 'search', keyword: string): void
}>()

const logger = window.electronAPI?.getLogger?.('全局搜索')

const router = useRouter()
const { isRouteLocked, triggerBlockCallback } = useRouteLock()

// 搜索会话状态机（globalSearch.ts，含「跳转后再搜索」自愈逻辑与单元测试）
const session = createGlobalSearchSession({ isCollapsed: () => props.collapsed })
const { keyword, activeIndex, popoverOpen, inlineExpanded, hasKeyword, inlinePanelOpen } = session
const searchInputRef = ref<{ focus?: () => void; blur?: () => void } | null>(null)

// ---- 插件实例数据源：面板打开时按需拉取 ----
const pluginInstances = ref<PluginInstanceLike[]>([])

const toBackendUrl = (path: string) => {
  const base = (OpenAPI.BASE || 'http://127.0.0.1:36163').replace(/\/+$/, '')
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

const refreshPluginInstances = async () => {
  try {
    const response = await authenticatedApiFetch(toBackendUrl('/api/plugins/get'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    })
    const payload = (await response.json()) as {
      code?: number
      message?: string
      instances?: Array<{ id?: string; name?: string; plugin?: string }>
    }
    if (!response.ok || (payload.code !== undefined && payload.code !== 200)) {
      throw new Error(payload.message || `HTTP ${response.status}`)
    }
    if (Array.isArray(payload.instances)) {
      pluginInstances.value = payload.instances
        .filter(item => Boolean(item) && typeof item === 'object')
        .map(item => ({
          id: String(item.id || ''),
          name: String(item.name || item.id || ''),
          plugin: String(item.plugin || ''),
        }))
        .filter(item => item.id && item.name)
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    logger?.warn(`全局搜索加载插件实例失败: ${message}`)
  }
}

// ---- 结果构建 ----
const groups = computed(() =>
  buildGlobalSearchGroups(keyword.value, props.pages, pluginInstances.value)
)
const flatItems = computed(() => groups.value.flatMap(group => group.items))
const flatIndexOf = (item: GlobalSearchItem) =>
  flatItems.value.findIndex(candidate => candidate.key === item.key)

watch(popoverOpen, open => {
  if (open) {
    void refreshPluginInstances()
  } else {
    keyword.value = ''
  }
})

// 侧栏收起时一并收回临时搜索框；再次展开仍保持干净的导航层级
watch(
  () => props.collapsed,
  collapsed => session.handleCollapsedChange(collapsed)
)

// ---- 打开 / 关闭 ----
const openInlineSearch = async () => {
  session.openInline()
  void refreshPluginInstances()
  await nextTick()
  searchInputRef.value?.focus?.()
}

const handleInlineFocus = () => {
  session.focusInline()
}

const handleInlineBlur = () => {
  // 结果项 mousedown.prevent 保持输入框焦点，真正点击外部时才会触发 blur
  session.blurInline()
}

// ---- 激活条目 ----
const activateItem = (item: GlobalSearchItem) => {
  const searchKeyword = keyword.value.trim()
  // 整体结束本次搜索会话：收回输入框、清空关键字，
  // 避免残留的焦点标志位让下一次搜索打不开结果面板
  session.reset()
  if (item.key.startsWith('scripts:')) {
    emit('search', searchKeyword)
    return
  }
  if (isRouteLocked.value) {
    triggerBlockCallback(item.target.path)
    return
  }
  void router.push({ path: item.target.path, query: item.target.query })
}

const submitDefault = () => {
  // Enter 未选中条目时保留原有行为：跳转脚本管理搜索
  const activeItem = activeIndex.value >= 0 ? flatItems.value[activeIndex.value] : undefined
  if (activeItem) {
    activateItem(activeItem)
    return
  }
  const searchKeyword = keyword.value.trim()
  session.reset()
  emit('search', searchKeyword)
}

const handleKeydown = (event: KeyboardEvent) => {
  const total = flatItems.value.length
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (total > 0) activeIndex.value = (activeIndex.value + 1) % total
    return
  }
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (total > 0) activeIndex.value = (activeIndex.value - 1 + total) % total
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    session.reset()
  }
}
</script>

<template>
  <div class="global-search" :class="{ 'global-search--collapsed': collapsed }">
    <!-- 折叠态：图标按钮 + 右侧弹层（输入框与结果同层） -->
    <a-popover
      v-if="collapsed"
      v-model:open="popoverOpen"
      placement="rightTop"
      trigger="click"
      overlay-class-name="global-search-popover"
    >
      <button
        type="button"
        class="global-search-tool-button"
        aria-label="全局搜索"
        title="全局搜索"
      >
        <SearchOutlined aria-hidden="true" />
      </button>
      <template #content>
        <div class="global-search-panel">
          <a-input
            v-model:value="keyword"
            class="global-search-popover__input"
            allow-clear
            autofocus
            placeholder="全局搜索…"
            aria-label="全局搜索"
            @press-enter="submitDefault"
            @keydown="handleKeydown"
          >
            <template #prefix><SearchOutlined aria-hidden="true" /></template>
          </a-input>
          <div v-if="hasKeyword" class="global-search-results" role="listbox" aria-label="搜索结果">
            <template v-for="group in groups" :key="group.key">
              <div class="global-search-group-label">{{ group.label }}</div>
              <button
                v-for="item in group.items"
                :key="item.key"
                type="button"
                role="option"
                class="global-search-item"
                :class="{ 'global-search-item--active': flatIndexOf(item) === activeIndex }"
                :aria-selected="flatIndexOf(item) === activeIndex"
                @mousedown.prevent
                @click="activateItem(item)"
              >
                <span class="global-search-item__label">{{ item.label }}</span>
                <span v-if="item.note" class="global-search-item__note">{{ item.note }}</span>
              </button>
            </template>
          </div>
        </div>
      </template>
    </a-popover>

    <!-- 展开态：点击展开内联输入框，结果经弹层浮出（避免被侧栏裁剪） -->
    <template v-else>
      <button
        v-if="!inlineExpanded"
        type="button"
        class="global-search-tool-button global-search-trigger"
        aria-label="全局搜索"
        title="全局搜索"
        @click="openInlineSearch"
      >
        <SearchOutlined aria-hidden="true" />
      </button>
      <a-popover
        v-else
        :open="inlinePanelOpen"
        placement="rightTop"
        overlay-class-name="global-search-popover"
      >
        <a-input
          ref="searchInputRef"
          v-model:value="keyword"
          class="global-search-input"
          allow-clear
          placeholder="全局搜索…"
          aria-label="全局搜索"
          @press-enter="submitDefault"
          @keydown="handleKeydown"
          @focus="handleInlineFocus"
          @blur="handleInlineBlur"
        >
          <template #prefix><SearchOutlined aria-hidden="true" /></template>
        </a-input>
        <template #content>
          <div
            class="global-search-panel global-search-results"
            role="listbox"
            aria-label="搜索结果"
          >
            <template v-for="group in groups" :key="group.key">
              <div class="global-search-group-label">{{ group.label }}</div>
              <button
                v-for="item in group.items"
                :key="item.key"
                type="button"
                role="option"
                class="global-search-item"
                :class="{ 'global-search-item--active': flatIndexOf(item) === activeIndex }"
                :aria-selected="flatIndexOf(item) === activeIndex"
                @mousedown.prevent
                @click="activateItem(item)"
              >
                <span class="global-search-item__label">{{ item.label }}</span>
                <span v-if="item.note" class="global-search-item__note">{{ item.note }}</span>
              </button>
            </template>
          </div>
        </template>
      </a-popover>
    </template>
  </div>
</template>

<style scoped>
/*
 * 布局契约（与 AppSider / AppSiderMenu 的行几何完全同构，锁定折叠动画稳定性）：
 * 行高固定 40px；图标固定 20px 列居中（18px 字形）；两态 padding 相同（0 10px）；
 * 纵向布局属性（height/padding/margin）一律不参与 transition。
 */
.global-search {
  width: 100%;
  height: 40px;
  display: flex;
  align-items: center;
}

.global-search-tool-button {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  width: 100%;
  height: 40px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: var(--v6-radius-control);
  background: transparent;
  color: var(--ant-color-text-secondary);
  font: inherit;
  cursor: pointer;
  overflow: hidden;
  white-space: nowrap;
  -webkit-app-region: no-drag;
}

/* 图标固定列宽：两态图标 x 位置不漂移 */
.global-search-tool-button :deep(.anticon) {
  flex: 0 0 20px;
  width: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  line-height: 1;
}

.global-search-tool-button:hover {
  color: var(--ant-color-text);
  background: var(--v6-vibrancy-hover);
}

.global-search-tool-button:focus-visible {
  outline: none;
  box-shadow: var(--v6-focus-ring-inset);
}

.global-search-trigger {
  width: 100%;
}

.global-search-input {
  width: 100%;
  animation: global-search-reveal var(--v6-motion-base) var(--v6-ease-out);
}

.global-search-input :deep(.ant-input-affix-wrapper),
:deep(.global-search-input.ant-input-affix-wrapper) {
  min-height: 36px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: color-mix(in srgb, var(--v6-color-text) 5%, transparent);
  box-shadow: none;
}

:deep(.global-search-input.ant-input-affix-wrapper .ant-input) {
  background: transparent;
  font-size: 13px;
}

@keyframes global-search-reveal {
  from {
    opacity: 0;
    transform: translateY(-3px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .global-search-input {
    animation: none;
  }
}

:global(:root[data-perf-mode='low']) .global-search-input {
  animation: none;
}
</style>

<style>
/* 弹层挂载于 body，需用非 scoped 样式（沿用 mac 风格 elevated surface token） */
.global-search-popover .ant-popover-inner {
  padding: 8px;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: 12px;
  background: var(--v6-color-surface-elevated);
  box-shadow: var(--v6-shadow-elevated);
}

.global-search-popover__input {
  width: 260px;
}

.global-search-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 260px;
}

.global-search-results {
  max-height: 320px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.global-search-group-label {
  padding: 6px 8px 2px;
  font-size: var(--v6-font-size-xs);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text-tertiary);
  letter-spacing: 0.02em;
  user-select: none;
  -webkit-user-select: none;
}

.global-search-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: var(--v6-radius-control);
  background: transparent;
  color: var(--ant-color-text);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.global-search-item:hover,
.global-search-item--active {
  background: var(--v6-vibrancy-hover);
}

.global-search-item:focus-visible {
  outline: none;
  box-shadow: var(--v6-focus-ring-inset);
}

.global-search-item__label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-search-item__note {
  flex-shrink: 0;
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-tertiary);
}
</style>
