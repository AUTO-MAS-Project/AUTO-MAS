<template>
  <a-space-compact block size="large">
    <a-input
      v-model:value="value"
      :placeholder="placeholder"
      size="large"
      class="path-picker-input"
      readonly
      aria-readonly="true"
      :disabled="disabled"
    />
    <a-button size="large" :disabled="disabled" @click="emit('pick')">
      <template #icon>
        <FolderOpenOutlined v-if="mode === 'folder'" />
        <FileOutlined v-else />
      </template>
      {{ pickLabel }}
    </a-button>
  </a-space-compact>
</template>

<script setup lang="ts">
import { FileOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'

defineProps<{
  mode: 'file' | 'folder'
  placeholder: string
  pickLabel: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  pick: []
}>()

const value = defineModel<string | null>({ required: true })
</script>

<style scoped>
.path-picker-input {
  min-width: 0;
}
</style>
