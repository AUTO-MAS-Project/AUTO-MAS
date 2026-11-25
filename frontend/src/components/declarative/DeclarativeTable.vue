<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TableHint } from '@/api'
import SectionCard from '@/components/ui/SectionCard.vue'

export type DeclarativeTableHint = Pick<TableHint, 'rows' | 'columns'> &
  Partial<Pick<TableHint, 'key' | 'transpose'>>

const props = withDefaults(
  defineProps<{
    table: DeclarativeTableHint
    namespace: string
    title: string
    columnTypes?: Record<string, string>
  }>(),
  { columnTypes: () => ({}) }
)
const emit = defineEmits<{ 'update:value': [group: string, field: string, value: unknown] }>()
const { t, te } = useI18n()

function label(key: string, groupAxis: boolean) {
  const keys = groupAxis
    ? []
    : props.table.rows.map(group => `${props.namespace}.${group}.${key}.label`)
  keys.push(`${props.namespace}.${key}.label`, `${props.namespace}.${key}`)
  const translated = keys.find(path => te(path))
  return translated ? t(translated) : key
}

const columns = computed(() => [
  { key: '', title: '', width: 108 },
  ...(props.table.transpose ? props.table.rows : props.table.columns).map(key => ({
    key,
    title: label(key, Boolean(props.table.transpose)),
    ...(props.columnTypes[key] === 'switch'
      ? { width: 84, align: 'center' as const }
      : props.columnTypes[key] === 'number'
        ? { width: 116 }
        : {}),
  })),
])
function cell(row: string, column: string) {
  const [group, field] = props.table.transpose ? [column, row] : [row, column]
  return { group, field, update: (value: unknown) => emit('update:value', group, field, value) }
}

const records = computed(() =>
  (props.table.transpose ? props.table.columns : props.table.rows).map(key => ({
    key,
    label: label(key, !props.table.transpose),
  }))
)
</script>

<template>
  <SectionCard variant="card" :title="title">
    <a-table
      :columns="columns"
      :data-source="records"
      :pagination="false"
      size="small"
      :scroll="{ x: 'max-content' }"
    >
      <template #bodyCell="{ column, record }">
        <strong v-if="column.key === ''">{{ record.label }}</strong>
        <slot v-else name="cell" v-bind="cell(record.key, column.key)" />
      </template>
    </a-table>
  </SectionCard>
</template>
