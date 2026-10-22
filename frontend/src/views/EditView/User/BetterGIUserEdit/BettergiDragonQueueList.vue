<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import draggable from 'vuedraggable'
import {
  ClearOutlined,
  CopyOutlined,
  EditOutlined,
  HolderOutlined,
  PlusOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue'
import { kindTagClass, type ConfigGroupIdentity } from './bettergiQueueIdentity'
const props = defineProps<{
  selected: ConfigGroupIdentity | null
  editable: boolean
  groupLabel: (item: ConfigGroupIdentity) => string
  groupPrefix: (item: ConfigGroupIdentity) => string
  isGroupFrozen: (item: ConfigGroupIdentity) => boolean
  groupEnabled: (item: ConfigGroupIdentity) => boolean
  toggleConfigGroup: (item: ConfigGroupIdentity) => void
  removeFromDragon: (item: ConfigGroupIdentity) => void
  clear: () => void
  persist: () => void
}>()
const {
  groupLabel,
  groupPrefix,
  isGroupFrozen,
  groupEnabled,
  toggleConfigGroup,
  removeFromDragon,
} = props
const emit = defineEmits<{
  select: [item: ConfigGroupIdentity]
  add: []
  duplicate: [item: ConfigGroupIdentity]
  rename: [item: ConfigGroupIdentity]
  copy: [item: ConfigGroupIdentity]
}>()
const dragonList = defineModel<ConfigGroupIdentity[]>('rows', { required: true })
const dragonListModel = dragonList
const groupsEditable = computed(() => props.editable)
const selectedGroupIdentity = computed(() => props.selected)
const selectConfigGroup = (item: ConfigGroupIdentity) => emit('select', item)
const persistDragonQueue = () => props.persist()
const clearDragon = () => {
  props.clear()
  clearMultiSelection()
}
const openAddToDragonModal = () => emit('add')
const canDuplicateGroup = (item: ConfigGroupIdentity) => item.kind !== 'stamina'
const canRenameGroup = canDuplicateGroup
const openDuplicateModal = (item: ConfigGroupIdentity) => emit('duplicate', item)
const openRenameModal = (item: ConfigGroupIdentity) => emit('rename', item)
const duplicateSameGroup = (item: ConfigGroupIdentity) => emit('copy', item)
const { t } = useI18n()
const logger = window.electronAPI.getLogger('BetterGI用户编辑')
// ---- 一条龙队列行多选（Shift 区间 / Ctrl 逐个）----
// 多选集合按 uid 记录（允许同类多实例时互不干扰）
const multiSelectedUids = ref<Set<number>>(new Set())

// Shift 区间选择的锚点行 uid（普通/Ctrl 点击时更新）
const multiAnchorUid = ref<number>(-1)
// 队列成员只由父级修改；移除成员时同步清理本列表的多选状态。
watch(
  () => dragonList.value.map(row => row.uid),
  uids => {
    const present = new Set(uids)
    multiSelectedUids.value = new Set([...multiSelectedUids.value].filter(uid => present.has(uid)))
  },
  { flush: 'sync' }
)

// 行是否在多选中
const isRowMultiSelected = (item: ConfigGroupIdentity): boolean =>
  item.uid != null && multiSelectedUids.value.has(item.uid)

// 当前多选中的行（按 dragonList 顺序，用于批量操作）
const multiSelectedRows = computed<ConfigGroupIdentity[]>(() =>
  dragonList.value.filter(i => i.uid != null && multiSelectedUids.value.has(i.uid))
)

// 是否处于多选状态（多于 1 行时展示批量操作）
const hasMultiSelection = computed<boolean>(() => multiSelectedRows.value.length > 1)

// 清空多选（单选切换/清空一条龙时调用）
const clearMultiSelection = () => {
  multiSelectedUids.value = new Set()
  multiAnchorUid.value = -1
}

// 行点击：普通=单选看详情（并作为后续 Shift 区间的锚点）；
// Ctrl=逐个切换多选；Shift=从锚点行到当前行区间多选。
const handleRowClick = (item: ConfigGroupIdentity, index: number, event: MouseEvent) => {
  if (!groupsEditable.value) return
  if (item.uid == null) return
  if (event.shiftKey) {
    // Shift 区间选择：锚点 uid 位于锚点行；按当前队列顺序圈选锚点行到当前行
    const anchorIndex = dragonList.value.findIndex(i => i.uid === multiAnchorUid.value)
    if (anchorIndex < 0) {
      // 无锚点（例如本次会话首次点击即 Shift）：以当前行为锚点，单选当前行
      multiAnchorUid.value = item.uid
      multiSelectedUids.value = new Set([item.uid])
      selectConfigGroup(item)
      return
    }
    const lo = Math.min(anchorIndex, index)
    const hi = Math.max(anchorIndex, index)
    const uids = new Set<number>()
    for (let i = lo; i <= hi; i += 1) {
      const uid = dragonList.value[i]?.uid
      if (uid != null) uids.add(uid)
    }
    multiSelectedUids.value = uids
    return
  }
  if (event.ctrlKey || event.metaKey) {
    multiAnchorUid.value = item.uid
    const next = new Set(multiSelectedUids.value)
    if (next.has(item.uid)) next.delete(item.uid)
    else next.add(item.uid)
    multiSelectedUids.value = next
    return
  }
  // 普通点击：清空多选集合，但保留当前行为后续 Shift 的锚点
  multiSelectedUids.value = new Set()
  multiAnchorUid.value = item.uid
  selectConfigGroup(item)
}

// 批量启停：把选中的每行切到 target（已处于目标状态的行跳过）
const batchToggleEnabled = (target: boolean) => {
  for (const row of multiSelectedRows.value) {
    if (!isGroupFrozen(row) && groupEnabled(row) !== target) {
      toggleConfigGroup(row)
    }
  }
}

// 批量移除选中行（确认后逐行移除）
const batchRemoveSelected = () => {
  const count = multiSelectedRows.value.length
  Modal.confirm({
    title: t('edit.bettergiMultiRemoveTitle'),
    content: t('edit.bettergiMultiRemoveContent', { count }),
    okText: t('edit.bettergiMultiRemove'),
    okButtonProps: { danger: true },
    cancelText: t('edit.cancel'),
    onOk: () => {
      const rows = [...multiSelectedRows.value]
      for (const row of rows) removeFromDragon(row)
      clearMultiSelection()
    },
  })
}

// draggable 行 key：优先用 uid（允许重复时每行唯一）；无 uid 时退化用身份
const getDragonRowKey = (item: ConfigGroupIdentity): string =>
  item.uid != null ? `row:${item.uid}` : `${item.kind}:${item.key}`

// 行是否被选中：按 uid 精确匹配（重复同类行互不影响）
const isRowSelected = (item: ConfigGroupIdentity): boolean => {
  const sel = selectedGroupIdentity.value
  if (!sel) return false
  if (item.uid != null && sel.uid != null) return item.uid === sel.uid
  return sel.kind === item.kind && sel.key === item.key
}

const handleGroupDragEnd = () => {
  // 拖拽结果按行实例顺序持久化到 OneDragon.Queue，运行时后端据此重建 TaskOrder
  persistDragonQueue()
  logger.debug(`一条龙队列顺序已调整: ${dragonList.value.map(i => i.key).join(',')}`)
}

// 右键某一配置组 → 确认后从一条龙移除
const handleRowContextMenu = (item: ConfigGroupIdentity) => {
  if (!groupsEditable.value) return
  if (isGroupFrozen(item)) {
    message.warning(t('edit.bettergiGroupFrozenTip'))
    return
  }
  Modal.confirm({
    title: t('edit.bettergiRemoveFromDragonTitle'),
    content: t('edit.bettergiRemoveFromDragonContent', { name: groupLabel(item) }),
    okText: t('edit.deleteSelected'),
    okButtonProps: { danger: true },
    cancelText: t('edit.cancel'),
    onOk: () => removeFromDragon(item),
  })
}
</script>
<template>
  <div class="bettergi-groups-pane bettergi-groups-list-pane">
    <div class="bettergi-groups-toolbar">
      <a-space size="small">
        <a-button
          type="primary"
          ghost
          size="small"
          :disabled="!groupsEditable"
          @click="openAddToDragonModal"
        >
          <template #icon>
            <PlusOutlined />
          </template>
          {{ t('edit.bettergiAddToDragon') }}
        </a-button>
        <a-popconfirm
          :title="t('edit.bettergiClearDragonTitle')"
          :ok-text="t('edit.ok')"
          :cancel-text="t('edit.cancel')"
          :disabled="!groupsEditable || dragonList.length === 0"
          @confirm="clearDragon"
        >
          <a-button size="small" :disabled="!groupsEditable || dragonList.length === 0">
            <template #icon>
              <ClearOutlined />
            </template>
            {{ t('edit.bettergiClearDragon') }}
          </a-button>
        </a-popconfirm>
      </a-space>
    </div>

    <div v-if="hasMultiSelection" class="bettergi-groups-multi-bar">
      <span class="bettergi-groups-multi-count">
        {{ t('edit.bettergiMultiSelected', { count: multiSelectedRows.length }) }}
      </span>
      <a-space size="small">
        <a-button size="small" @click="batchToggleEnabled(true)">
          {{ t('edit.bettergiMultiEnable') }}
        </a-button>
        <a-button size="small" @click="batchToggleEnabled(false)">
          {{ t('edit.bettergiMultiDisable') }}
        </a-button>
        <a-button size="small" danger @click="batchRemoveSelected">
          <template #icon><ClearOutlined /></template>
          {{ t('edit.bettergiMultiRemove') }}
        </a-button>
      </a-space>
    </div>

    <draggable
      v-model="dragonListModel"
      :item-key="getDragonRowKey"
      handle=".group-row-drag-area"
      :animation="200"
      :disabled="!groupsEditable"
      ghost-class="group-row-ghost"
      chosen-class="group-row-chosen"
      drag-class="group-row-drag"
      class="bettergi-groups-list"
      @end="handleGroupDragEnd"
    >
      <template #item="{ element: item, index }">
        <div
          class="group-row"
          :class="{
            'group-row-selected': isRowSelected(item),
            'group-row-multi': isRowMultiSelected(item),
            'group-row-disabled': !groupsEditable || isGroupFrozen(item),
            'group-row-frozen': isGroupFrozen(item),
          }"
          @contextmenu.prevent="handleRowContextMenu(item)"
          @click="handleRowClick(item, index, $event)"
        >
          <!-- 可拖拽热区：覆盖整行左 2/3（名称区），仅右键菜单/开关在热区外 -->
          <div class="group-row-drag-area">
            <HolderOutlined class="group-row-drag-handle" aria-hidden="true" />
            <span class="group-row-name">
              <a-tag size="small" class="group-row-kind-tag" :class="kindTagClass(item.kind)">
                {{ groupPrefix(item) }}
              </a-tag>
              <span class="group-row-label">{{ groupLabel(item) }}</span>
              <a-tag v-if="isGroupFrozen(item)" color="orange" size="small">
                {{ t('edit.bettergiGroupFrozen') }}
              </a-tag>
            </span>
          </div>
          <!-- 行尾操作（右对齐）：左=另存为新配置组（scriptgroup/js/pathing 内容可复制成新组），
                           右=复制相同（所有可编辑行直接加一份相同配置组入队，无弹窗；内置/专项同此） -->
          <span v-if="groupsEditable" class="group-row-actions" @click.stop>
            <a-tooltip v-if="canDuplicateGroup(item)" :title="t('edit.bettergiDuplicateAsNew')">
              <a-button
                class="group-row-action-btn"
                type="text"
                size="small"
                :disabled="isGroupFrozen(item)"
                :aria-label="t('edit.bettergiDuplicateAsNew')"
                @click.stop="openDuplicateModal(item)"
              >
                <template #icon><SaveOutlined /></template>
              </a-button>
            </a-tooltip>
            <a-tooltip :title="t('edit.bettergiRenameAsNew')">
              <a-button
                class="group-row-action-btn"
                type="text"
                size="small"
                :disabled="isGroupFrozen(item) || !canRenameGroup(item)"
                :aria-label="t('edit.bettergiRenameAsNew')"
                @click.stop="openRenameModal(item)"
              >
                <template #icon><EditOutlined /></template>
              </a-button>
            </a-tooltip>
            <a-tooltip :title="t('edit.bettergiCopySameAs')">
              <a-button
                class="group-row-action-btn"
                type="text"
                size="small"
                :disabled="isGroupFrozen(item)"
                :aria-label="t('edit.bettergiCopySameAs')"
                @click.stop="duplicateSameGroup(item)"
              >
                <template #icon><CopyOutlined /></template>
              </a-button>
            </a-tooltip>
          </span>
          <div
            class="config-group-item-capsule group-row-capsule"
            :class="{ active: groupEnabled(item) }"
            @click.stop="toggleConfigGroup(item)"
          >
            <span class="config-group-item-dot"></span>
          </div>
        </div>
      </template>
    </draggable>
  </div>
</template>
<style scoped>
@import './bettergiGroupTags.css';
@import './bettergiQueueCapsule.css';
.bettergi-groups-list-pane {
  padding-bottom: 8px;
}

.bettergi-groups-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.bettergi-groups-list-hint {
  padding: 8px 14px 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.bettergi-groups-list {
  padding: 0 8px;
}

.group-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  border: none;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  background: transparent;
  color: var(--ant-color-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease;
}

.group-row:last-child {
  border-bottom: none;
}

.group-row:hover {
  background: var(--ant-color-fill-quaternary);
}

.group-row-selected {
  background: var(--ant-color-primary-bg);
}

.group-row-multi {
  background: var(--ant-color-primary-bg);
  outline: 1px solid var(--ant-color-primary);
  outline-offset: -1px;
  box-shadow: inset 2px 0 0 var(--ant-color-primary);
}

.bettergi-groups-multi-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  margin-bottom: 8px;
  border: 1px solid var(--ant-color-primary-border);
  border-radius: 8px;
  background: var(--ant-color-primary-bg);
}

.bettergi-groups-multi-count {
  font-size: 12px;
  color: var(--ant-color-primary);
}

.group-row-disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.group-row-chosen,
.group-row-drag {
  cursor: grabbing;
}

.group-row-ghost {
  opacity: 0.45;
  background: var(--ant-color-primary-bg);
}

.group-row-drag-area {
  flex: 2 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: grab;
}

.group-row-drag-handle {
  flex: 0 0 auto;
  padding: 4px;
  border-radius: 4px;
  color: var(--ant-color-text-quaternary);
  font-size: 15px;
  transition:
    color 0.15s ease,
    background-color 0.15s ease;
}

.group-row-chosen .group-row-drag-area,
.group-row-drag .group-row-drag-area {
  cursor: grabbing;
}

.group-row-name {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-row-kind-tag {
  margin-inline-end: 0;
}

.group-row-capsule {
  flex: 0 0 auto;
}

.group-row-actions {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.group-row-action-btn {
  color: var(--ant-color-text-tertiary);
  transition: color 0.15s ease;
}

.group-row-action-btn:hover {
  color: var(--ant-color-primary);
}

.group-row-action-btn[disabled] {
  color: var(--ant-color-text-quaternary);
}

.group-row-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-row-kind-tag {
  margin-inline-end: 0;
  flex: 0 0 auto;
}

.group-row-frozen {
  opacity: 0.6;
}
</style>
