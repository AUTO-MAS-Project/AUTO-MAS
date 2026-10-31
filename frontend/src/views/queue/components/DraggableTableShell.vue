<template>
  <div class="draggable-table-container">
    <div class="draggable-table-header">
      <slot name="header" />
    </div>

    <draggable
      v-model="items"
      :group="group"
      :item-key="itemKey"
      :animation="200"
      :disabled="disabled"
      ghost-class="draggable-table-ghost"
      chosen-class="draggable-table-chosen"
      drag-class="draggable-table-drag"
      handle=".drag-handle"
      class="draggable-container"
      @end="emit('end', $event)"
    >
      <template #item="{ element, index }">
        <div class="draggable-row" :class="{ 'row-busy': busy }">
          <slot name="row" :element="element" :index="index" />
        </div>
      </template>
    </draggable>

    <div v-if="modelValue.length === 0" class="empty-state">
      <NoData :image-style="{ height: '200px' }" :description="false" />
    </div>
  </div>
</template>

<script setup lang="ts" generic="T extends object">
import { computed } from 'vue'
import draggable from 'vuedraggable'

interface DragEndEvent {
  oldIndex?: number
  newIndex?: number
}

interface Props {
  modelValue: T[]
  itemKey: string
  disabled?: boolean
  busy?: boolean
  group?: string
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  busy: false,
  group: '',
})

const emit = defineEmits<{
  'update:modelValue': [items: T[]]
  end: [event: DragEndEvent]
}>()

const items = computed<T[]>({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})
</script>

<style scoped>
.draggable-table-container {
  width: 100%;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  overflow: hidden;
}

.draggable-table-header {
  display: flex;
  background-color: var(--ant-color-fill-quaternary);
  border-bottom: 1px solid var(--ant-color-border);
}

:slotted(.header-cell) {
  padding: 12px 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  text-align: center;
  border-right: 1px solid var(--ant-color-border);
}

:slotted(.header-cell:last-child) {
  border-right: none;
}

:slotted(.drag-cell) {
  width: 36px;
  min-width: 36px;
  max-width: 36px;
}

:slotted(.index-cell) {
  width: 80px;
  min-width: 80px;
  max-width: 80px;
}

:slotted(.actions-cell) {
  width: 120px;
  min-width: 120px;
  max-width: 120px;
}

.draggable-container {
  min-height: 60px;
}

.draggable-row {
  display: flex;
  align-items: center;
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border);
  transition: all 0.2s ease;
  cursor: default;
}

.draggable-row:last-child {
  border-bottom: none;
}

.draggable-row:hover {
  background-color: var(--ant-color-fill-quaternary);
}

.draggable-row.row-busy {
  cursor: not-allowed;
}

:slotted(.row-cell) {
  padding: 12px 16px;
  text-align: center;
  border-right: 1px solid var(--ant-color-border);
  display: flex;
  align-items: center;
  justify-content: center;
}

:slotted(.row-cell:last-child) {
  border-right: none;
}

:slotted(.row-cell.index-cell) {
  font-weight: 500;
  color: var(--ant-color-text-secondary);
}

.draggable-table-ghost {
  opacity: 0 !important;
  background: transparent !important;
  border-color: transparent !important;
  box-shadow: none !important;
}

.draggable-table-chosen {
  cursor: grabbing !important;
}

.draggable-table-drag {
  transform: rotate(3deg);
  opacity: 1 !important;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}

@media (max-width: 768px) {
  .draggable-row {
    flex-direction: column;
    align-items: stretch;
  }

  :slotted(.header-cell),
  :slotted(.row-cell) {
    width: 100% !important;
    min-width: auto !important;
    max-width: none !important;
    border-right: none;
    border-bottom: 1px solid var(--ant-color-border);
  }

  :slotted(.header-cell:last-child),
  :slotted(.row-cell:last-child) {
    border-bottom: none;
  }
}
</style>
