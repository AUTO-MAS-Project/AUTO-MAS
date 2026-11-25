<script setup lang="ts">
import { computed, useId, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDeclarativeOptions } from '@/composables/useDeclarativeOptions'
import DeclarativeTable, { type DeclarativeTableHint } from '@/components/DeclarativeTable.vue'
import { fieldRuns, isWideField, tableColumnTypes } from '@/components/declarativeLayout'
import { SectionCard } from '@/components/ui'
import PluginDeclarativeField, { type DeclarativeHint } from './PluginDeclarativeField.vue'

const props = withDefaults(
  defineProps<{
    groups: Array<{ name: string; hints: DeclarativeHint[] }>
    tables?: DeclarativeTableHint[]
    errors?: Record<string, string>
    values: Record<string, Record<string, unknown>>
    runningKey?: string | null
    activeFields?: string[]
    uid: string
    namespace: string
    disabled?: boolean
  }>(),
  { tables: () => [], errors: () => ({}), runningKey: null, activeFields: () => [] }
)

const { t, te } = useI18n()
// 动态选项按当前插件配置、字段声明和依赖值查询。
const target = computed(() => ({
  ...props.values,
  uid: props.uid,
  ui: { hints: Object.fromEntries(props.groups.map(group => [group.name, group.hints])) },
}))
const { optionsFor, stateFor } = useDeclarativeOptions(target)
const options = (group: string, hint: DeclarativeHint) =>
  /* 取得字段静态或动态选项，并应用插件命名空间中的选项翻译。 */ optionsFor(group, hint).map(
    option => {
      // 为单个选项选择翻译标签，未提供词条时保留后端声明名称。
      const key = `${props.namespace}.${group}.${hint.field}.options.${option.value}`
      return { ...option, label: te(key) ? t(key) : option.label }
    }
  )

const emit = defineEmits<{
  'update:value': [group: string, field: string, value: unknown]
  action: [group: string, hint: DeclarativeHint, value: unknown]
}>()

const hintsByGroup = computed(
  () =>
    new Map(
      props.groups.map(group => [group.name, new Map(group.hints.map(hint => [hint.field, hint]))])
    )
)
const visibleTables = computed(() =>
  props.tables
    .map(table => ({
      ...table,
      rows: table.rows.filter(group =>
        table.columns.some(field => hintsByGroup.value.get(group)?.has(field))
      ),
      columns: table.columns.filter(field =>
        table.rows.some(group => hintsByGroup.value.get(group)?.has(field))
      ),
    }))
    .filter(table => table.rows.length && table.columns.length)
)
const remainingGroups = computed(() =>
  Array.from(hintsByGroup.value, ([name, fields]) => ({
    name,
    hints: [...fields.values()].filter(
      hint =>
        !visibleTables.value.some(
          table => table.rows.includes(name) && table.columns.includes(hint.field ?? '')
        )
    ),
  })).filter(group => group.hints.length)
)

const form = useTemplateRef<HTMLElement>('form')
const formId = useId()
const getContainer = () => form.value?.closest<HTMLElement>('.plugin-settings-content') ?? window
function sectionTitle(name: string) {
  const key = `${props.namespace}.${name}`
  return te(`${key}.label`) ? t(`${key}.label`) : te(key) ? t(key) : name
}
const sections = computed(() => [
  ...visibleTables.value.map((table, index) => ({
    id: `${formId}-table-${index}`,
    key: `table-${index}-${table.key ?? ''}`,
    title: table.key ? sectionTitle(table.key) : t('core.plugins.table'),
    badge: t('core.plugins.table'),
    table,
    columnTypes: tableColumnTypes(table, (group, field) =>
      hintsByGroup.value.get(group)?.get(field)
    ),
  })),
  ...remainingGroups.value.map((group, index) => ({
    id: `${formId}-group-${index}`,
    key: `group-${group.name}`,
    title: sectionTitle(group.name),
    badge: group.hints.length,
    group,
    runs: fieldRuns(group.hints),
  })),
])
const navItems = computed(() =>
  sections.value.map(({ id, title, badge }) => ({
    key: id,
    href: `#${id}`,
    title,
    badge,
  }))
)

function fieldBindings(group: string, hint: DeclarativeHint) {
  const field = hint.field ?? ''
  const key = `${group}.${field}`
  const state = stateFor(group, hint)
  return {
    group,
    hint,
    namespace: props.namespace,
    value: props.values[group]?.[field],
    options: options(group, hint),
    disabled: props.disabled,
    disabledReason: hint.editable === false ? t('core.plugins.readOnly') : undefined,
    loading:
      hint.state === 'busy' ||
      props.activeFields.includes(key) ||
      props.runningKey === key ||
      state?.loading.value,
    error: props.errors[key] || state?.error.value || undefined,
    retry: state?.error.value ? state.execute : undefined,
    onAction: (value: unknown) => emit('action', group, hint, value),
  }
}
</script>

<template>
  <section
    ref="form"
    class="plugin-form"
    :class="{ 'with-nav': sections.length >= 3 }"
    :aria-label="t('core.plugins.settingsForm')"
  >
    <nav
      v-if="sections.length >= 3"
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
      <template v-for="section in sections" :key="section.key">
        <DeclarativeTable
          v-if="'table' in section"
          :id="section.id"
          :table="section.table"
          :column-types="section.columnTypes"
          :title="section.title"
          :namespace="namespace"
          @update:value="(group, field, value) => emit('update:value', group, field, value)"
        >
          <template #cell="{ group, field, update }">
            <PluginDeclarativeField
              v-if="hintsByGroup.get(group)?.has(field)"
              v-bind="fieldBindings(group, hintsByGroup.get(group)!.get(field)!)"
              table-cell
              @update:value="update"
            />
          </template>
        </DeclarativeTable>
        <SectionCard v-else :id="section.id" variant="card" :title="section.title">
          <div
            v-for="run in section.runs"
            :key="run.hints[0]?.field"
            :class="run.tiles ? 'declarative-switch-grid' : 'declarative-field-grid'"
          >
            <PluginDeclarativeField
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
