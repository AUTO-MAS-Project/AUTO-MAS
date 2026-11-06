<template>
  <a-row :gutter="24">
    <a-col :span="24">
      <a-form-item :label="label" :help="help">
        <a-select
          :value="value"
          :options="options"
          :disabled="disabled"
          size="large"
          @change="emit('change', $event)"
        />
      </a-form-item>
    </a-col>
  </a-row>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MaaEndScriptConfig } from '@/types/script'

const props = defineProps<{
  value: MaaEndScriptConfig['Game']['AutoHDR']
  restore?: boolean
  disabled: boolean
}>()
const emit = defineEmits<{ change: [value: MaaEndScriptConfig['Game']['AutoHDR']] }>()
const { t } = useI18n()
const label = computed(() =>
  props.restore ? t('core.edit.maaEndRestoreAutoHDR') : t('core.edit.maaEndAutoHDR')
)
const help = computed(() =>
  props.restore ? t('core.edit.maaEndRestoreAutoHDRHelp') : t('core.edit.maaEndAutoHDRHelp')
)
const options = computed(() => [
  { value: 'Unchanged', label: t('core.edit.maaEndAutoHDRUnchanged') },
  { value: 'Disable', label: t('core.edit.maaEndAutoHDRDisable') },
  { value: 'Enable', label: t('core.edit.maaEndAutoHDREnable') },
])
</script>
