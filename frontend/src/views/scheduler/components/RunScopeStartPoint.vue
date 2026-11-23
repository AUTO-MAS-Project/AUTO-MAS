<template>
  <div class="pick-heading">
    <span :id="labelId">{{ t('core.scheduler.scope.startHeading') }}</span>
    <a-button size="small" type="text" @click="emit('back')">{{ t('core.comp.back') }}</a-button>
  </div>
  <a-radio-group
    ref="choices"
    v-model:value="startUid"
    class="pick-list"
    role="radiogroup"
    :name="labelId"
    :aria-labelledby="labelId"
    :disabled="disabled"
  >
    <a-radio
      v-for="(row, i) in rows"
      :key="row.entry.uid"
      :value="row.entry.uid"
      :aria-label="startLabel(row)"
      class="pick-row"
      :class="{ first: i === startIndex, earlier: i < startIndex }"
    >
      <span class="pick-content">
        <span class="num">{{ String(i + 1).padStart(2, '0') }}</span>
        <span class="name">{{ row.entry.name || row.entry.scriptId }}</span>
        <span v-if="i === startIndex" class="status first-status">
          <FlagOutlined aria-hidden="true" />
          {{
            row.entry.selection === 'none' || row.unavailable
              ? t('core.scheduler.scope.boundary')
              : t('core.scheduler.scope.runsFirst')
          }}
        </span>
        <span v-else-if="row.entry.selection === 'none'" class="status">{{
          t('core.scheduler.scope.unchecked')
        }}</span>
        <span v-else-if="i < startIndex" class="status">{{ t('core.history.skipped') }}</span>
        <span v-else-if="row.unavailable" class="status">{{
          t('core.scheduler.scope.unavailable')
        }}</span>
      </span>
    </a-radio>
  </a-radio-group>
  <footer v-if="startRow" class="pick-footer">
    <div role="status" aria-atomic="true">
      <strong>{{ startLabel(startRow) }}</strong>
      <small>{{
        startIndex
          ? t('core.scheduler.scope.skippedBefore', { count: startIndex })
          : t('core.scheduler.scope.noEarlier')
      }}</small>
    </div>
    <a-button size="small" :disabled="disabled" @click="emit('apply', startIndex)">
      {{ t('core.scheduler.scope.applyStart') }}
    </a-button>
  </footer>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, useId, useTemplateRef } from 'vue'
import { FlagOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { TaskScopeEntry } from '@/composables/taskSelection'

type Row = { entry: TaskScopeEntry; unavailable: boolean }
const props = defineProps<{ rows: Row[]; disabled?: boolean }>()
const emit = defineEmits<{ apply: [index: number]; back: [] }>()
const { t } = useI18n()
const labelId = useId()
const choices = useTemplateRef<{ $el: HTMLElement }>('choices')
const initial = props.rows.find(
  ({ entry, unavailable }) => entry.selection !== 'none' && !unavailable
)
const startUid = ref((initial ?? props.rows[0])?.entry.uid)
const startIndex = computed(() => props.rows.findIndex(row => row.entry.uid === startUid.value))
const startRow = computed(() => props.rows[startIndex.value])

onMounted(() => choices.value?.$el.querySelector<HTMLInputElement>('input:checked')?.focus())

function startLabel({ entry, unavailable }: Row) {
  const name = entry.name || entry.scriptId
  if (entry.selection === 'none') return t('core.scheduler.scope.startUnchecked', { name })
  if (unavailable) return t('core.scheduler.scope.startUnavailable', { name })
  return t('core.scheduler.scope.startIncluded', { name })
}
</script>

<style scoped>
.pick-heading,
.pick-footer {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-inline: 18px;
}
.pick-heading {
  min-height: 36px;
  background: var(--ant-color-fill-quaternary);
  border-block: 1px solid var(--ant-color-border-secondary);
  font-weight: 500;
}
.pick-heading .ant-btn {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
.pick-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 4px 0;
}
.pick-row {
  min-height: 38px;
  margin: 0;
  padding: 3px 18px;
  align-items: center;
  width: 100%;
}
.pick-row > :deep(span:last-child) {
  min-width: 0;
  padding-inline: 12px 0;
  flex: 1;
}
.pick-row:hover {
  background: var(--ant-color-fill-quaternary);
}
.pick-row.first {
  background: var(--ant-color-primary-bg);
  box-shadow: inset 0 2px var(--ant-color-primary);
}
.pick-content {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.num,
.status,
.pick-footer small {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
.num {
  flex: none;
  width: 18px;
  font-variant-numeric: tabular-nums;
}
.name,
.pick-footer strong {
  overflow-wrap: anywhere;
}
.status {
  flex: none;
  margin-inline-start: auto;
}
.earlier .name {
  color: var(--ant-color-text-secondary);
}
.first .name,
.pick-footer strong {
  font-weight: 600;
}
.first-status {
  color: var(--ant-color-link);
  font-weight: 500;
}
.pick-footer {
  border-top: 1px solid var(--ant-color-border-secondary);
  padding-block: 10px;
}
.pick-footer > div {
  min-width: 0;
}
.pick-footer strong,
.pick-footer small {
  display: block;
}
.pick-footer strong {
  font-size: 13px;
}
.pick-footer small {
  line-height: 18px;
}
</style>
