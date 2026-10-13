<script setup lang="ts">
import PluginDeclarativeField, { type DeclarativeHint } from './PluginDeclarativeField.vue'

defineProps<{
  groups: Array<{ name: string; hints: DeclarativeHint[] }>
  values: Record<string, Record<string, unknown>>
  runningKey?: string | null
}>()

const emit = defineEmits<{
  'update:value': [group: string, field: string, value: unknown]
  action: [group: string, hint: DeclarativeHint]
}>()
</script>

<template>
  <section class="plugin-form" :aria-label="$t('plugins.settingsForm')">
    <section v-for="group in groups" :key="group.name" class="plugin-form-group">
      <a-divider orientation="left">{{ group.name }}</a-divider>
      <div class="form-grid-24">
      <PluginDeclarativeField
        v-for="hint in group.hints"
        :key="`${group.name}.${hint.field}`"
        :group="group.name"
        :hint="hint"
        :value="values[group.name]?.[hint.field || '']"
        :loading="runningKey === `${group.name}.${hint.field}`"
        @update:value="emit('update:value', group.name, hint.field || '', $event)"
        @action="emit('action', group.name, hint)"
      />
      </div>
    </section>
  </section>
</template>

<style scoped>
.plugin-form-group + .plugin-form-group { margin-top: 24px; }
.plugin-form :deep(.ant-divider) { margin: 8px 0 16px; }
</style>
