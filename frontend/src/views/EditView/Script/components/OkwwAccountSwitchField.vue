<template>
  <a-form-item>
    <template #label>
      <FieldLabelWithHint
        :text="t('core.edit.okwwAccountSwitchMethod')"
        :hint="t('core.edit.okwwAccountSwitchHint')"
        variant="form"
      />
    </template>
    <a-select
      v-model:value="method"
      size="large"
      class="modern-input"
      option-label-prop="label"
      @change="emit('save', $event)"
    >
      <a-select-option
        v-for="option in options"
        :key="option.value"
        :value="option.value"
        :label="t(option.label)"
        title=""
      >
        <a-tooltip :title="t(option.hint)" placement="left" :mouse-enter-delay="0.3">
          <span class="switch-option">{{ t(option.label) }}</span>
        </a-tooltip>
      </a-select-option>
    </a-select>
    <span v-if="method === 'MAS'" class="control-hint">
      {{ t('core.edit.accountSwitch16x9ArgHint', { p0: '-Res=1920x1080' }) }}
    </span>
  </a-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { OkwwConfig_Game } from '@/api'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

type SwitchMethod = NonNullable<OkwwConfig_Game['AccountSwitchMethod']>
const method = defineModel<SwitchMethod>({ required: true })
const emit = defineEmits<{ save: [value: SwitchMethod] }>()
const { t } = useI18n()

const options = [
  { value: 'NONE', label: 'core.edit.okwwSwitchOff', hint: 'core.edit.okwwSwitchOffHint' },
  { value: 'MAS', label: 'core.edit.okwwMasRecommended', hint: 'core.edit.okwwMasSwitchHint' },
  {
    value: 'OKWW_SINGLE',
    label: 'core.edit.okwwSingleSwitch',
    hint: 'core.edit.okwwSingleSwitchHint',
  },
  { value: 'OKWW', label: 'core.edit.okwwNativeSwitch', hint: 'core.edit.okwwBatchSwitchHint' },
] satisfies { value: SwitchMethod; label: string; hint: string }[]
</script>

<style scoped>
.switch-option {
  display: block;
}
</style>
