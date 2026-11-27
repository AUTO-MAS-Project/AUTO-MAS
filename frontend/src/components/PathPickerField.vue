<template>
  <a-space-compact block :size="size">
    <a-input
      v-model:value="value"
      :placeholder="placeholder"
      :size="size"
      class="path-picker-input"
      readonly
      aria-readonly="true"
      :disabled="disabled"
    />
    <slot name="before-pick" />
    <a-button :size="size" :disabled="disabled || pickDisabled" @click="emit('pick')">
      <template #icon>
        <FolderOpenOutlined v-if="mode === 'folder'" />
        <FileOutlined v-else />
      </template>
      {{ pickLabel }}
    </a-button>
    <slot name="after-pick" />
  </a-space-compact>
</template>

<script setup lang="ts" generic="T extends string | null | undefined">
import { FileOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'

const { size = 'large' } = defineProps<{
  size?: 'large' | 'middle'
  mode: 'file' | 'folder'
  placeholder: string
  pickLabel: string
  disabled?: boolean
  pickDisabled?: boolean
}>()

const emit = defineEmits<{
  pick: []
}>()

const value = defineModel<T>({ required: true })
</script>

<style scoped>
.path-picker-input {
  min-width: 0;
}
</style>
