<template>
  <div class="override-editor">
    <a-alert type="info" show-icon :message="t('core.plan.oknte.inheritanceHint')" />
    <a-alert v-if="error" type="error" show-icon :message="error">
      <template #action>
        <a-space>
          <a-button :loading="loading || isSaving" @click="loadFailed ? load() : retrySave()">
            {{ t('core.apiErrors.retry') }}
          </a-button>
          <a-button v-if="!loadFailed" :disabled="isSaving" @click="discardAndBack">
            {{ t('core.plan.discardAndBack') }}
          </a-button>
        </a-space>
      </template>
    </a-alert>
    <div class="editor-loading">
      <a-spin :spinning="loading">
        <a-row :gutter="24" class="editor-columns">
          <a-col :span="8">
            <h3>{{ t('core.edit.taskConfiguration') }}</h3>
            <a-menu
              :selected-keys="[selected]"
              @click="({ key }: { key: string | number }) => (selected = String(key))"
            >
              <a-menu-item v-for="panel in panels" :key="panel.filename">{{
                panelLabel(panel.kind)
              }}</a-menu-item>
            </a-menu>
          </a-col>
          <a-col :span="16" class="configuration-panel">
            <h3>{{ activePanel && panelLabel(activePanel.kind) }}</h3>
            <a-form
              :key="selected"
              layout="vertical"
              class="configuration-scroll"
              tabindex="0"
              :aria-label="activePanel && panelLabel(activePanel.kind)"
            >
              <OkwwPlanOverrideItem
                v-if="targetGroup"
                :title="t(targetGroup.label)"
                :overridden="targetOverridden"
                :disabled="loading"
                label-only
                @toggle="toggleTarget"
              >
                <template v-if="targetIncomplete" #actions>
                  <a-button size="small" type="link" :disabled="loading" @click="completeTarget">
                    {{ t('core.plan.okww.completeTarget') }}
                  </a-button>
                </template>
              </OkwwPlanOverrideItem>
              <OkwwPlanOverrideField
                v-for="field in visibleFields"
                :key="field.name"
                :field="field"
                :grouped="isTargetField(field.name)"
                :labels="activePanel?.labels ?? {}"
                :default-value="
                  activePanel?.values[field.name] ?? activePanel?.overrides[field.name]
                "
                :value="
                  overrides[field.name] ??
                  (isTargetField(field.name) ? targetDefaults[field.name] : undefined)
                "
                :overridden="isTargetField(field.name) || field.name in overrides"
                :disabled="loading"
                @set="change(field.name, $event)"
                @inherit="change(field.name, undefined)"
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
import { navigateTo } from '@/router'
import type { OkwwConfigField, OkwwPlanPanel } from '@/api'
import { readOkwwPlan, saveOkwwPlan } from '@/composables/useOkwwPlanApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import OkwwPlanOverrideField from './OkwwPlanOverrideField.vue'
import OkwwPlanOverrideItem from './OkwwPlanOverrideItem.vue'
const props = defineProps<{ planId: string; day: string }>()
const { t, locale } = useI18n()
const panels = ref<OkwwPlanPanel[]>([])
const selected = ref('')
const configs = ref<Record<string, Record<string, unknown>>>({})
const loading = ref(false)
const error = ref('')
const loadFailed = ref(false)
const { enqueue, isSaving } = useSaveQueue()
const activePanel = computed(() => panels.value.find(panel => panel.filename === selected.value))
const overrides = computed(() => configs.value[selected.value] ?? {})
const targetGroup = computed(() => {
  if (activePanel.value?.kind === 'echo') {
    return { root: 'Teleport to Boss', label: 'core.plan.okww.bossTarget', always: ['Boss'] }
  }
  if (activePanel.value?.kind === 'daily') {
    return { root: 'Which to Farm', label: 'core.plan.okww.farm', always: [] }
  }
  return null
})
const targetDefaults = computed(() => activePanel.value?.values ?? {})
const targetFields = computed(() => {
  const group = targetGroup.value
  if (!group || !activePanel.value) return []
  const fields = activePanel.value.fields
  return [
    ...fields.filter(field => field.name === group.root),
    ...fields.filter(field => field.parent === group.root && field.name !== 'Boss Level'),
    ...fields.filter(field => field.parent === group.root && field.name === 'Boss Level'),
    ...fields.filter(field => group.always.includes(field.name)),
  ]
})
const targetOverridden = computed(() =>
  targetFields.value.some(field => field.name in overrides.value)
)
const targetIncomplete = computed(
  () =>
    targetOverridden.value &&
    targetFields.value.some(
      field => targetFieldActive(field, overrides.value) && overrides.value[field.name] == null
    )
)
function isTargetField(name: string) {
  return targetFields.value.some(field => field.name === name)
}
const visibleFields = computed(() => {
  const independent = activePanel.value?.fields.filter(field => !isTargetField(field.name)) ?? []
  const fields = targetOverridden.value ? [...targetFields.value, ...independent] : independent
  return fields.filter(field => targetFieldActive(field, overrides.value))
})
const panelLabels = {
  daily: 'core.edit.okwwDailyTab',
  echo: 'core.edit.okwwEchoConfigTitle',
  nightmare: 'core.edit.okwwPanelNightmare',
  combat: 'core.edit.okwwPanelCombat',
  character: 'core.edit.okwwPanelCharacter',
  monthly: 'core.edit.okwwPanelMonthly',
}
function panelLabel(kind: keyof typeof panelLabels) {
  return t(panelLabels[kind])
}
let pending: Promise<boolean> = Promise.resolve(true)
let revision = 0
function change(name: string, value: unknown) {
  const next = { ...overrides.value }
  if (value === undefined) delete next[name]
  else next[name] = value
  if (isTargetField(name)) fillTarget(next)
  savePanel(next)
}
function targetFieldActive(field: OkwwConfigField, values: Record<string, unknown>) {
  return (
    !field.parent ||
    field.choices?.includes(String(values[field.parent] ?? targetDefaults.value[field.parent]))
  )
}
function fillTarget(next: Record<string, unknown>) {
  for (const field of targetFields.value) {
    if (targetFieldActive(field, next)) next[field.name] ??= targetDefaults.value[field.name]
  }
}
function completeTarget() {
  const next = { ...overrides.value }
  fillTarget(next)
  savePanel(next)
}
function toggleTarget() {
  const next = { ...overrides.value }
  if (targetOverridden.value) {
    for (const field of targetFields.value) delete next[field.name]
  } else {
    fillTarget(next)
  }
  savePanel(next)
}
function savePanel(next: Record<string, unknown>) {
  configs.value = { ...configs.value, [selected.value]: next }
  queueSave()
}
function queueSave() {
  const planId = props.planId,
    day = props.day,
    current = revision
  const snapshot = JSON.parse(JSON.stringify(configs.value)) as Record<
    string,
    Record<string, unknown>
  >
  pending = enqueue(async () => {
    try {
      await saveOkwwPlan(planId, day, snapshot)
      if (current === revision) error.value = ''
      return true
    } catch (reason) {
      if (current === revision) error.value = String(reason)
      return false
    }
  })
}
function discardAndBack() {
  pending = Promise.resolve(true)
  navigateTo('/plans', { query: { planId: props.planId } })
}
function retrySave() {
  queueSave()
}
async function saveAll() {
  return await pending
}
defineExpose({ saveAll })
onBeforeRouteLeave(saveAll)
onBeforeRouteUpdate(saveAll)
async function load() {
  const current = ++revision
  loading.value = true
  loadFailed.value = false
  error.value = ''
  panels.value = []
  try {
    const data = await readOkwwPlan(props.planId, props.day, locale.value)
    if (current !== revision) return
    panels.value = data
    configs.value = Object.fromEntries(panels.value.map(panel => [panel.filename, panel.overrides]))
    selected.value = panels.value[0]?.filename ?? ''
    pending = Promise.resolve(true)
  } catch (reason) {
    if (current === revision) {
      loadFailed.value = true
      error.value = String(reason)
    }
  } finally {
    if (current === revision) loading.value = false
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
