<template>
  <a-form-item :label="t('core.edit.okwwEchoOverride')">
    <a-switch :checked="enabled" :disabled="disabled" @change="toggle" />
  </a-form-item>
  <a-typography-paragraph v-if="!enabled" type="secondary">
    {{ t('core.edit.okwwEchoInherit') }}
  </a-typography-paragraph>
  <template v-else>
    <a-typography-paragraph v-if="!overlayEnabled" type="secondary">
      {{ t('core.edit.okwwEchoOverlayOff') }}
    </a-typography-paragraph>
    <a-row :gutter="24">
      <a-col v-for="field in visibleFields" :key="field.key" :xs="24" :md="12">
        <a-form-item :label="t(`core.edit.okwwEcho.${field.key}`)">
          <a-select
            v-if="field.options"
            :value="String(config[field.key] ?? defaults[field.key])"
            :options="
              field.options.map(value => ({
                value,
                label: t(`core.edit.okwwEchoOption.${value}`, value),
              }))
            "
            :disabled="disabled"
            @change="(value: unknown) => setField(field.key, String(value))"
          />
          <a-switch
            v-else-if="typeof defaults[field.key] === 'boolean'"
            :checked="Boolean(config[field.key] ?? defaults[field.key])"
            :disabled="disabled"
            @change="(value: boolean | string | number) => setField(field.key, Boolean(value))"
          />
          <a-input-number
            v-else
            :value="Number(config[field.key] ?? defaults[field.key])"
            :min="field.min ?? 1"
            :precision="0"
            :disabled="disabled"
            style="width: 100%"
            @change="
              (value: number | string | null) => {
                if (value !== null) setField(field.key, Number(value))
              }
            "
          />
        </a-form-item>
      </a-col>
    </a-row>
  </template>
  <a-button :disabled="disabled" @click="emit('configure')">
    {{ t('core.edit.okwwEchoConfigure') }}
  </a-button>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

type Values = Record<string, string | number | boolean>
type Field = { key: string; options?: string[]; min?: number; when?: string }
const config = defineModel<Values>({ required: true })
defineProps<{ disabled: boolean; overlayEnabled: boolean }>()
const emit = defineEmits<{ save: []; configure: [] }>()
const { t } = useI18n()
// 原生字段原样透传；上游新增任务字段时保留未识别的值。
const defaults: Values = {
  'Teleport to Boss': 'No',
  'Boss Level': '80',
  Boss: 'Other',
  'Repeat Farm Count': 10000,
  'Combat Wait Time': 0,
  'Echo Pickup Method': 'Walk',
  'Use Liberation': true,
  'Switch to Healer before and after Combat': true,
  'Which Weekly Boss to Teleport': 1,
  'Which Boss Challenge to Teleport': 1,
  'Which Special Nightmare to Teleport': 1,
}
const fields: Field[] = [
  {
    key: 'Teleport to Boss',
    options: ['No', 'Weekly Challenge', 'Boss Challenge', 'Special Nightmare'],
  },
  { key: 'Which Weekly Boss to Teleport', when: 'Weekly Challenge' },
  { key: 'Which Boss Challenge to Teleport', when: 'Boss Challenge' },
  { key: 'Which Special Nightmare to Teleport', when: 'Special Nightmare' },
  { key: 'Boss Level', options: ['50', '60', '70', '80', '90'] },
  {
    key: 'Boss',
    options: [
      'Other',
      'Hyvatia',
      'Fallacy of No Return',
      'Sentry Construct',
      'Lorelei',
      'Lioness of Glory',
      'Nightmare: Hecate',
      'Fenrico',
      'Nameless Explorer',
    ],
  },
  { key: 'Repeat Farm Count' },
  { key: 'Combat Wait Time', min: 0 },
  { key: 'Echo Pickup Method', options: ['Yolo', 'Run in Circle', 'Walk'] },
  { key: 'Use Liberation' },
  { key: 'Switch to Healer before and after Combat' },
]
const enabled = computed(() => Object.keys(config.value).length > 0)
const visibleFields = computed(() =>
  fields.filter(field => !field.when || field.when === config.value['Teleport to Boss'])
)
function toggle(value: boolean | string | number) {
  config.value = value ? { ...defaults } : {}
  emit('save')
}
function setField(key: string, value: string | number | boolean) {
  config.value = { ...defaults, ...config.value, [key]: value }
  emit('save')
}
</script>
