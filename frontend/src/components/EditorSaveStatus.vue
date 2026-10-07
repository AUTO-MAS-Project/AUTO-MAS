<template>
  <div v-if="visible" class="editor-save-status">
    <SaveStateIndicator :state="state" />
    <div v-if="pendingFields.length > 0" class="editor-save-status__fields">
      <span v-for="field in pendingFields" :key="field.key" class="editor-save-status__field">
        <span class="editor-save-status__field-name">{{ field.key }}</span>
        <SaveStateIndicator :state="field.state" />
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import SaveStateIndicator from '@/components/SaveStateIndicator.vue'
import type { SaveState } from '@/utils/saveState'

defineOptions({ name: 'EditorSaveStatus' })

const props = withDefaults(
  defineProps<{
    /** 页面级保存状态（useSaveQueue 的 state） */
    state: SaveState
    /** 字段级保存状态（useSaveQueue 的 fieldStates） */
    fieldStates?: Record<string, SaveState>
  }>(),
  { fieldStates: () => ({}) }
)

/** 已经落盘或从未改动过的字段不再占位，避免页头被正常状态刷屏 */
const settled: ReadonlySet<SaveState> = new Set<SaveState>(['idle', 'saved'])

const pendingFields = computed(() =>
  Object.entries(props.fieldStates)
    .filter(([, fieldState]) => !settled.has(fieldState))
    .map(([key, fieldState]) => ({ key, state: fieldState }))
    .sort((a, b) => a.key.localeCompare(b.key))
)

const visible = computed(() => props.state !== 'idle' || pendingFields.value.length > 0)
</script>

<style scoped>
.editor-save-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.editor-save-status__fields {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.editor-save-status__field {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.editor-save-status__field-name {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
</style>
