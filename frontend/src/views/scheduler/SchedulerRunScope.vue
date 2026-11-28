<template>
  <a-popover
    :open="open"
    :trigger="triggerDisabled ? [] : 'click'"
    :placement="showAbove ? 'topLeft' : 'bottomLeft'"
    :arrow="false"
    :auto-adjust-overflow="false"
    :align="{ offset: [horizontalOffset, showAbove ? -4 : 4] }"
    destroy-tooltip-on-hide
    :overlay-style="{ padding: 0 }"
    :overlay-inner-style="{ padding: 0, borderRadius: 'var(--ant-border-radius)' }"
    @open-change="setOpen"
  >
    <a-button
      ref="trigger"
      type="text"
      class="scope-invoker run-control-trigger"
      :class="{ customized: summary && !error && rows.length && !allChecked }"
      :disabled="triggerDisabled"
      :aria-expanded="open"
      :aria-controls="open ? panelId : undefined"
      :aria-label="
        triggerLabel ? t('core.scheduler.scope.trigger', { value: triggerLabel }) : undefined
      "
      :title="summary"
      @keydown.down.prevent="setOpen(true)"
      @keydown.esc="setOpen(false)"
    >
      <span class="invoker-content">
        <FilterOutlined class="invoker-filter" />
        <span class="invoker-value">{{
          triggerLabel ?? t('core.scheduler.control.runScopeTitle')
        }}</span>
        <DownOutlined class="invoker-arrow" :rotate="open ? 180 : 0" />
      </span>
    </a-button>
    <template #content>
      <section
        :id="panelId"
        ref="panel"
        class="scope-sheet"
        :class="{ compact: panelHeight < (pickingStart ? 200 : 160) }"
        role="region"
        :aria-label="t('core.scheduler.control.runScopeTitle')"
        tabindex="-1"
        :style="{ maxHeight: `${panelHeight}px` }"
        @keydown.esc.stop.prevent="escape"
        @focusout="onFocusOut"
      >
        <header class="sheet-heading">
          <h2>{{ t('core.scheduler.control.runScopeTitle') }}</h2>
          <div v-if="ready && !pickingStart" class="sheet-count" role="status" aria-atomic="true">
            <i18n-t
              v-if="draft?.kind === 'queue'"
              keypath="core.scheduler.scope.items"
              tag="span"
              scope="global"
            >
              <template #count
                ><b>{{ chosenEntries }}/{{ rows.length }}</b></template
              >
            </i18n-t>
            <i18n-t keypath="core.scheduler.scope.accounts" tag="span" scope="global">
              <template #count
                ><b>{{ selectedCount }}/{{ userCount }}</b></template
              >
            </i18n-t>
          </div>
        </header>
        <a-alert v-if="error" class="scope-state" type="error" show-icon :message="error">
          <template #action
            ><a-button size="small" @click="emit('refresh')">{{
              t('core.scheduler.control.runScopeRetry')
            }}</a-button></template
          >
        </a-alert>
        <div v-else-if="!ready" class="scope-state" role="status">
          <a-spin size="small" /> {{ t('core.scheduler.scope.loading') }}
        </div>
        <a-empty
          v-else-if="!rows.length"
          class="scope-state"
          :image="Empty.PRESENTED_IMAGE_SIMPLE"
          :description="t('core.scheduler.scope.emptyQueue')"
        />
        <RunScopeStartPoint
          v-else-if="pickingStart"
          :rows="rows"
          :disabled="disabled"
          @apply="applyStart"
          @back="closePicker"
        />
        <template v-else>
          <div class="tree-master">
            <a-checkbox
              :checked="allChecked"
              :indeterminate="chosenEntries > 0 && !allChecked"
              :disabled="disabled"
              @change="(event: CheckboxChangeEvent) => setAll(!!event.target.checked)"
              >{{ t('core.scheduler.scope.all') }}</a-checkbox
            >
            <a-button
              v-if="draft?.kind === 'queue' && rows.length > 1"
              ref="startPointButton"
              type="text"
              size="small"
              class="start-point-action"
              :disabled="disabled"
              @click="pickingStart = true"
            >
              {{ t('core.scheduler.scope.chooseStart') }} <FlagOutlined aria-hidden="true" />
            </a-button>
          </div>
          <ol class="tree-scroll">
            <RunScopeEntry
              v-for="({ entry, selected, checked, unavailable }, index) in rows"
              :key="entry.uid"
              :entry="entry"
              :selected="selected"
              :checked="checked"
              :unavailable="unavailable"
              :position="draft?.kind === 'queue' ? index + 1 : undefined"
              :expanded="detail === entry.uid"
              :disabled="disabled"
              @toggle="detail = detail === entry.uid ? null : entry.uid"
              @select="value => setEntry(entry.uid, value)"
              @select-user="(uid, value) => setUser(entry.uid, uid, value)"
              @refresh="emit('refresh')"
            />
          </ol>
        </template>
      </section>
    </template>
  </a-popover>
</template>

<script setup lang="ts">
import { computed, nextTick, onDeactivated, ref, useId, useTemplateRef, watch } from 'vue'
import { useElementBounding, useElementVisibility, useWindowSize } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { Empty } from 'ant-design-vue'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import { DownOutlined, FilterOutlined, FlagOutlined } from '@ant-design/icons-vue'
import {
  selectedScopeUsers,
  type TaskScopeDraft,
  type TaskScopeEntry,
} from '@/composables/taskSelection'
import RunScopeEntry from './components/RunScopeEntry.vue'
import RunScopeStartPoint from './components/RunScopeStartPoint.vue'

const props = defineProps<{
  hasTarget: boolean
  modelValue?: TaskScopeDraft
  loading?: boolean
  error?: string
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: TaskScopeDraft]; refresh: [] }>()
const draft = computed(() => props.modelValue)
const triggerDisabled = computed(() => !props.hasTarget || props.disabled)
const { t } = useI18n()
const open = ref(false)
const pickingStart = ref(false)
const detail = ref<string | null>(null)
const panelId = useId()
const trigger = useTemplateRef<{ $el: HTMLButtonElement }>('trigger')
const startPointButton = useTemplateRef<{ $el: HTMLButtonElement }>('startPointButton')
const panel = useTemplateRef<HTMLElement>('panel')
const panelVisible = useElementVisibility(panel)
const { left, top, bottom, update } = useElementBounding(() => trigger.value?.$el)
const { width, height } = useWindowSize()
const spaceBelow = computed(() => Math.max(0, height.value - bottom.value - 16))
// 极矮的窗口向上展开时，为桌面标题栏保留 32px。
const spaceAbove = computed(() => Math.max(0, top.value - 32 - 16))
const showAbove = computed(() => spaceBelow.value < 160 && spaceAbove.value > spaceBelow.value)
const panelHeight = computed(() =>
  Math.min(460, showAbove.value ? spaceAbove.value : spaceBelow.value)
)
const horizontalOffset = computed(() =>
  Math.min(0, width.value - 12 - left.value - Math.min(416, width.value - 24))
)
const ready = computed(() => !!draft.value && !props.loading && !props.error)
const rows = computed(() =>
  (draft.value?.entries ?? []).map(entry => {
    const selected = new Set(selectedScopeUsers(entry))
    const unavailable =
      !!entry.missing ||
      (entry.selection === 'explicit' &&
        entry.selected.some(uid => !entry.users.some(user => user.uid === uid)))
    const checked =
      entry.selection === 'all' ||
      (!unavailable && selected.size > 0 && selected.size === entry.users.length)
    return { entry, selected, checked, unavailable }
  })
)
const chosenEntries = computed(
  () => rows.value.filter(({ entry }) => entry.selection !== 'none').length
)
const allChecked = computed(
  () => rows.value.length > 0 && rows.value.every(row => row.checked && !row.unavailable)
)
const userCount = computed(() => rows.value.reduce((sum, { entry }) => sum + entry.users.length, 0))
const selectedCount = computed(() =>
  rows.value.reduce(
    (sum, { entry, selected }) => sum + entry.users.filter(user => selected.has(user.uid)).length,
    0
  )
)
// 同一目标重读时保留已确认的摘要；切换目标会按任务 ID 重建组件。
const selectionSummary = computed<string | undefined>(previous => {
  if (!ready.value) return previous
  if (!rows.value.length) return t('core.scheduler.scope.noEntries')
  if (!chosenEntries.value) return t('core.scheduler.scope.none')
  if (rows.value.some(row => row.unavailable && row.entry.selection !== 'none'))
    return t('core.scheduler.scope.review')
  if (allChecked.value)
    return draft.value?.kind === 'queue'
      ? t('core.scheduler.scope.allEntries')
      : t('core.scheduler.scope.allAccounts')
  if (chosenEntries.value === rows.value.length)
    return t('core.scheduler.scope.selectedAccounts', { count: selectedCount.value })
  return t('core.scheduler.scope.selectedEntries', { count: chosenEntries.value })
})
const summary = computed(() => {
  if (!props.hasTarget) return undefined
  return props.error ? t('core.scheduler.scope.loadError') : selectionSummary.value
})
const triggerLabel = computed(() =>
  // 新选任务默认全选，读取名单不会改变选择意图。
  props.hasTarget && !props.error && (!draft.value || allChecked.value)
    ? t('core.scheduler.scope.allSelected')
    : summary.value
)

function setOpen(value: boolean) {
  if (value) update()
  else {
    detail.value = null
    pickingStart.value = false
  }
  open.value = value
}
watch(panelVisible, visible => {
  const el = panel.value
  if (visible && el && open.value && document.activeElement === trigger.value?.$el)
    (el.querySelector<HTMLElement>('input:not(:disabled), button:not(:disabled)') ?? el).focus({
      preventScroll: true,
    })
})
onDeactivated(() => setOpen(false))

function onFocusOut(event: FocusEvent) {
  const target = event.relatedTarget
  if (
    target instanceof Node &&
    !panel.value?.contains(target) &&
    !trigger.value?.$el.contains(target)
  )
    setOpen(false)
}
function escape() {
  if (pickingStart.value) closePicker()
  else {
    setOpen(false)
    trigger.value?.$el.focus()
  }
}
function closePicker() {
  pickingStart.value = false
  nextTick(() => startPointButton.value?.$el.focus())
}
function updateEntries(
  change: (entry: TaskScopeEntry, index: number) => TaskScopeEntry,
  selection: TaskScopeDraft['selection'] = 'explicit'
) {
  if (draft.value)
    emit('update:modelValue', {
      ...draft.value,
      selection,
      entries: draft.value.entries.map(change),
    })
}
function setAll(checked: boolean) {
  const selection = checked ? 'all' : 'none'
  updateEntries(entry => ({ ...entry, selection, selected: [] }), selection)
}
function applyStart(index: number) {
  if (index > 0)
    updateEntries((entry, position) =>
      position < index ? { ...entry, selection: 'none', selected: [] } : entry
    )
  closePicker()
}
function setEntry(uid: string, checked: boolean) {
  updateEntries(entry =>
    entry.uid === uid ? { ...entry, selection: checked ? 'all' : 'none', selected: [] } : entry
  )
}
function setUser(entryUid: string, userUid: string, checked: boolean) {
  updateEntries(entry => {
    if (entry.uid !== entryUid) return entry
    const selected = new Set(selectedScopeUsers(entry))
    if (checked) selected.add(userUid)
    else selected.delete(userUid)
    return {
      ...entry,
      selection: selected.size ? 'explicit' : 'none',
      selected: entry.users.filter(user => selected.has(user.uid)).map(user => user.uid),
    }
  })
}
</script>

<style scoped>
.scope-invoker.ant-btn {
  display: grid;
  flex-shrink: 0;
  align-items: center;
  width: 146px;
  padding: 0 12px;
}
.scope-invoker.ant-btn > .invoker-content {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) 12px;
  column-gap: 4px;
  align-items: center;
  text-align: start;
  font-size: 14px;
  line-height: 22px;
}
.invoker-filter {
  font-size: 16px;
}
.invoker-filter,
.invoker-arrow {
  color: var(--ant-color-text-secondary);
}
.scope-invoker.customized .invoker-filter,
.scope-invoker[aria-expanded='true'] .invoker-arrow {
  color: var(--ant-color-link);
}
.invoker-value {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
}
.invoker-arrow {
  font-size: 11px;
}
.scope-sheet {
  display: flex;
  flex-direction: column;
  width: min(416px, calc(100vw - 24px));
  color: var(--ant-color-text);
  font-size: 14px;
  line-height: 22px;
}
.sheet-heading {
  flex: none;
  min-height: 54px;
  padding: 14px 18px 12px;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px 12px;
}
.sheet-heading h2 {
  margin: 0;
  font-size: 16px;
  line-height: 24px;
  font-weight: 600;
  color: var(--ant-color-text-heading);
}
.sheet-count {
  display: inline-flex;
  gap: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}
.sheet-count b {
  font-weight: 600;
  color: var(--ant-color-text);
}
.tree-master {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 36px;
  padding-inline: 16px;
  background: var(--ant-color-fill-quaternary);
  border-block: 1px solid var(--ant-color-border-secondary);
}
.tree-master :deep(.ant-checkbox-wrapper) {
  padding-inline: 2px;
  align-items: center;
  min-height: 32px;
}
.tree-master :deep(.ant-checkbox-wrapper > span:last-child) {
  padding-inline-start: 10px;
}
.start-point-action.ant-btn {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  padding-inline: 6px;
}
.tree-scroll {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  margin: 0;
  padding: 4px 0 7px;
  list-style: none;
}
.scope-sheet.compact {
  display: block;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.scope-sheet.compact .tree-scroll {
  overflow: visible;
}
.scope-state {
  margin: 8px 16px 16px;
  overflow: auto;
  text-align: center;
  color: var(--ant-color-text-secondary);
}
</style>
