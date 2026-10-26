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
          <span class="form-label">
            {{ t(field.label) }}
            <a-tooltip :title="t(field.hint)">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
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
          <span class="form-label">
            {{ t('edit.accountSwitchingMethod') }}
            <a-tooltip :title="t('edit.chooseWhetherMasSwitches')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
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
          <span class="form-label">
            {{ t('edit.taskTransitionMethod') }}
            <a-tooltip :title="t('edit.taskTransitionHint')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
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
          <span class="form-label">
            {{ t('edit.runsPerDay') }}
            <a-tooltip :title="t('edit.skipRunOnceThis')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
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
      <MaaEndErrorLogBundleField
        v-model:run="run"
        @save="(key, value) => emit('save', key, value)"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
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
.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}
.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
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
