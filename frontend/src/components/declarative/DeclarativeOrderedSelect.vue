<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDownOutlined, ArrowUpOutlined, CloseOutlined } from '@ant-design/icons-vue'

type Value = string | number | boolean
const props = defineProps<{
  selected: Value[]
  options: Array<{ value?: Value; label?: string }>
  size: 'middle' | 'large'
  disabled: boolean
}>()
const emit = defineEmits<{ change: [values: Value[]] }>()
const { t } = useI18n()
const remaining = computed(() =>
  props.options.flatMap(({ value, label }, index) =>
    value === undefined || props.selected.includes(value)
      ? []
      : [{ label: label ?? String(value), value: index }]
  )
)
const add = (index: number) => {
  const value = props.options[index]?.value
  if (value !== undefined && !props.selected.includes(value))
    emit('change', [...props.selected, value])
}
const move = (index: number, offset: number) => {
  const next = props.selected.slice()
  const [value] = next.splice(index, 1)
  next.splice(index + offset, 0, value!)
  emit('change', next)
}
</script>

<template>
  <div class="ordered-select">
    <ol v-if="selected.length">
      <li
        v-for="(value, index) in selected"
        :key="`${typeof value}:${value}`"
        class="ordered-select-item"
      >
        <span class="order-badge" aria-hidden="true">{{ index + 1 }}</span>
        <span class="order-label">{{
          options.find(option => option.value === value)?.label ?? value
        }}</span>
        <a-button
          size="small"
          type="text"
          :disabled="disabled || index === 0"
          :aria-label="t('core.setting.tray.moveUp')"
          @click="move(index, -1)"
          ><ArrowUpOutlined
        /></a-button>
        <a-button
          size="small"
          type="text"
          :disabled="disabled || index === selected.length - 1"
          :aria-label="t('core.setting.tray.moveDown')"
          @click="move(index, 1)"
          ><ArrowDownOutlined
        /></a-button>
        <a-button
          size="small"
          type="text"
          :disabled="disabled"
          :aria-label="t('core.comp.delete')"
          @click="
            emit(
              'change',
              selected.filter((_, i) => i !== index)
            )
          "
          ><CloseOutlined
        /></a-button>
      </li>
    </ol>
    <a-select
      :size="size"
      :value="null"
      :options="remaining"
      :disabled="disabled || !remaining.length"
      :placeholder="t('core.plugins.addOption')"
      @update:value="add"
    />
  </div>
</template>

<style scoped>
.ordered-select,
.ordered-select ol {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.ordered-select {
  padding: 8px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius);
  background: var(--ant-color-fill-quaternary);
}
.ordered-select ol {
  margin: 0;
  padding: 0;
  list-style: none;
}
.ordered-select-item {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 36px;
  min-width: 0;
  padding: 0 6px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius);
  background: var(--ant-color-bg-container);
}
.order-badge {
  min-width: 22px;
  border-radius: var(--ant-border-radius-sm);
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.order-label {
  flex: 1;
  margin-inline: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ordered-select :deep(.ant-select-selector) {
  border-style: dashed;
}
</style>
