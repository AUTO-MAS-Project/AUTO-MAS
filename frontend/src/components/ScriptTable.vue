<template>
  <div class="scripts-grid">
    <draggable
      v-model="localScripts"
      item-key="id"
      :animation="200"
      :disabled="searchActive || isReorderingScripts"
      ghost-class="script-ghost"
      chosen-class="script-chosen"
      drag-class="script-drag"
      handle=".script-drag-handle"
      class="draggable-scripts"
      @start="onScriptDragStart"
      @end="onScriptDragEnd"
    >
      <template #item="{ element: script }">
        <ScriptCard
          :ref="el => setScriptCardRef(script.id, el)"
          :script="script"
          :active-connections="activeConnections"
          :copying-script-id="copyingScriptId"
          :search-active="searchActive"
          :normalized-search-keyword="normalizedSearchKeyword"
          :active-search-match-key="activeSearchMatchKey ?? ''"
          :collapsed="collapsedScriptIds.has(script.id)"
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
          @toggle-collapsed="toggleUsersCollapsed(script.id)"
          @user-reorder="onUserReorder"
        />
      </template>
    </draggable>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import draggable from 'vuedraggable'
import type { Script, User } from '@/types/script'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { normalizeScriptSearchQuery } from '@/views/scripts/scriptPageSearch'
import { isSameOrder, restoreItemOrder } from '@/views/scripts/reorderHelpers'
import ScriptCard from '@/views/scripts/components/ScriptCard.vue'

interface Props {
  scripts: Script[]
  activeConnections: Map<string, { subscriptionId: string; websocketId: string }>
  copyingScriptId?: string | null
  allPlansData?: Record<string, Record<string, any>>
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
const normalizedSearchKeyword = computed(() =>
  normalizeScriptSearchQuery(props.searchKeyword ?? '')
)
const searchActive = computed(() => normalizedSearchKeyword.value.length > 0)

// 拖拽排序状态：保存排序前快照，用于失败回滚；并发/刷新时保护本地状态
const isDraggingScripts = ref(false)
const isReorderingScripts = ref(false)
const scriptOrderBeforeDrag = ref<string[]>([])
const isReorderingUsers = ref<Record<string, boolean>>({})
const scriptCardRefs = ref<Map<string, InstanceType<typeof ScriptCard>>>(new Map())

const setScriptCardRef = (scriptId: string, el: unknown) => {
  if (el) {
    scriptCardRefs.value.set(scriptId, el as InstanceType<typeof ScriptCard>)
  } else {
    scriptCardRefs.value.delete(scriptId)
  }
}

// 脚本用户列表收起状态 - 持久化到 localStorage，切换页面后仍保持
const COLLAPSED_SCRIPTS_STORAGE_KEY = 'scripts.collapsedScriptIds'

const loadCollapsedScriptIds = (): Set<string> => {
  try {
    const raw = localStorage.getItem(COLLAPSED_SCRIPTS_STORAGE_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw)
    return new Set(Array.isArray(parsed) ? parsed.filter(id => typeof id === 'string') : [])
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
    // 存储不可用时（如隐私模式）忽略，仅本次会话内生效
  }
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

// 搜索匹配元素管理
const searchMatchElements = new Map<string, HTMLElement>()

const setSearchMatchElement = (key: string, element: unknown) => {
  if (element instanceof HTMLElement) {
    searchMatchElements.set(key, element)
  } else {
    searchMatchElements.delete(key)
  }
}

const scrollToSearchMatch = (key: string) => {
  const element = searchMatchElements.get(key)
  if (!element?.isConnected) return
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  // 'nearest' 仅在元素不在视口内时滚动，避免键盘导航时的多余跳动；
  // 低性能 / reduced-motion 模式下禁用 smooth 滚动以减少主线程开销。
  element.scrollIntoView({
    behavior: reduceMotion ? 'auto' : 'smooth',
    block: 'nearest',
  })
}

defineExpose({ collapseAllUsers, expandAllUsers, scrollToSearchMatch })

// 监听 props 变化，更新本地状态；拖拽/排序 pending 期间跳过，避免刷新覆盖新状态
watch(
  () => props.scripts,
  newScripts => {
    if (isDraggingScripts.value || isReorderingScripts.value) return
    localScripts.value = [...newScripts]
  },
  { immediate: true, deep: true }
)

const restoreScriptOrder = () => {
  localScripts.value = restoreItemOrder(scriptOrderBeforeDrag.value, props.scripts)
}

const onScriptDragStart = () => {
  if (searchActive.value || isReorderingScripts.value) return
  isDraggingScripts.value = true
  scriptOrderBeforeDrag.value = localScripts.value.map(s => s.id)
}

const onScriptDragEnd = async () => {
  if (!isDraggingScripts.value || isReorderingScripts.value) return
  isDraggingScripts.value = false
  const scriptIds = localScripts.value.map(s => s.id)
  const previousIds = scriptOrderBeforeDrag.value
  // 无实际顺序变化时不调用 API
  if (isSameOrder(scriptIds, previousIds)) {
    localScripts.value = [...props.scripts]
    scriptOrderBeforeDrag.value = []
    return
  }

  isReorderingScripts.value = true
  try {
    await registryApi.reorderScripts(scriptIds)
    // 请求期间父层可能刷新了对象或新增脚本；按已持久化顺序重排最新真值，
    // 避免成功后把刷新结果覆盖回拖拽前顺序，也避免丢失新增项。
    localScripts.value = restoreItemOrder(scriptIds, props.scripts)
    emit('scriptsReordered', localScripts.value)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    message.error(`脚本排序失败: ${errorMsg}`)
    restoreScriptOrder()
  } finally {
    isReorderingScripts.value = false
    scriptOrderBeforeDrag.value = []
  }
}

const restoreUserOrder = (scriptId: string, previousUserIds: string[]) => {
  const script = localScripts.value.find(s => s.id === scriptId)
  if (!script) return
  script.users = restoreItemOrder(previousUserIds, script.users)
}

const onUserReorder = async (scriptId: string, userIds: string[], previousUserIds: string[]) => {
  if (isReorderingUsers.value[scriptId]) return
  const script = localScripts.value.find(s => s.id === scriptId)
  if (!script) return
  // 无实际顺序变化时不调用 API
  if (isSameOrder(userIds, previousUserIds)) {
    scriptCardRefs.value.get(scriptId)?.finishUserReorder(true)
    return
  }

  isReorderingUsers.value = { ...isReorderingUsers.value, [scriptId]: true }
  try {
    await registryApi.reorderUsers(scriptId, userIds)
    scriptCardRefs.value.get(scriptId)?.finishUserReorder(true)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    message.error(`用户排序失败: ${errorMsg}`)
    restoreUserOrder(scriptId, previousUserIds)
    scriptCardRefs.value.get(scriptId)?.finishUserReorder(false)
  } finally {
    const next = { ...isReorderingUsers.value }
    delete next[scriptId]
    isReorderingUsers.value = next
  }
}
</script>

<style scoped>
.scripts-grid {
  width: 100%;
}

/* 拖拽样式 */
.draggable-scripts {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-4);
}

/* 脚本级拖拽占位样式；ScriptCard 内部保留自身的拖拽视觉。
   此处仅保留 ghost/chosen/drag 类名占位，避免 vuedraggable 类名找不到目标。 */
.script-ghost {
  opacity: 0 !important;
  background: transparent !important;
  border-color: transparent !important;
  box-shadow: none !important;
}

.script-chosen {
  cursor: grabbing !important;
}

.script-drag {
  transform: rotate(2deg);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.2);
  z-index: 1000;
  opacity: 1 !important;
  cursor: grabbing !important;
}

.script-drag * {
  cursor: grabbing !important;
}
</style>
