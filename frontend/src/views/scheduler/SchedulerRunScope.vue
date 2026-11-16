<template>
  <a-button size="large" :disabled="disabled" @click="open = true">
    <template #icon><TeamOutlined /></template>
    {{ t('core.scheduler.control.runScopeTitle') }}
    <span
      v-if="!loading && !error"
      class="scope-button-count"
      :class="{ 'is-partial': scopePartial }"
      >{{ selectedCount }}/{{ userCount }}</span
    >
  </a-button>
  <a-modal
    v-model:open="open"
    :title="t('core.scheduler.control.runScopeTitle')"
    :width="1120"
    wrap-class-name="scheduler-scope-modal"
    destroy-on-close
  >
    <div class="scope-toolbar">
      <div class="scope-summary">
        <span>{{ t('core.scheduler.scope.items', { count: draft?.entries.length ?? 0 }) }}</span>
        <span>{{
          t('core.scheduler.scope.users', { selected: selectedCount, total: userCount })
        }}</span>
      </div>
      <a-space :size="4">
        <a-button
          type="link"
          size="small"
          :disabled="loading || !draft || draft.selection === 'all'"
          @click="selectAll"
          >{{ t('core.scheduler.scope.all') }}</a-button
        >
        <a-button
          type="link"
          size="small"
          danger
          :disabled="loading || !draft || draft.selection === 'none'"
          @click="clearAll"
          >{{ t('core.scheduler.scope.clear') }}</a-button
        >
        <a-button
          type="text"
          size="small"
          :loading="loading"
          :aria-label="t('core.scheduler.scope.refresh')"
          :title="t('core.scheduler.scope.refresh')"
          @click="emit('refresh')"
        >
          <template #icon><ReloadOutlined /></template>
        </a-button>
      </a-space>
    </div>
    <!-- 只由此列表滚动；标题、工具栏和底部确认按钮始终可见。 -->
    <div class="scope-entries" tabindex="0" :aria-label="t('core.scheduler.control.runScopeTitle')">
      <a-alert v-if="error" type="error" show-icon :message="error">
        <template #action
          ><a-button size="small" @click="emit('refresh')">{{
            t('core.scheduler.control.runScopeRetry')
          }}</a-button></template
        >
      </a-alert>
      <div v-else-if="loading" class="scope-state"><a-spin /></div>
      <div v-else-if="!draft?.entries.length" class="scope-state">
        <a-empty
          :description="t('core.scheduler.control.runScopeNoUsers')"
          :image="Empty.PRESENTED_IMAGE_SIMPLE"
        />
      </div>
      <section
        v-for="({ entry, selected, missingUsers }, index) in error || loading ? [] : rows"
        :key="entry.uid"
        class="queue-scope-group"
      >
        <div class="scope-entry-heading">
          <a-checkbox
            :checked="
              entry.selection === 'all' ||
              (entry.selection === 'explicit' &&
                selected.size > 0 &&
                selected.size === entry.users.length &&
                !missingUsers)
            "
            :indeterminate="
              entry.selection === 'explicit' &&
              selected.size > 0 &&
              selected.size < entry.users.length
            "
            @change="
              (event: CheckboxChangeEvent) => setEntry(entry.uid, Boolean(event.target.checked))
            "
          >
            <span v-if="draft?.kind === 'queue'" class="scope-position">{{ index + 1 }}</span>
            <span class="scope-name">{{ entry.name || entry.scriptId }}</span>
          </a-checkbox>
          <div class="scope-entry-actions">
            <span class="scope-summary">{{
              t('core.scheduler.scope.users', {
                selected: selected.size,
                total: entry.users.length,
              })
            }}</span>
            <a-button
              v-if="draft?.kind === 'queue'"
              type="link"
              size="small"
              @click="fromHere(index)"
              >{{ t('core.scheduler.scope.fromHere') }}</a-button
            >
          </div>
        </div>
        <a-alert
          v-if="entry.missing || missingUsers"
          class="scope-warning"
          type="warning"
          show-icon
          :message="t('core.scheduler.scope.missing')"
        />
        <div v-if="!entry.missing && entry.users.length" class="scope-users">
          <a-checkbox
            v-for="user in entry.users"
            :key="user.uid"
            :checked="selected.has(user.uid)"
            @change="
              (event: CheckboxChangeEvent) =>
                setUser(entry.uid, user.uid, Boolean(event.target.checked))
            "
          >
            <span class="scope-user-name">{{ user.name }}</span>
          </a-checkbox>
        </div>
        <p v-else-if="!entry.missing" class="scope-empty">
          {{ t('core.scheduler.control.runScopeNoUsers') }}
        </p>
      </section>
    </div>
    <template #footer>
      <a-button type="primary" size="large" @click="open = false">{{
        t('core.common.confirm')
      }}</a-button>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Empty } from 'ant-design-vue'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import { ReloadOutlined, TeamOutlined } from '@ant-design/icons-vue'
import {
  selectedScopeUsers,
  type TaskScopeDraft,
  type TaskScopeEntry,
} from '@/composables/taskSelection'

const props = defineProps<{
  modelValue?: TaskScopeDraft
  loading?: boolean
  error?: string
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: TaskScopeDraft]; refresh: [] }>()
const { t } = useI18n()
const open = ref(false)
const draft = computed(() => props.modelValue)
const rows = computed(
  () =>
    draft.value?.entries.map(entry => {
      const selected = new Set(selectedScopeUsers(entry))
      return {
        entry,
        selected,
        missingUsers:
          entry.selection === 'explicit' &&
          entry.selected.some(uid => !entry.users.some(user => user.uid === uid)),
      }
    }) ?? []
)
const userCount = computed(
  () => draft.value?.entries.reduce((sum, entry) => sum + entry.users.length, 0) ?? 0
)
const selectedCount = computed(
  () => draft.value?.entries.reduce((sum, entry) => sum + selectedScopeUsers(entry).length, 0) ?? 0
)

const scopePartial = computed(() => selectedCount.value < userCount.value)

const updateEntries = (
  change: (entry: TaskScopeEntry, index: number) => TaskScopeEntry,
  selection: TaskScopeDraft['selection'] = 'explicit'
) => {
  if (draft.value)
    emit('update:modelValue', {
      ...draft.value,
      selection,
      entries: draft.value.entries.map(change),
    })
}
const selectAll = () =>
  updateEntries(entry => ({ ...entry, selection: 'all', selected: [] }), 'all')
const clearAll = () =>
  updateEntries(entry => ({ ...entry, selection: 'none', selected: [] }), 'none')
const fromHere = (index: number) =>
  updateEntries((entry, position) => ({
    ...entry,
    selection: position < index ? 'none' : 'all',
    selected: [],
  }))
const setEntry = (uid: string, checked: boolean) =>
  updateEntries(entry =>
    entry.uid === uid ? { ...entry, selection: checked ? 'all' : 'none', selected: [] } : entry
  )
const setUser = (entryUid: string, userUid: string, checked: boolean) =>
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
</script>

<style scoped>
/* 共享 overlay 样式预留标题栏；弹窗体仅负责分配高度，不另加滚动条。 */
:global(.scheduler-scope-modal.ant-modal-wrap) {
  padding-block: 16px;
  overflow: hidden;
}
:global(.scheduler-scope-modal .ant-modal) {
  top: 0;
  max-width: calc(100vw - 32px);
  margin-block: 0;
  padding-bottom: 0;
}
:global(.scheduler-scope-modal .ant-modal-content) {
  display: flex;
  flex-direction: column;
  height: min(720px, calc(100vh - 32px));
}
:global(.scheduler-scope-modal .ant-modal-header),
:global(.scheduler-scope-modal .ant-modal-footer) {
  flex-shrink: 0;
}
:global(.scheduler-scope-modal .ant-modal-title) {
  font-size: 18px;
  line-height: 26px;
}
:global(.scheduler-scope-modal .ant-modal-body) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.scope-toolbar,
.scope-entry-heading,
.scope-entry-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.scope-toolbar {
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 12px;
}
.scope-summary,
.scope-position,
.scope-empty {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
}
.scope-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-variant-numeric: tabular-nums;
}
.scope-entries {
  flex: 1;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  padding-inline-end: 8px;
}
.scope-entries:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}
.queue-scope-group {
  padding: 16px 0;
  border-top: 1px solid var(--ant-color-border);
}
.scope-entry-heading {
  align-items: flex-start;
}
.scope-entry-heading :deep(.ant-checkbox-wrapper) {
  flex: 1;
  min-width: 0;
  font-size: 16px;
  line-height: 24px;
}
.scope-entry-heading :deep(.ant-checkbox-wrapper > span:last-child) {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.scope-name {
  font-weight: 500;
  overflow-wrap: anywhere;
}
.scope-entry-actions {
  flex-shrink: 0;
  gap: 8px;
}
.scope-users {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 230px), 1fr));
  gap: 16px;
  padding: 16px 0 0 24px;
}
.scope-users :deep(.ant-checkbox-wrapper) {
  align-items: flex-start;
  min-width: 0;
  margin-inline-start: 0;
  font-size: 16px;
  line-height: 24px;
}
.scope-users :deep(.ant-checkbox),
.scope-entry-heading :deep(.ant-checkbox) {
  align-self: flex-start;
  margin-top: 4px;
}
.scope-user-name {
  overflow-wrap: anywhere;
}
.scope-empty {
  margin: 12px 0 0 24px;
}
.scope-warning {
  margin-top: 12px;
}
.scope-state {
  display: grid;
  place-items: center;
  min-height: 128px;
  height: 100%;
}
.scope-button-count {
  margin-left: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.scope-button-count.is-partial {
  color: var(--ant-color-warning);
}
@media (max-width: 600px) {
  .scope-entry-heading {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>
