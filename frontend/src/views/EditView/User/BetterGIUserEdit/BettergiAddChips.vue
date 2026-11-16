<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useEventListener, useTimeoutFn } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { CloseOutlined } from '@ant-design/icons-vue'
import { kindTagClass } from './bettergiQueueIdentity'
import type { ConfigGroupIdentity } from './bettergiQueueIdentity'
type AddChipItem = ConfigGroupIdentity & { chipUid: number }

const props = defineProps<{ groupLabel: (item: ConfigGroupIdentity) => string }>()
const items = defineModel<AddChipItem[]>('items', { required: true })
const draft = defineModel<string>('draft', { required: true })
const emit = defineEmits<{ commit: [] }>()
const { t } = useI18n()
const addDraftInputRef = ref<HTMLInputElement | null>(null)

const addDraftFocused = ref(false)

const focusAddDraftInput = () => {
  void nextTick(() => addDraftInputRef.value?.focus())
}

// 删除指定气泡（同时从选中集合移除）
const removeAddChip = (chipUid: number) => {
  items.value = items.value.filter(c => c.chipUid !== chipUid)
  unselectChip(chipUid)
}

// ---- 气泡选择（Shift 区间 / Ctrl 逐个 / 拖动框选）+ 回退键删除 ----
// 选中集合按 chipUid 记录
const chipSelectedUids = ref<Set<number>>(new Set())

// Shift 区间锚点 chipUid（普通/Ctrl 点击时更新）
const chipAnchorUid = ref<number>(-1)

// 鼠标拖动框选：左键按下起点 chipUid 与进行状态
const chipDragAnchorUid = ref<number>(-1)

const chipDragging = ref(false)

const isChipSelected = (chipUid: number): boolean => chipSelectedUids.value.has(chipUid)

// 点击输入区空白：聚焦草稿输入框并清除气泡选中
const handleTagEditorClick = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  if (target.closest('.add-dragon-tag-chip')) return
  clearChipSelection()
  focusAddDraftInput()
}

const clearChipSelection = () => {
  chipSelectedUids.value = new Set()
  chipAnchorUid.value = -1
}

const unselectChip = (chipUid: number) => {
  const next = new Set(chipSelectedUids.value)
  next.delete(chipUid)
  chipSelectedUids.value = next
  if (chipAnchorUid.value === chipUid) chipAnchorUid.value = -1
}

const selectChip = (chipUid: number) => {
  const next = new Set(chipSelectedUids.value)
  next.add(chipUid)
  chipSelectedUids.value = next
}

// 区间选择：[from, to]（含两端，按 items.value 当前顺序）
const selectChipRange = (fromUid: number, toUid: number) => {
  const indexOf = (uid: number) => items.value.findIndex(c => c.chipUid === uid)
  let lo = indexOf(fromUid)
  let hi = indexOf(toUid)
  if (lo < 0 && hi < 0) return
  if (lo < 0) lo = hi
  if (hi < 0) hi = lo
  const next = new Set<number>()
  for (let i = Math.min(lo, hi); i <= Math.max(lo, hi); i += 1) {
    next.add(items.value[i].chipUid)
  }
  chipSelectedUids.value = next
}

// 拖动状态：是否真的拖离了起点气泡（用于区分"拖动框选"与"普通单击"）
let chipDragMoved = false

// 拖动结束标记：确实拖动过的 mouseup 之后若紧随 click（松开于气泡上），忽略以免覆盖拖选结果
let chipDragJustFinished = false

// 气泡点击：普通=单选（并作 Shift 锚点）；Ctrl=逐个切换；Shift=区间选择
const handleChipClick = (chip: AddChipItem, event: MouseEvent) => {
  // 拖动框选刚结束的 click 忽略，避免把拖选区间重置为单点
  if (chipDragJustFinished) {
    chipDragJustFinished = false
    return
  }
  if (event.shiftKey) {
    const anchor = chipAnchorUid.value >= 0 ? chipAnchorUid.value : chip.chipUid
    selectChipRange(anchor, chip.chipUid)
    chipAnchorUid.value = chip.chipUid
    focusAddDraftInput()
    return
  }
  if (event.ctrlKey || event.metaKey) {
    if (chipSelectedUids.value.has(chip.chipUid)) unselectChip(chip.chipUid)
    else selectChip(chip.chipUid)
    chipAnchorUid.value = chip.chipUid
    focusAddDraftInput()
    return
  }
  chipSelectedUids.value = new Set([chip.chipUid])
  chipAnchorUid.value = chip.chipUid
  focusAddDraftInput()
}

const { start: resetDragFinished } = useTimeoutFn(
  () => {
    chipDragJustFinished = false
  },
  0,
  { immediate: false }
)

const finishChipDrag = () => {
  if (!chipDragging.value) return
  chipDragging.value = false
  chipDragAnchorUid.value = -1
  // 仅拖动后忽略随后的 click；下一轮事件恢复单击选择。
  if (chipDragMoved) {
    chipDragJustFinished = true
    resetDragFinished()
  }
  focusAddDraftInput()
}
// 在 setup 注册，监听和短定时器随组件作用域卸载；空闲时忽略 mouseup。
useEventListener(window, 'mouseup', finishChipDrag)

// 气泡按下左键：进入拖动框选。
const handleChipMouseDown = (chip: AddChipItem, event: MouseEvent) => {
  if (event.button !== 0) return
  chipDragJustFinished = false
  chipDragMoved = false
  chipDragging.value = true
  chipDragAnchorUid.value = chip.chipUid
}

// 拖动经过其它气泡：实时区间选择（从按下起点到当前气泡）
const handleChipMouseEnter = (chip: AddChipItem) => {
  if (!chipDragging.value || chipDragAnchorUid.value < 0) return
  if (chip.chipUid !== chipDragAnchorUid.value) chipDragMoved = true
  selectChipRange(chipDragAnchorUid.value, chip.chipUid)
}

// 回退键删除选中气泡；无选中时 Backspace 删除最后一个
const removeSelectedChips = () => {
  if (!chipSelectedUids.value.size) return
  items.value = items.value.filter(c => !chipSelectedUids.value.has(c.chipUid))
  clearChipSelection()
}

// 行内输入按键：Enter 或「;」「；」提交草稿（拼写检查一致）；
// Backspace/Delete：删除选中的气泡（无选中时 Backspace 删除最后一个气泡）；输入法组合期忽略
const handleAddDraftKeydown = (e: KeyboardEvent) => {
  if (e.isComposing) return
  if (e.key === 'Enter' || e.key === ';' || e.key === '；') {
    e.preventDefault()
    emit('commit')
    return
  }
  const hasDraft = draft.value.trim().length > 0
  if (hasDraft) return
  if (e.key === 'Backspace' || e.key === 'Delete') {
    if (chipSelectedUids.value.size) {
      // 有选中气泡：删除选中的多个
      e.preventDefault()
      removeSelectedChips()
      return
    }
    if (e.key === 'Backspace' && items.value.length) {
      // 无选中：回退删除最后一个气泡
      e.preventDefault()
      removeAddChip(items.value[items.value.length - 1].chipUid)
    }
  }
}
defineExpose({ focus: focusAddDraftInput, clearSelection: clearChipSelection })
</script>
<template>
  <div
    class="add-dragon-tag-editor add-dragon-input"
    :class="{ 'add-dragon-tag-editor-focus': addDraftFocused }"
    @click="handleTagEditorClick"
  >
    <span
      v-for="chip in items"
      :key="chip.chipUid"
      class="add-dragon-tag-chip"
      :class="[
        kindTagClass(chip.kind),
        { 'add-dragon-tag-chip-selected': isChipSelected(chip.chipUid) },
      ]"
      :title="t('core.edit.bettergiChipSelectHint')"
      @mousedown="handleChipMouseDown(chip, $event)"
      @mouseenter="handleChipMouseEnter(chip)"
      @click.stop="handleChipClick(chip, $event)"
    >
      <span class="add-dragon-tag-chip-label">{{ groupLabel(chip) }}</span>
      <CloseOutlined
        class="add-dragon-tag-chip-remove"
        @mousedown.stop.prevent
        @click.stop="removeAddChip(chip.chipUid)"
      />
    </span>
    <input
      ref="addDraftInputRef"
      v-model="draft"
      class="add-dragon-tag-draft-input"
      :placeholder="items.length ? '' : t('core.edit.bettergiInputGroupNames')"
      @focus="addDraftFocused = true"
      @blur="addDraftFocused = false"
      @keydown="handleAddDraftKeydown"
      @click.stop="clearChipSelection()"
    />
  </div>
</template>
<style scoped>
@import './bettergiGroupTags.css';
.add-dragon-tag-editor {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 2px 11px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  cursor: text;
  transition: border-color 0.15s ease;
}

.add-dragon-tag-editor:hover {
  border-color: var(--ant-color-primary-hover);
}

.add-dragon-tag-editor-focus {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

.add-dragon-tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 1px 6px 1px 10px;
  font-size: 13px;
  line-height: 22px;
  border-radius: 11px;
  border: 1px solid transparent;
  cursor: default;
  user-select: none;
}

.add-dragon-tag-chip-selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  box-shadow: 0 0 0 1px var(--ant-color-primary) inset;
}

.add-dragon-tag-chip-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.add-dragon-tag-chip-remove {
  flex: 0 0 auto;
  font-size: 10px;
  cursor: pointer;
  opacity: 0.6;
  padding: 2px;
  border-radius: 50%;
  transition:
    opacity 0.15s ease,
    background-color 0.15s ease;
}

.add-dragon-tag-chip-remove:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.08);
}

.add-dragon-tag-draft-input {
  flex: 1 1 120px;
  min-width: 120px;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  line-height: 22px;
  color: var(--ant-color-text);
  padding: 1px 0;
}

.add-dragon-tag-draft-input::placeholder {
  color: var(--ant-color-text-quaternary, var(--ant-color-text-tertiary));
}
</style>
