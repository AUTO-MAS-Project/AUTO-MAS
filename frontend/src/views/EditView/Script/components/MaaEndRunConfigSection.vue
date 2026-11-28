<template>
  <SectionCard variant="card" :title="t('core.edit.runConfiguration')" :icon="ThunderboltOutlined">
    <a-row :gutter="24">
      <a-col :xs="24" :md="12">
        <ScriptHardTimeoutField
          v-model:value="run.HardTimeLimit"
          full-width
          @save="emit('save', 'HardTimeLimit', run.HardTimeLimit)"
        />
      </a-col>
      <a-col v-for="field in timeoutFields" :key="field.key" :xs="24" :md="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint :text="t(field.label)" :hint="t(field.hint)" variant="form" />
          </template>
          <a-input-number
            v-model:value="run[field.key]"
            :min="1"
            :max="9999"
            style="width: 100%"
            @blur="emit('save', field.key, run[field.key])"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12">
        <a-form-item :help="t('core.edit.accountSwitch16x9Only')">
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.accountSwitchingMethod')"
              :hint="t('core.edit.chooseWhetherMasSwitches')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="run.AccountSwitchMethod"
            :options="accountSwitchOptions"
            @change="emit('accountSwitch', $event)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.taskTransitionMethod')"
              :hint="t('core.edit.taskTransitionHint')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="run.TaskTransitionMethod"
            :options="transitionOptions"
            @change="emit('save', 'TaskTransitionMethod', $event)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.runsPerDay')"
              :hint="t('core.edit.skipRunOnceThis')"
              variant="form"
            />
          </template>
          <a-input-number
            v-model:value="run.ProxyTimesLimit"
            :min="0"
            :max="9999"
            style="width: 100%"
            @blur="emit('save', 'ProxyTimesLimit', run.ProxyTimesLimit)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <MaaEndErrorLogBundleField v-model:run="run" @save="(key, value) => emit('save', key, value)" />
  </SectionCard>
</template>

<script setup lang="ts">
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { ThunderboltOutlined } from '@ant-design/icons-vue'
import { SectionCard } from '@/components/ui'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MaaEndScriptConfig } from '@/types/script'
import ScriptHardTimeoutField from './ScriptHardTimeoutField.vue'
import MaaEndErrorLogBundleField from './MaaEndErrorLogBundleField.vue'

type RunConfig = MaaEndScriptConfig['Run']
const run = defineModel<RunConfig>('run', { required: true })
const emit = defineEmits<{
  save: [key: keyof RunConfig, value: RunConfig[keyof RunConfig]]
  accountSwitch: [value: RunConfig['AccountSwitchMethod']]
}>()
const { t } = useI18n()
const timeoutFields = [
  { key: 'RunTimeLimit', label: 'core.edit.runTimeoutMinutes', hint: 'core.edit.treatRunAsTimed' },
  { key: 'RunTimesLimit', label: 'core.edit.retryLimit2', hint: 'core.edit.ifRunStillUnfinished' },
] as const
const accountSwitchOptions = computed(() => [
  { label: t('core.edit.accountSwitchMethodMas'), value: 'MAS' },
  { label: t('core.edit.accountSwitchMethodMaaend'), value: 'MAAEND' },
])
const transitionOptions = computed(() => [
  { label: t('core.edit.restartMaaendOnly'), value: 'NoAction' },
  { label: t('core.edit.restartEndfield'), value: 'ExitGame' },
])
</script>
