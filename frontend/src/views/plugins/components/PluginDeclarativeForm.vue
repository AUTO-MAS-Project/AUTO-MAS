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
const target = computed(
  () => /* 组合当前表单值、配置标识与控件提示，为动态选项查询提供完整依赖上下文。 */ ({
    ...props.values,
    uid: props.uid,
    ui: {
      hints: Object.fromEntries(
        props.groups.map(group => /* 将表单分组转换为分组名到控件提示列表的映射。 */ [
          group.name,
          group.hints,
        ])
      ),
    },
  })
)
const { optionsFor, stateFor } = useDeclarativeOptions(target)
const options = (group: string, hint: DeclarativeHint) =>
  /* 取得字段静态或动态选项，并应用插件命名空间中的选项翻译。 */ optionsFor(group, hint).map(
    option => {
      // 为单个选项选择翻译标签，未提供词条时保留后端声明名称。
      const key = `${props.namespace}.${group}.${hint.field}.options.${option.value}`
      return { ...option, label: te(key) ? t(key) : option.label }
    }
  )

const emit = defineEmits<{
  'update:value': [group: string, field: string, value: unknown]
  action: [group: string, hint: DeclarativeHint, value: unknown]
}>()
</script>

<template>
  <section class="plugin-form" :aria-label="$t('core.plugins.settingsForm')">
    <section v-for="group in groups" :key="group.name" class="plugin-form-group">
      <div class="section-header">
        <h3>
          {{
            te(`${namespace}.${group.name}.label`)
              ? t(`${namespace}.${group.name}.label`)
              : group.name
          }}
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
.form-grid-24 {
  display: grid;
  grid-template-columns: repeat(24, minmax(0, 1fr));
  gap: 16px;
}
.form-grid-24 :deep(.form-grid-24__item) {
  grid-column: span var(--field-span, 12);
}
@media (max-width: 768px) {
  .form-grid-24 :deep(.form-grid-24__item) {
    grid-column: span 24;
  }
}
.plugin-form :deep(.ant-divider) {
  margin: 8px 0 16px;
}
</style>
