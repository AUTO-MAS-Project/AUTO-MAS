<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDeclarativeOptions } from '@/composables/useDeclarativeOptions'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import PluginDeclarativeField, { type DeclarativeHint } from './PluginDeclarativeField.vue'

const props = defineProps<{
  groups: Array<{ name: string; hints: DeclarativeHint[] }>
  values: Record<string, Record<string, unknown>>
  runningKey?: string | null
  uid: string
  namespace: string
  disabled?: boolean
}>()

const { t, te } = useI18n()
const target = computed(() => ({
  ...props.values,
  uid: props.uid,
  ui: { hints: Object.fromEntries(props.groups.map(group => [group.name, group.hints])) },
}))
const { optionsFor, stateFor } = useDeclarativeOptions(target)
const options = (group: string, hint: DeclarativeHint) =>
  optionsFor(group, hint).map(option => {
    const key = `${props.namespace}.${group}.${hint.field}.options.${option.value}`
    return { ...option, label: te(key) ? t(key) : option.label }
  })

const emit = defineEmits<{
  'update:value': [group: string, field: string, value: unknown]
  action: [group: string, hint: DeclarativeHint, value: unknown]
}>()
</script>

<template>
  <section class="plugin-form" :aria-label="$t('plugins.settingsForm')">
    <section v-for="group in groups" :key="group.name" class="plugin-form-group">
      <div class="section-header">
        <h3>
          {{ te(`${namespace}.${group}.label`) ? t(`${namespace}.${group}.label`) : group.name }}
        </h3>
      </div>
      <div class="form-grid-24">
        <PluginDeclarativeField
          v-for="hint in group.hints"
          :key="`${group.name}.${hint.field}`"
          :group="group.name"
          :namespace="namespace"
          :disabled="disabled"
          :hint="hint"
          :value="values[group.name]?.[hint.field || '']"
          :options="options(group.name, hint)"
          :loading="runningKey === `${group.name}.${hint.field}`"
          @update:value="emit('update:value', group.name, hint.field || '', $event)"
          @action="emit('action', group.name, hint, $event)"
        />
        <ApiRetryAlert
          v-for="hint in group.hints.filter(item => item.endpoint)"
          :key="`error-${hint.field}`"
          :error="stateFor(group.name, hint)?.error.value"
          :loading="stateFor(group.name, hint)?.loading.value"
          @retry="stateFor(group.name, hint)?.execute()"
        />
      </div>
    </section>
  </section>
</template>

<style scoped>
.plugin-form-group + .plugin-form-group {
  margin-top: 24px;
}
.plugin-form :deep(.ant-divider) {
  margin: 8px 0 16px;
}
</style>
