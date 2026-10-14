<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons-vue'
import type { ComponentHint } from '@/api'
import DeclarativeControl from '@/components/DeclarativeControl.vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import { useDeclarativeOptions } from '@/composables/useDeclarativeOptions'
import GeneralConfigModeSelector from '@/components/GeneralConfigModeSelector.vue'
import { configurationFieldSpan } from '@/utils/declarativeLayout'
import type { ConfigData, ManagedScript, ManagedUser } from '../managedScriptTypes'

const props = defineProps<{
  script: ManagedScript
  user?: ManagedUser
  pending: Record<string, boolean>
  busy: boolean
  configurable: boolean
  configLoading: boolean
  save: (
    script: ManagedScript,
    section: string,
    field: string,
    value: unknown,
    user?: ManagedUser
  ) => Promise<boolean>
}>()
const emit = defineEmits<{ back: []; configure: [] }>()
const { t, te } = useI18n()
const drafts = reactive<Record<string, unknown>>({})
const target = computed(() => props.user ?? props.script)
const { optionsFor: declaredOptions, stateFor } = useDeclarativeOptions(target)
const groups = computed(() =>
  Object.entries(target.value.ui.hints ?? {}).filter(([, hints]) => hints.length)
)
const keyFor = (section: string, field: string) =>
  `${props.script.uid}:${props.user?.uid ?? 'script'}:${section}:${field}`
const valueFor = (section: string, field: string) => {
  const key = keyFor(section, field)
  if (Object.prototype.hasOwnProperty.call(drafts, key)) return drafts[key]
  return (target.value[section] as ConfigData | undefined)?.[field]
}
const labelFor = (field: string) =>
  te(`scripts.field.${field}`) ? t(`scripts.field.${field}`) : field.replace(/_/g, ' ')
const sectionFor = (section: string) => {
  const keys: Record<string, string> = {
    info: 'scripts.configTitle',
    run: 'scripts.runTitle',
    task: 'scripts.taskTitle',
    notify: 'scripts.notifyTitle',
    data: 'scripts.dataTitle',
  }
  return keys[section] ? t(keys[section]) : section
}
const deferred = (hint: ComponentHint) =>
  ['input', 'number', 'path'].includes(hint.component ?? 'input')
const save = async (section: string, hint: ComponentHint, value: unknown) => {
  const field = hint.field
  if (!field) return
  if (await props.save(props.script, section, field, value, props.user))
    delete drafts[keyFor(section, field)]
}
const update = (section: string, hint: ComponentHint, value: unknown) => {
  if (!hint.field) return
  if (deferred(hint)) drafts[keyFor(section, hint.field)] = value
  else void save(section, hint, value)
}
const blur = (section: string, hint: ComponentHint) => {
  const key = keyFor(section, hint.field ?? '')
  if (Object.prototype.hasOwnProperty.call(drafts, key)) void save(section, hint, drafts[key])
}
const pickPath = async (section: string, hint: ComponentHint) => {
  if (!window.electronAPI) return
  try {
    const selected =
      hint.path_kind !== 'folder'
        ? ((await window.electronAPI.selectFile())?.[0] ?? null)
        : await window.electronAPI.selectFolder()
    if (selected) {
      drafts[keyFor(section, hint.field ?? '')] = selected
      await save(section, hint, selected)
    }
  } catch {
    message.error(t('comp.couldNotPickFile'))
  }
}
const displayValue = (value: unknown) =>
  value != null && typeof value === 'object' ? JSON.stringify(value) : String(value ?? '-')
const optionsFor = (section: string, hint: ComponentHint) =>
  declaredOptions(section, hint).map(option => ({
    ...option,
    label:
      !hint.endpoint && te(`scripts.option.${option.value}`)
        ? t(`scripts.option.${option.value}`)
        : option.label,
  }))
const configModeOptions = computed(() => [
  {
    label: t('edit.script'),
    value: '脚本' as const,
    title: t('edit.script'),
    description: t('edit.useSharedScriptLevel'),
    icon: 'file' as const,
  },
  {
    label: t('edit.user'),
    value: '用户' as const,
    title: t('edit.user'),
    description: t('edit.useThisUserS'),
    icon: 'database' as const,
  },
  {
    label: t('edit.directControl'),
    value: '直控' as const,
    title: t('edit.directControl'),
    description: t('edit.nativeConfigSourceDescription'),
    icon: 'setting' as const,
  },
])
const infoHints = computed(() => groups.value.find(([section]) => section === 'info')?.[1] ?? [])
const hasModeField = computed(() => infoHints.value.some(hint => hint.field === 'mode'))
const hasQuickConfigField = computed(() =>
  infoHints.value.some(hint => hint.field === 'if_quick_config')
)
const modeHint = computed(() => infoHints.value.find(hint => hint.field === 'mode'))
const quickConfigHint = computed(() =>
  infoHints.value.find(hint => hint.field === 'if_quick_config')
)
const modeValue = computed(() => (valueFor('info', 'mode') as string) || '脚本')
const quickConfigValue = computed(() => valueFor('info', 'if_quick_config') as boolean)
const updateSpecial = (field: 'mode' | 'if_quick_config', value: unknown) => {
  void save(
    'info',
    { field, component: field === 'mode' ? 'select' : 'bool' } as ComponentHint,
    value
  )
}
const editHints = (hints: ComponentHint[]) =>
  hints.filter(
    hint =>
      hint.field &&
      hint.field !== 'mode' &&
      hint.field !== 'if_quick_config' &&
      hint.field !== 'tags'
  )
const hintTip = (field: string) =>
  te(`scripts.fieldTip.${field}`) ? t(`scripts.fieldTip.${field}`) : ''
</script>

<template>
  <div class="script-edit-header">
    <a-breadcrumb>
      <a-breadcrumb-item
        ><a @click="emit('back')">{{ t('scripts.title') }}</a></a-breadcrumb-item
      >
      <a-breadcrumb-item>{{ String(script.info.name || script.type) }}</a-breadcrumb-item>
      <a-breadcrumb-item v-if="user">{{ String(user.info.name || user.type) }}</a-breadcrumb-item>
    </a-breadcrumb>
    <a-button size="large" @click="emit('back')"
      ><template #icon><ArrowLeftOutlined /></template>{{ t('edit.back') }}</a-button
    >
  </div>
  <a-card class="config-card" :title="user ? t('comp.editUser') : t('comp.editScript')">
    <template #extra
      ><a-button
        v-if="configurable"
        type="primary"
        ghost
        :loading="configLoading"
        :disabled="busy"
        @click="emit('configure')"
        ><template #icon><SettingOutlined /></template>{{ t('scripts.configureNative') }}</a-button
      ></template
    >
    <section v-for="[section, hints] in groups" :key="section" class="form-section">
      <div class="section-header">
        <h3>{{ sectionFor(section) }}</h3>
      </div>
      <a-form layout="vertical">
        <GeneralConfigModeSelector
          v-if="section === 'info' && user && hasModeField"
          :model-value="modeValue"
          :options="configModeOptions"
          :quick-config="hasQuickConfigField ? quickConfigValue : undefined"
          :disabled="busy || modeHint?.editable === false"
          :quick-config-disabled="quickConfigHint?.editable === false"
          :saving="pending[keyFor('info', 'mode')] || pending[keyFor('info', 'if_quick_config')]"
          :alert-message="t('edit.configSourceHintBase')"
          @change="updateSpecial('mode', $event)"
          @quick-config-change="updateSpecial('if_quick_config', $event)"
        />
        <div class="form-grid-24">
          <div
            v-for="hint in editHints(hints)"
            :key="hint.field"
            class="form-grid-24__item form-item-vertical"
            :style="{ '--field-span': configurationFieldSpan(hint.component) }"
          >
            <div class="form-label-wrapper">
              <span class="form-label">{{ labelFor(hint.field ?? '') }}</span
              ><a-tooltip v-if="hintTip(hint.field ?? '')" :title="hintTip(hint.field ?? '')"
                ><QuestionCircleOutlined class="help-icon"
              /></a-tooltip>
            </div>
            <span v-if="hint.editable === false" class="readonly-value">{{
              displayValue(valueFor(section, hint.field ?? ''))
            }}</span>
            <DeclarativeControl
              v-else
              :component="hint.component"
              :label="labelFor(hint.field ?? '')"
              :model-value="valueFor(section, hint.field ?? '')"
              :disabled="busy || pending[keyFor(section, hint.field ?? '')]"
              :loading="
                pending[keyFor(section, hint.field ?? '')] || stateFor(section, hint)?.loading.value
              "
              :secret="hint.secret"
              :path-kind="hint.path_kind"
              :min="hint.min"
              :max="hint.max"
              :options="optionsFor(section, hint)"
              :multiple="hint.multiple"
              @update:model-value="update(section, hint, $event)"
              @blur="blur(section, hint)"
              @pick="pickPath(section, hint)"
            />
            <ApiRetryAlert
              :error="stateFor(section, hint)?.error.value"
              :loading="stateFor(section, hint)?.loading.value"
              @retry="stateFor(section, hint)?.execute()"
            />
          </div>
        </div>
      </a-form>
    </section>
  </a-card>
</template>

<style scoped>
.script-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 32px;
  padding: 0 8px;
}
.config-card {
  border-radius: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.08),
    0 1px 3px rgba(0, 0, 0, 0.1);
}
.config-card :deep(.ant-card-head) {
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 24px 32px;
}
.config-card :deep(.ant-card-head-title) {
  font-size: 24px;
  font-weight: 700;
}
.config-card :deep(.ant-card-body) {
  padding: 32px;
}
.form-section:last-child {
  margin-bottom: 0;
}
.readonly-value {
  min-height: 40px;
  display: flex;
  align-items: center;
  color: var(--ant-color-text-secondary);
  overflow-wrap: anywhere;
}
@media (max-width: 768px) {
  .config-card :deep(.ant-card-head),
  .config-card :deep(.ant-card-body) {
    padding: 16px;
  }
  .script-edit-header {
    padding: 0;
    margin-bottom: 24px;
  }
}
</style>
