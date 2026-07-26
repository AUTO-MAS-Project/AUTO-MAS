<template>
  <div class="script-split-view">
    <Section
      class="script-master-section"
      title="脚本"
      description="选择脚本后在右侧管理配置与用户"
      :padding="false"
    >
      <template #actions>
        <span class="script-count">{{ localScripts.length }}</span>
      </template>

      <draggable
        v-model="localScripts"
        item-key="id"
        :animation="200"
        :disabled="searchActive || isReorderingScripts"
        ghost-class="script-master-ghost"
        chosen-class="script-master-chosen"
        drag-class="script-master-drag"
        handle=".script-master-drag-handle"
        class="script-master-list"
        @start="onScriptDragStart"
        @end="onScriptDragEnd"
      >
        <template #item="{ element: script }">
          <button
            type="button"
            class="script-master-item"
            :class="{
              'script-master-item--selected': selectedScriptId === script.id,
              'script-master-item--match': isScriptSearchMatch(script.id),
              'script-master-item--unavailable': script.available === false,
              [`script-master-item--${statusKind(script)}`]: true,
            }"
            :aria-current="selectedScriptId === script.id ? 'page' : undefined"
            :title="statusLabel(script)"
            @click="selectScript(script.id)"
            @dblclick="emit('edit', script)"
          >
            <span
              class="script-master-drag-handle"
              :class="{ 'script-master-drag-handle--disabled': searchActive }"
              :title="searchActive ? '搜索期间暂停拖拽排序' : '拖拽排序'"
              aria-label="拖拽排序"
              :aria-disabled="searchActive"
              @click.stop
            >
              <MenuOutlined />
            </span>
            <span class="script-master-icon">
              <img
                class="script-master-icon-image"
                :src="getScriptIcon(script.type, script.iconUrl)"
                :alt="`${script.displayName || script.type} 图标`"
                @error="event => handleScriptIconError(event, script.type)"
              />
            </span>
            <span class="script-master-name">{{ script.name }}</span>
            <span class="script-master-meta">{{ script.users.length }} 位用户</span>
            <span
              class="script-status-dot"
              :class="`dot-${statusKind(script)}`"
              :aria-label="statusLabel(script)"
            />
          </button>
        </template>
      </draggable>
    </Section>

    <div class="script-detail-pane">
      <ScriptCard
        v-if="selectedScript"
        ref="scriptCardRef"
        class="script-detail-card"
        :script="selectedScript"
        :active-connections="activeConnections"
        :copying-script-id="copyingScriptId"
        :search-active="searchActive"
        :normalized-search-keyword="normalizedSearchKeyword"
        :active-search-match-key="activeSearchMatchKey ?? ''"
        :collapsed="collapsedScriptIds.has(selectedScriptId)"
        :register-match-element="setSearchMatchElement"
        @edit="emit('edit', $event)"
        @delete="emit('delete', $event)"
        @copy="emit('copy', $event)"
        @add-user="emit('addUser', $event)"
        @edit-user="emit('editUser', $event)"
        @delete-user="emit('deleteUser', $event)"
        @start-src-config="emit('startSrcConfig', $event)"
        @start-maa-end-config="emit('startMaaEndConfig', $event)"
        @toggle-user-status="emit('toggleUserStatus', $event)"
        @pass-check-user="emit('passCheckUser', $event)"
        @toggle-collapsed="toggleUsersCollapsed(selectedScriptId)"
        @user-reorder="onUserReorder"
      />

      <StatePanel v-else type="neutral" title="选择一个脚本">
        从左侧列表选择脚本，以查看配置和用户。
      </StatePanel>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { MenuOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import type { Script, User } from '@/types/script'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import Section from '@/components/mac/Section.vue'
import StatePanel from '@/components/mac/StatePanel.vue'
import { getScriptIcon, handleScriptIconError } from '@/utils/scriptRegistry'
import {
  getScriptSearchMatchKey,
  getUserSearchMatchKey,
  normalizeScriptSearchQuery,
} from '@/views/scripts/scriptPageSearch'
import { isSameOrder, restoreItemOrder } from '@/views/scripts/reorderHelpers'
import ScriptCard from './ScriptCard.vue'

interface Props {
  scripts: Script[]
  activeConnections: Map<string, { subscriptionId: string; websocketId: string }>
  copyingScriptId?: string | null
  allPlansData?: Record<string, Record<string, unknown>>
  searchKeyword?: string
  activeSearchMatchKey?: string
}

interface Emits {
  (e: 'edit', script: Script): void
  (e: 'delete', script: Script): void
  (e: 'copy', script: Script): void
  (e: 'addUser', script: Script): void
  (e: 'editUser', user: User): void
  (e: 'deleteUser', user: User): void
  (e: 'startSrcConfig', script: Script): void
  (e: 'startMaaEndConfig', script: Script): void
  (e: 'toggleUserStatus', user: User): void
  (e: 'passCheckUser', user: User): void
  (e: 'scriptsReordered', scripts: Script[]): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const registryApi = useScriptRegistryApi()

const localScripts = ref<Script[]>([])
const selectedScriptId = ref('')
const normalizedSearchKeyword = computed(() =>
  normalizeScriptSearchQuery(props.searchKeyword ?? '')
)
const searchActive = computed(() => normalizedSearchKeyword.value.length > 0)
const selectedScript = computed(
  () => localScripts.value.find(script => script.id === selectedScriptId.value) ?? null
)

// 脚本运行状态分类：基于真实的活动连接与可用性，不引入假数据。
// - running：配置会话活动中（activeConnections 命中）
// - error：脚本类型未启用（available === false）
// - stopped：可用且当前无活动连接
type ScriptStatusKind = 'running' | 'stopped' | 'error'

const statusKind = (script: Script): ScriptStatusKind => {
  if (script.available === false) return 'error'
  if (props.activeConnections.has(script.id)) return 'running'
  return 'stopped'
}

const statusLabel = (script: Script): string => {
  switch (statusKind(script)) {
    case 'error':
      return script.unavailableReason || '未启用'
    case 'running':
      return '配置中'
    default:
      return '空闲'
  }
}

const isDraggingScripts = ref(false)
const isReorderingScripts = ref(false)
const scriptOrderBeforeDrag = ref<string[]>([])
const isReorderingUsers = ref<Record<string, boolean>>({})
const scriptCardRef = ref<InstanceType<typeof ScriptCard> | null>(null)

const COLLAPSED_SCRIPTS_STORAGE_KEY = 'scripts.collapsedScriptIds'

const loadCollapsedScriptIds = (): Set<string> => {
  try {
    const raw = localStorage.getItem(COLLAPSED_SCRIPTS_STORAGE_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw) as unknown
    return new Set(
      Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : []
    )
  } catch {
    return new Set()
  }
}

const collapsedScriptIds = ref<Set<string>>(loadCollapsedScriptIds())

const saveCollapsedScriptIds = () => {
  try {
    localStorage.setItem(
      COLLAPSED_SCRIPTS_STORAGE_KEY,
      JSON.stringify([...collapsedScriptIds.value])
    )
  } catch {
    // Storage is an optional persistence enhancement; in-memory state remains available.
  }
}

const selectScript = (scriptId: string) => {
  selectedScriptId.value = scriptId
}

const toggleUsersCollapsed = (scriptId: string) => {
  const next = new Set(collapsedScriptIds.value)
  if (next.has(scriptId)) {
    next.delete(scriptId)
  } else {
    next.add(scriptId)
  }
  collapsedScriptIds.value = next
  saveCollapsedScriptIds()
}

const collapseAllUsers = () => {
  collapsedScriptIds.value = new Set(localScripts.value.map(script => script.id))
  saveCollapsedScriptIds()
}

const expandAllUsers = () => {
  collapsedScriptIds.value = new Set()
  saveCollapsedScriptIds()
}

const searchMatchElements = new Map<string, HTMLElement>()

const setSearchMatchElement = (key: string, element: unknown) => {
  if (element instanceof HTMLElement) {
    searchMatchElements.set(key, element)
  } else {
    searchMatchElements.delete(key)
  }
}

const findScriptIdForMatch = (key: string) =>
  localScripts.value.find(
    script =>
      key === getScriptSearchMatchKey(script.id) ||
      script.users.some(user => key === getUserSearchMatchKey(script.id, user.id))
  )?.id ?? ''

const isScriptSearchMatch = (scriptId: string) => {
  const key = props.activeSearchMatchKey ?? ''
  if (!key) return false
  return (
    key === getScriptSearchMatchKey(scriptId) ||
    localScripts.value
      .find(script => script.id === scriptId)
      ?.users.some(user => key === getUserSearchMatchKey(scriptId, user.id)) === true
  )
}

const scrollToSearchMatch = (key: string) => {
  const scriptId = findScriptIdForMatch(key)
  if (scriptId) selectedScriptId.value = scriptId
  void nextTick(() => {
    const element = searchMatchElements.get(key)
    if (!element?.isConnected) return
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    element.scrollIntoView({
      behavior: reduceMotion ? 'auto' : 'smooth',
      block: 'nearest',
    })
  })
}

defineExpose({ collapseAllUsers, expandAllUsers, scrollToSearchMatch })

watch(
  () => props.scripts,
  newScripts => {
    if (isDraggingScripts.value || isReorderingScripts.value) return
    localScripts.value = [...newScripts]
    if (!newScripts.some(script => script.id === selectedScriptId.value)) {
      selectedScriptId.value = newScripts[0]?.id ?? ''
    }
  },
  { immediate: true, deep: true }
)

watch(
  () => props.activeSearchMatchKey,
  key => {
    if (!key) return
    const scriptId = findScriptIdForMatch(key)
    if (scriptId) selectedScriptId.value = scriptId
  },
  { immediate: true }
)

const restoreScriptOrder = () => {
  localScripts.value = restoreItemOrder(scriptOrderBeforeDrag.value, props.scripts)
}

const onScriptDragStart = () => {
  if (searchActive.value || isReorderingScripts.value) return
  isDraggingScripts.value = true
  scriptOrderBeforeDrag.value = localScripts.value.map(script => script.id)
}

const onScriptDragEnd = async () => {
  if (!isDraggingScripts.value || isReorderingScripts.value) return
  isDraggingScripts.value = false
  const scriptIds = localScripts.value.map(script => script.id)
  const previousIds = scriptOrderBeforeDrag.value
  if (isSameOrder(scriptIds, previousIds)) {
    localScripts.value = [...props.scripts]
    scriptOrderBeforeDrag.value = []
    return
  }

  isReorderingScripts.value = true
  try {
    await registryApi.reorderScripts(scriptIds)
    localScripts.value = restoreItemOrder(scriptIds, props.scripts)
    emit('scriptsReordered', localScripts.value)
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    message.error(`脚本排序失败: ${errorMessage}`)
    restoreScriptOrder()
  } finally {
    isReorderingScripts.value = false
    scriptOrderBeforeDrag.value = []
  }
}

const restoreUserOrder = (scriptId: string, previousUserIds: string[]) => {
  const script = localScripts.value.find(item => item.id === scriptId)
  if (!script) return
  script.users = restoreItemOrder(previousUserIds, script.users)
}

const onUserReorder = async (scriptId: string, userIds: string[], previousUserIds: string[]) => {
  if (isReorderingUsers.value[scriptId]) return
  const script = localScripts.value.find(item => item.id === scriptId)
  if (!script) return
  if (isSameOrder(userIds, previousUserIds)) {
    scriptCardRef.value?.finishUserReorder(true)
    return
  }

  isReorderingUsers.value = { ...isReorderingUsers.value, [scriptId]: true }
  try {
    await registryApi.reorderUsers(scriptId, userIds)
    script.users = restoreItemOrder(userIds, script.users)
    scriptCardRef.value?.finishUserReorder(true)
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    message.error(`用户排序失败: ${errorMessage}`)
    restoreUserOrder(scriptId, previousUserIds)
    scriptCardRef.value?.finishUserReorder(false)
  } finally {
    const next = { ...isReorderingUsers.value }
    delete next[scriptId]
    isReorderingUsers.value = next
  }
}
</script>

<style scoped>
.script-split-view {
  container: script-split / inline-size;
  display: grid;
  flex: 1;
  grid-template-columns: minmax(260px, 300px) minmax(0, 1fr);
  align-items: stretch;
  gap: var(--v6-space-4);
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.script-master-section {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
}

.script-master-section :deep(.mac-section__content-wrapper) {
  flex: 1;
  min-height: 0;
}

.script-master-section :deep(.mac-section__content) {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
}

.script-count {
  min-width: 22px;
  padding: var(--v6-space-0-5) var(--v6-space-2);
  border-radius: var(--v6-radius-full);
  background: var(--v6-vibrancy-hover);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-xs);
  font-variant-numeric: tabular-nums;
  text-align: center;
}

/* ── Master list (NSTableView 风格) ── */
.script-master-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  padding: var(--v6-space-1) 0;
  overflow: auto;
}

.script-master-item {
  display: flex;
  align-items: center;
  width: 100%;
  height: 44px;
  gap: var(--v6-space-2);
  padding: 0 var(--v6-space-3) 0 var(--v6-space-2);
  border: none;
  border-bottom: 1px solid var(--v6-color-border-subtle);
  border-radius: 0;
  background: transparent;
  color: var(--v6-color-text);
  font: inherit;
  text-align: left;
  cursor: default;
  transition: background-color var(--v6-motion-fast) var(--v6-ease-out);
}

/* 交替行背景，模拟 NSTableView alternating rows */
.script-master-item:nth-child(even) {
  background: var(--v6-color-border-subtle);
}

.script-master-item:hover {
  background: var(--v6-vibrancy-hover);
}

.script-master-item:focus-visible {
  outline: none;
  box-shadow: var(--v6-focus-ring);
}

/* 选中行：蓝色半透明背景，文字保持深色（不反白） */
.script-master-item--selected,
.script-master-item--selected:hover {
  background: var(--v6-vibrancy-selected);
}

.script-master-item--match {
  box-shadow: inset 3px 0 0 var(--v6-color-info);
}

.script-master-item--unavailable {
  color: var(--v6-color-text-secondary);
}

.script-master-item--error .script-master-name {
  color: var(--v6-color-text-secondary);
}

.script-master-drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 28px;
  flex-shrink: 0;
  border-radius: var(--v6-radius-sm);
  color: var(--v6-color-text-tertiary);
  cursor: grab;
  opacity: 0.55;
  transition:
    color var(--v6-motion-fast) var(--v6-ease-out),
    opacity var(--v6-motion-fast) var(--v6-ease-out);
}

.script-master-item:hover .script-master-drag-handle {
  color: var(--v6-color-text-secondary);
  opacity: 1;
}

.script-master-drag-handle:active {
  cursor: grabbing;
}

.script-master-drag-handle--disabled {
  cursor: not-allowed;
  opacity: 0.3;
}

.script-master-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-sm);
  background: var(--v6-color-window);
  overflow: hidden;
}

.script-master-icon img {
  width: 18px;
  height: 18px;
  object-fit: contain;
}

.script-master-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
  font-weight: var(--v6-font-weight-medium);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.script-master-meta {
  flex-shrink: 0;
  color: var(--v6-color-text-tertiary);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* 状态圆点：7px，运行中带 pulse 动效 */
.script-status-dot {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--v6-color-text-quaternary);
}

.script-status-dot.dot-running {
  background: var(--v6-color-success);
  box-shadow: 0 0 0 0 var(--v6-color-success-bg);
  animation: script-status-pulse 2s ease-in-out infinite;
}

.script-status-dot.dot-stopped {
  background: var(--v6-color-text-quaternary);
}

.script-status-dot.dot-error {
  background: var(--v6-color-error);
}

@keyframes script-status-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 var(--v6-color-success-bg);
  }
  50% {
    box-shadow: 0 0 0 4px transparent;
  }
}

/* ── Detail pane ── */
.script-detail-pane {
  display: flex;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.script-detail-card {
  flex: 1;
  min-width: 0;
}

/* 详情卡片作为单卡片 box（不再嵌套于 Section），保持自身卡片样式 */
.script-detail-pane :deep(.script-wrapper) {
  height: 100%;
}

.script-master-ghost {
  opacity: 0;
}

.script-master-chosen,
.script-master-drag {
  cursor: grabbing;
}

.script-master-drag {
  box-shadow: var(--v6-shadow-elevated);
}

:root[data-perf-mode='low'] .script-master-item {
  transition: none;
}

:root[data-perf-mode='low'] .script-status-dot.dot-running {
  animation: none;
}

@media (prefers-reduced-motion: reduce) {
  .script-master-item {
    transition: none;
  }

  .script-status-dot.dot-running {
    animation: none;
  }
}

/* 窄容器降级:@container 只作用于容器的后代,不能命中声明容器的元素自身,
   因此用外层 Scripts.vue 根元素声明的 scripts-page 容器来驱动本组件根的单列布局 */
@container scripts-page (max-width: 900px) {
  .script-split-view {
    grid-template-columns: 1fr;
    grid-template-rows: repeat(2, minmax(0, 1fr));
  }
}
</style>
