<template>
  <a-checkbox-group
    class="native-checkboxes"
    :value="value"
    :disabled="disabled"
    :options="options"
    @change="emit('change', $event)"
  />
</template>

<script setup lang="ts">
defineProps<{
  value: string[]
  disabled?: boolean
  options: { value: string; label: string }[]
}>()

const emit = defineEmits<{ change: [values: string[]] }>()
</script>

<style scoped>
.native-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.native-checkboxes :deep(.ant-checkbox-wrapper) {
  margin-inline-start: 0;
  max-width: 100%;
  white-space: normal;
}
</style>
