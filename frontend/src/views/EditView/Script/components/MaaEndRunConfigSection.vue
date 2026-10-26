<template>
  <section class="form-section run-config-section">
    <div class="section-header">
      <h3>{{ t('edit.runConfiguration') }}</h3>
    </div>
    <div class="run-config-grid">
      <ScriptHardTimeoutField
        v-model:value="run.HardTimeLimit"
        full-width
        @save="emit('save', 'HardTimeLimit', run.HardTimeLimit)"
      />
      <a-form-item v-for="field in timeoutFields" :key="field.key">
        <template #label>
          <FieldLabelWithHint :text="t(field.label)" :hint="t(field.hint)" variant="form" />
        </template>
        <a-input-number
          v-model:value="run[field.key]"
          :min="1"
          :max="9999"
          size="large"
          class="number-input"
          @blur="emit('save', field.key, run[field.key])"
        />
      </a-form-item>
      <a-form-item :help="t('edit.accountSwitch16x9Only')">
        <template #label>
          <FieldLabelWithHint
            :text="t('edit.accountSwitchingMethod')"
            :hint="t('edit.chooseWhetherMasSwitches')"
            variant="form"
          />
        </template>
        <a-select
          v-model:value="run.AccountSwitchMethod"
          :options="accountSwitchOptions"
          size="large"
          @change="emit('accountSwitch', $event)"
        />
      </a-form-item>
      <a-form-item>
        <template #label>
          <FieldLabelWithHint
            :text="t('edit.taskTransitionMethod')"
            :hint="t('edit.taskTransitionHint')"
            variant="form"
          />
        </template>
        <a-select
          v-model:value="run.TaskTransitionMethod"
          :options="transitionOptions"
          size="large"
          @change="emit('save', 'TaskTransitionMethod', $event)"
        />
      </a-form-item>
      <a-form-item>
        <template #label>
          <FieldLabelWithHint
            :text="t('edit.runsPerDay')"
            :hint="t('edit.skipRunOnceThis')"
            variant="form"
          />
        </template>
        <a-input-number
          v-model:value="run.ProxyTimesLimit"
          :min="0"
          :max="9999"
          size="large"
          class="number-input"
          @blur="emit('save', 'ProxyTimesLimit', run.ProxyTimesLimit)"
        />
      </a-form-item>
    </div>
  </section>
</template>

<script setup lang="ts">
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MaaEndScriptConfig } from '@/types/script'
import ScriptHardTimeoutField from './ScriptHardTimeoutField.vue'

type RunConfig = MaaEndScriptConfig['Run']
const run = defineModel<RunConfig>('run', { required: true })
const emit = defineEmits<{
  save: [key: keyof RunConfig, value: RunConfig[keyof RunConfig]]
  accountSwitch: [value: RunConfig['AccountSwitchMethod']]
}>()
const { t } = useI18n()
const timeoutFields = [
  { key: 'RunTimeLimit', label: 'edit.runTimeoutMinutes', hint: 'edit.treatRunAsTimed' },
  { key: 'RunTimesLimit', label: 'edit.retryLimit2', hint: 'edit.ifRunStillUnfinished' },
] as const
const accountSwitchOptions = computed(() => [
  { label: t('edit.accountSwitchMethodMas'), value: 'MAS' },
  { label: t('edit.accountSwitchMethodMaaend'), value: 'MAAEND' },
])
const transitionOptions = computed(() => [
  { label: t('edit.restartMaaendOnly'), value: 'NoAction' },
  { label: t('edit.restartEndfield'), value: 'ExitGame' },
])
</script>

<style scoped>
.run-config-section {
  container-type: inline-size;
}
.section-header {
  margin-bottom: 16px;
}
.run-config-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px 24px;
}
.run-config-grid :deep(.ant-form-item-label) {
  font-weight: 600;
}
.run-config-grid :deep(.anticon-question-circle) {
  color: var(--ant-color-text-tertiary);
}
.run-config-grid > * {
  min-width: 0;
}
.number-input {
  width: 100%;
}
@container (max-width: 900px) {
  .run-config-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container (max-width: 560px) {
  .run-config-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
