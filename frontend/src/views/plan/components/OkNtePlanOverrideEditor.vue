<template>
  <div class="override-editor">
    <a-alert type="info" show-icon :message="t('core.plan.oknte.inheritanceHint')" />
    <a-alert v-if="error" type="error" show-icon :message="error">
      <template #action>
        <a-button :loading="loading || isSaving" @click="loadFailed ? load() : retrySave()">{{
          t('core.apiErrors.retry')
        }}</a-button>
      </template>
    </a-alert>
    <div class="editor-loading">
      <a-spin :spinning="loading">
        <a-row :gutter="24" class="editor-columns">
          <OkNteConfigNavigation
            :groups="{ [t('core.edit.taskConfiguration')]: files }"
            :selected="selected"
            @select="selected = $event"
          />
          <a-col :span="16" class="configuration-panel">
            <h3>{{ activeFile?.displayName }}</h3>
            <a-form
              :key="selected ?? ''"
              layout="vertical"
              class="configuration-scroll"
              tabindex="0"
              :aria-label="activeFile?.displayName"
            >
              <OkNteOverrideField
                v-for="row in rows"
                :key="row.id"
                :field="row.field"
                :value="read(row)"
                :overridden="read(row) !== undefined"
                :disabled="loading"
                @set="change(row, $event)"
                @inherit="change(row, undefined)"
              />
            </a-form>
          </a-col>
        </a-row>
      </a-spin>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { OknteService, type OkNtePlanFile } from '@/api'
import { saveOkNtePlan } from '@/composables/useOkNtePlanApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import OkNteConfigNavigation from '@/views/EditView/User/OkNteUserEdit/OkNteConfigNavigation.vue'
import OkNteOverrideField from './OkNteOverrideField.vue'
import type { OverrideField, OverrideRow, OverrideConfigs } from '../oknteOverrideTypes'
type FileInfo = OkNtePlanFile
const props = defineProps<{ planId: string; day: string }>()
const { t } = useI18n()
const files = ref<FileInfo[]>([])
const selected = ref<string | null>(null)
const configs = ref<OverrideConfigs>({})
const loading = ref(false)
const error = ref('')
const loadFailed = ref(false)
const { enqueue, isSaving } = useSaveQueue()
const activeFile = computed(() => files.value.find(file => file.filename === selected.value))
const rows = computed<OverrideRow[]>(() => {
  const result: OverrideRow[] = []
  const file = activeFile.value
  if (!file) return result
  function append(field: OverrideField, parent: string[], prefix: string) {
    const path = [...parent, field.name]
    const label = prefix + (field.label || field.name)
    if (field.type === 'object' && field.children?.length)
      for (const child of field.children) append(child, path, label + ' / ')
    else if (field.type === 'routine_items')
      for (const item of field.itemDefinitions ?? [])
        result.push({
          id: item.id,
          field: { name: item.id, label: item.label, type: 'bool', value: false },
          path,
          routineId: item.id,
        })
    else result.push({ id: path.join('/'), field: { ...field, label }, path })
  }
  for (const field of file.fields) append(field, [file.filename], '')
  return result
})
function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}
function read(row: OverrideRow): unknown {
  let value: unknown = configs.value
  for (const key of row.path) value = object(value)[key]
  if (row.routineId)
    return Array.isArray(value)
      ? value.find(item => object(item).id === row.routineId)?.enabled
      : undefined
  return value
}
let pending: Promise<boolean> = Promise.resolve(true)
function change(row: OverrideRow, value: unknown) {
  const next: OverrideConfigs = JSON.parse(JSON.stringify(configs.value))
  let parent: Record<string, unknown> = next
  for (const key of row.path.slice(0, -1)) {
    if (!parent[key]) parent[key] = {}
    parent = object(parent[key])
  }
  const key = row.path.at(-1)!
  if (row.routineId) {
    const items = Array.isArray(parent[key])
      ? (parent[key] as Record<string, unknown>[]).filter(item => item.id !== row.routineId)
      : []
    if (value !== undefined) {
      items.push({ id: row.routineId, enabled: value })
      const definition = activeFile.value?.fields
        .find(field => field.name === key)
        ?.itemDefinitions?.find(item => item.id === row.routineId)
      if (value === true && definition?.exclusiveGroup) {
        for (const item of activeFile.value?.fields.find(field => field.name === key)
          ?.itemDefinitions ?? [])
          if (item.id !== row.routineId && item.exclusiveGroup === definition.exclusiveGroup) {
            const found = items.find(entry => entry.id === item.id)
            if (found) found.enabled = false
            else items.push({ id: item.id, enabled: false })
          }
      }
    }
    if (items.length) parent[key] = items
    else delete parent[key]
  } else if (value === undefined) delete parent[key]
  else parent[key] = value
  configs.value = next
  queueSave(next)
}
function queueSave(next: OverrideConfigs) {
  const planId = props.planId,
    day = props.day
  pending = enqueue(async () => {
    try {
      const result = await saveOkNtePlan(planId, day, next, true)
      if (result.code !== 200) throw new Error(result.message)
      error.value = ''
      return true
    } catch (reason) {
      error.value = String(reason)
      return false
    }
  })
}
function retrySave() {
  queueSave(JSON.parse(JSON.stringify(configs.value)))
}
async function saveAll() {
  return await pending
}
defineExpose({ saveAll })
onBeforeRouteLeave(saveAll)
onBeforeRouteUpdate(saveAll)
async function load() {
  loading.value = true
  loadFailed.value = false
  files.value = []
  error.value = ''
  try {
    const response = await OknteService.getOkntePlanConfigsApiScriptsOkntePlanConfigsPost(
      props.planId,
      props.day
    )
    if (response.code !== 200) throw new Error(response.message)
    files.value = response.data ?? []
    configs.value = Object.fromEntries(files.value.map(file => [file.filename, file.overrides]))
    selected.value = files.value[0]?.filename ?? null
  } catch (reason) {
    loadFailed.value = true
    error.value = String(reason)
  } finally {
    loading.value = false
  }
}
watch(() => [props.planId, props.day], load, { immediate: true })
</script>

<style scoped>
.override-editor {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.override-editor > .ant-alert {
  flex-shrink: 0;
}
.editor-loading {
  flex: 1;
  min-height: 0;
}
.editor-loading :deep(.ant-spin-nested-loading),
.editor-loading :deep(.ant-spin-container),
.editor-columns {
  height: 100%;
}
.configuration-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.configuration-panel h3 {
  flex-shrink: 0;
  margin: 0 0 16px;
  font-size: 16px;
  line-height: 24px;
}
.editor-columns :deep(.group-header) {
  padding: 0 12px 16px;
  font-size: 16px;
  line-height: 24px;
}
.configuration-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  scrollbar-gutter: stable;
  padding: 16px;
  background-color: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}
.override-editor :deep(.ant-select-selector),
.override-editor :deep(.ant-input-number),
.override-editor :deep(.ant-input) {
  background-color: var(--ant-color-bg-elevated);
}
</style>
