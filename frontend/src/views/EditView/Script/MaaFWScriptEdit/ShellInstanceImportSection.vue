<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.shellImportTitle') }}</h3>
    </div>
    <p class="shell-import-hint">
      {{ t('edit.shellImportHint', { count: instances.length, source: sourceLabel }) }}
    </p>

    <div class="shell-import-list">
      <div class="shell-import-head">
        <a-checkbox
          :checked="allSelected"
          :indeterminate="partiallySelected"
          :disabled="disabled"
          @change="toggleAll"
        >
          {{ t('edit.shellImportSelectAll') }}
        </a-checkbox>
        <span class="shell-import-count">
          {{
            t('edit.shellImportSelectedCount', {
              selected: selectedSet.size,
              total: instances.length,
            })
          }}
        </span>
      </div>

      <div
        v-for="item in instances"
        :key="item.id"
        class="shell-import-row"
        :class="{ 'is-unselected': !selectedSet.has(item.id), 'is-disabled': disabled }"
        @click="toggle(item.id)"
      >
        <a-checkbox
          :checked="selectedSet.has(item.id)"
          :disabled="disabled"
          @click.stop
          @change="toggle(item.id)"
        />
        <div class="shell-import-main">
          <div class="shell-import-title">
            <span class="shell-import-name">{{ item.name }}</span>
            <a-tag class="shell-import-tag">{{ item.source }}</a-tag>
            <a-tag v-if="item.active" color="green" class="shell-import-tag">
              {{ t('edit.shellImportActive') }}
            </a-tag>
          </div>
          <div class="shell-import-meta">{{ describeMeta(item) }}</div>
        </div>
        <div class="shell-import-user">
          {{ t('edit.shellImportUserName', { name: item.userName }) }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MaaFWShellInstanceItem } from '@/api'
import { describeShellSources } from './shellInstanceImport'

const { t } = useI18n()

const props = defineProps<{
  instances: MaaFWShellInstanceItem[]
  selectedIds: string[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:selectedIds': [ids: string[]]
}>()

const selectedSet = computed(() => new Set(props.selectedIds))
const allSelected = computed(
  () => props.instances.length > 0 && props.instances.every(item => selectedSet.value.has(item.id))
)
const partiallySelected = computed(() => selectedSet.value.size > 0 && !allSelected.value)
const sourceLabel = computed(() => describeShellSources(props.instances.map(item => item.source)))

// 勾选结果按列表顺序给出，导入时用户也按这个顺序建
const emitSelection = (selected: Set<string>) => {
  emit(
    'update:selectedIds',
    props.instances.filter(item => selected.has(item.id)).map(item => item.id)
  )
}

const toggleAll = () => {
  if (props.disabled) return
  emitSelection(allSelected.value ? new Set() : new Set(props.instances.map(item => item.id)))
}

const toggle = (id: string) => {
  if (props.disabled) return
  const next = new Set(selectedSet.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  emitSelection(next)
}

// 「N 个任务 · 控制方式 · 资源」，取不到的项不写
const describeMeta = (item: MaaFWShellInstanceItem) =>
  [t('edit.shellImportTaskCount', { count: item.taskCount ?? 0 }), item.controller, item.resource]
    .filter(Boolean)
    .join(' · ')
</script>

<style scoped>
.form-section {
  margin-bottom: 24px;
}

.section-header {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 20px;
  background: var(--ant-color-text-quaternary);
  border-radius: 2px;
}

.shell-import-hint {
  margin: 0 0 12px;
  color: var(--ant-color-text-secondary);
}

.shell-import-list {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  overflow: hidden;
}

.shell-import-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--ant-color-fill-quaternary);
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.shell-import-count {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.shell-import-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  cursor: pointer;
}

.shell-import-row + .shell-import-row {
  border-top: 1px solid var(--ant-color-border-secondary);
}

.shell-import-row.is-disabled {
  cursor: not-allowed;
}

.shell-import-row.is-unselected .shell-import-main,
.shell-import-row.is-unselected .shell-import-user {
  opacity: 0.45;
}

.shell-import-main {
  flex: 1;
  min-width: 0;
}

.shell-import-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.shell-import-name {
  color: var(--ant-color-text);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shell-import-tag {
  margin-inline-end: 0;
}

.shell-import-meta {
  margin-top: 2px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.shell-import-user {
  flex-shrink: 0;
  max-width: 40%;
  color: var(--ant-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
