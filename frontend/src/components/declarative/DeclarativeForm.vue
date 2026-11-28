<script setup lang="ts">
import { computed, useId, useTemplateRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { UiSection, UiStep } from '@/api'
import {
  useDeclarativeOptions,
  type DeclarativeHint,
  type DeclarativeOptions,
} from '@/composables/useDeclarativeOptions'
import DeclarativeTable, { type DeclarativeTableHint } from './DeclarativeTable.vue'
import { declarativeLayout, isWideField, useDeclarativeSteps } from './declarativeLayout'
import { SectionCard } from '@/components/ui'
import type { SettingsChange } from '@/views/plugins/settings/usePluginSettingsDraft'
import DeclarativeField from './DeclarativeField.vue'
import { createDeclarativeI18n, type DeclarativeI18nScope } from './declarativeI18n'

const props = withDefaults(
  defineProps<{
    groups: Array<{ name: string; hints: DeclarativeHint[] }>
    tables?: DeclarativeTableHint[]
    steps?: UiStep[]
    sections?: Record<string, UiSection>
    pluginName?: string | null
    options?: DeclarativeOptions
    blockMode?: boolean
    setupMode?: boolean
    submitDisabled?: boolean
    submitting?: boolean
    errors?: Record<string, string>
    values: Record<string, Record<string, unknown>>
    runningKey?: string | null
    activeFields?: string[]
    uid: string
    namespace: string
    scope: DeclarativeI18nScope
    disabled?: boolean
  }>(),
  {
    tables: () => [],
    steps: () => [],
    sections: () => ({}),
    pluginName: null,
    options: undefined,
    errors: () => ({}),
    runningKey: null,
    activeFields: () => [],
  }
)

const { t, te, locale } = useI18n()
const i18n = computed(() =>
  createDeclarativeI18n(t, te, locale.value, props.namespace, props.scope)
)
const emit = defineEmits<{
  'update:value': [group: string, field: string, value: unknown]
  'update:optionsInvalid': [invalid: boolean]
  action: [group: string, hint: DeclarativeHint, value: unknown, owner?: SettingsChange]
  finish: []
}>()
// 动态选项按当前插件配置、字段声明和依赖值查询。
const target = computed(() => ({
  ...props.values,
  uid: props.uid,
  pluginName: props.pluginName,
  ui: { hints: Object.fromEntries(props.groups.map(group => [group.name, group.hints])) },
}))
const { optionsFor, stateFor, validationErrors, optionsInvalid } =
  props.options ?? useDeclarativeOptions(target)
if (!props.options)
  watch(optionsInvalid, invalid => emit('update:optionsInvalid', invalid), { immediate: true })
const translatedOptions = (group: string, hint: DeclarativeHint) =>
  optionsFor(group, hint).map(option => ({
    ...option,
    // 缺少词条时保留动态选项的后端名称。
    label: i18n.value.config(`${group}.${hint.field}.options.${option.value}`) ?? option.label,
  }))

const layout = computed(() =>
  declarativeLayout(props.groups, props.tables, props.steps, props.sections)
)
const { current, collapsed } = useDeclarativeSteps(
  layout,
  () => props.uid,
  () => props.errors
)
const stepItems = computed(() =>
  layout.value.steps.map(step => ({
    title: i18n.value.config(`steps.${step.key}.label`) ?? (step.title || step.key),
    disabled: props.disabled,
  }))
)
const wizard = computed(() => !props.blockMode && (props.setupMode || stepItems.value.length > 1))

const form = useTemplateRef<HTMLElement>('form')
const formId = useId()
const getContainer = () => form.value?.closest<HTMLElement>('.plugin-settings-content') ?? window
function sectionTitle(name: string) {
  return i18n.value.config(`${name}.label`) ?? name
}
const cards = computed(() =>
  (props.blockMode ? layout.value.cards : (layout.value.steps[current.value]?.cards ?? [])).map(
    (card, index) => {
      const name = 'group' in card ? card.group.name : card.table.key
      return {
        ...card,
        id: `${formId}-section-${index}`,
        title: name ? sectionTitle(name) : t('core.plugins.table'),
        badge: 'group' in card ? card.group.hints.length : t('core.plugins.table'),
      }
    }
  )
)
const navItems = computed(() =>
  cards.value.map(({ id, title, badge }) => ({
    key: id,
    href: `#${id}`,
    title,
    badge,
  }))
)

function actionBusy(group: string, hint: DeclarativeHint) {
  const key = `${group}.${hint.field}`
  return hint.state === 'busy' || props.activeFields.includes(key) || props.runningKey === key
}

function fieldBindings(group: string, hint: DeclarativeHint) {
  const field = hint.field ?? ''
  const key = `${group}.${field}`
  const state = stateFor(group, hint)
  const action = layout.value.actions.get(key)
  return {
    group,
    hint,
    namespace: props.namespace,
    scope: props.scope,
    value: props.values[group]?.[field],
    options: translatedOptions(group, hint),
    disabled: props.disabled,
    disabledReason: hint.editable === false ? t('core.plugins.readOnly') : undefined,
    loading: actionBusy(group, hint) || state?.loading.value,
    error: props.errors[key] || validationErrors.value[key] || state?.error.value || undefined,
    retry: state?.error.value ? state.execute : undefined,
    onAction: (value: unknown) => emit('action', group, hint, value),
    inlineAction: action && {
      ...action,
      options: translatedOptions(action.group, action.hint),
      loading: actionBusy(action.group, action.hint),
      run: (value: unknown) => emit('action', action.group, action.hint, value, { group, field }),
    },
  }
}
</script>

<template>
  <section
    ref="form"
    class="plugin-form"
    :class="{ 'with-nav': cards.length >= 3 }"
    :aria-label="t('core.plugins.settingsForm')"
  >
    <nav
      v-if="cards.length >= 3"
      class="section-nav"
      :aria-label="t('core.setting.navigation.ariaLabel')"
    >
      <a-anchor
        :items="navItems"
        :affix="false"
        :get-container="getContainer"
        :get-current-anchor="(href: string) => href || navItems[0]?.href || ''"
        :target-offset="16"
        @click.prevent
      >
        <template #customTitle="{ title, badge }">
          <span class="nav-entry"
            ><span>{{ title }}</span
            ><small>{{ badge }}</small></span
          >
        </template>
      </a-anchor>
    </nav>
    <div class="section-list">
      <a-steps
        v-if="!blockMode && stepItems.length > 1"
        v-model:current="current"
        :items="stepItems"
        size="small"
      />
      <template v-for="section in cards" :key="section.key">
        <DeclarativeTable
          v-if="'table' in section"
          v-model:collapsed="collapsed[section.key]"
          :collapsible="section.collapsible"
          :id="section.id"
          :table="section.table"
          :column-types="section.columnTypes"
          :title="section.title"
          :namespace="namespace"
          :scope="scope"
          @update:value="(group, field, value) => emit('update:value', group, field, value)"
        >
          <template #cell="{ group, field, update }">
            <DeclarativeField
              v-if="layout.hintFor(group, field)"
              v-bind="fieldBindings(group, layout.hintFor(group, field)!)"
              table-cell
              @update:value="update"
            />
          </template>
        </DeclarativeTable>
        <SectionCard
          v-else
          :id="section.id"
          v-model:collapsed="collapsed[section.key]"
          variant="card"
          :title="section.title"
          :collapsible="section.collapsible"
        >
          <div
            v-for="run in section.runs"
            :key="run.hints[0]?.field"
            :class="run.tiles ? 'declarative-switch-grid' : 'declarative-field-grid'"
          >
            <DeclarativeField
              v-for="hint in run.hints"
              :key="hint.field"
              v-bind="fieldBindings(section.group.name, hint)"
              :tile="run.tiles"
              :class="{
                wide: isWideField(hint),
                'full-width': section.group.hints.length === 1 && isWideField(hint),
              }"
              @update:value="emit('update:value', section.group.name, hint.field ?? '', $event)"
            />
          </div>
        </SectionCard>
      </template>
      <a-flex
        v-if="!blockMode && (wizard || $slots.actions)"
        justify="end"
        align="center"
        gap="small"
      >
        <slot name="actions" :wizard="wizard" />
        <template v-if="wizard">
          <a-button
            v-if="stepItems.length > 1"
            :disabled="disabled || current === 0"
            @click="current--"
          >
            {{ t('core.edit.previousStep') }}
          </a-button>
          <a-button
            v-if="current < stepItems.length - 1"
            type="primary"
            :disabled="disabled"
            @click="current++"
          >
            {{ t('core.edit.next') }}
          </a-button>
          <a-button
            v-else
            type="primary"
            :disabled="disabled || optionsInvalid || submitDisabled"
            :loading="submitting"
            @click="emit('finish')"
          >
            {{ t('core.taskboard.complete') }}
          </a-button>
        </template>
      </a-flex>
      <slot v-if="!blockMode" name="footer" :wizard="wizard" />
    </div>
  </section>
</template>

<style scoped>
.plugin-form {
  width: 100%;
  max-width: 1120px;
  margin-inline: auto;
}
.plugin-form.with-nav {
  display: grid;
  grid-template-columns: 188px minmax(0, 1fr);
  align-items: start;
  gap: 20px;
  max-width: none;
}
.section-nav {
  position: sticky;
  top: 16px;
  padding: 12px 8px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius-lg);
  background: var(--ant-color-bg-container);
  box-shadow: var(--ant-box-shadow-tertiary);
}
.nav-entry {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.nav-entry > span {
  overflow: hidden;
  text-overflow: ellipsis;
}
.nav-entry small {
  padding-inline: 6px;
  border-radius: var(--ant-border-radius-sm);
  background: var(--ant-color-fill-quaternary);
}
.section-list {
  min-width: 0;
}
.section-list > .ant-steps {
  margin-bottom: 16px;
}
.declarative-switch-grid,
.declarative-field-grid {
  display: grid;
  align-items: start;
  gap: 12px;
  padding-bottom: 12px;
}
.declarative-switch-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.declarative-field-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.declarative-field-grid .wide {
  grid-column: span 2;
}
.declarative-field-grid .full-width {
  grid-column: 1 / -1;
}
@media (max-width: 1100px) {
  .declarative-switch-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 1024px) {
  .declarative-field-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 960px) {
  .plugin-form.with-nav {
    display: block;
  }
  .section-nav {
    display: none;
  }
}
@media (max-width: 640px) {
  .declarative-switch-grid,
  .declarative-field-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .declarative-field-grid .wide {
    grid-column: 1 / -1;
  }
}
</style>
