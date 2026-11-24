<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { HSRConfig_Run } from '@/api'
import ScriptExecutionSessionField from './ScriptExecutionSessionField.vue'
import ScriptRunLimitField from './ScriptRunLimitField.vue'

defineProps<{ showLowPerformance: boolean }>()
const run = defineModel<HSRConfig_Run>('run', { required: true })
const emit = defineEmits<{
  save: [key: keyof HSRConfig_Run, value: number | string | boolean | null]
}>()
const { t } = useI18n()
</script>

<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('core.edit.runLimits') }}</h3>
    </div>
    <ScriptExecutionSessionField />
    <a-row :gutter="16">
      <a-col :span="12">
        <ScriptRunLimitField
          v-model="run.ProxyTimesLimit"
          kind="daily"
          :label="t('core.edit.runsPerDayThis')"
          :hint="t('core.edit.k0MeansNoLimit')"
          @change="emit('save', 'ProxyTimesLimit', $event)"
        />
      </a-col>
      <a-col :span="12">
        <a-form-item :label="t('core.edit.maximumAttemptsFailedTask')">
          <a-input-number
            v-model:value="run.RunTimesLimit"
            :min="1"
            :max="9999"
            size="large"
            style="width: 100%"
            @change="emit('save', 'RunTimesLimit', $event)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item :label="t('core.edit.dailyTaskTimeoutMinutes')">
          <a-input-number
            v-model:value="run.DailyTimeLimit"
            :min="1"
            :max="9999"
            size="large"
            style="width: 100%"
            @change="emit('save', 'DailyTimeLimit', $event)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-row :gutter="16">
      <a-col :span="12">
        <a-form-item :label="t('core.edit.weeklyTaskTimeoutMinutes')">
          <a-input-number
            v-model:value="run.WeeklyTimeLimit"
            :min="1"
            :max="9999"
            size="large"
            style="width: 100%"
            @change="emit('save', 'WeeklyTimeLimit', $event)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <!-- 低性能兼容只作用于三月七，没填三月七路径时不渲染 -->
    <a-row v-if="showLowPerformance" :gutter="16">
      <a-col :span="12">
        <a-form-item :label="t('core.edit.enableLowPerformanceCompatibility')">
          <a-switch
            v-model:checked="run.LowPerformanceMode"
            @change="emit('save', 'LowPerformanceMode', $event)"
          />
          <div class="form-item-hint">
            {{ t('core.edit.appliesMarch7thDivergentUniverse') }}
          </div>
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.form-section {
  margin-bottom: 12px;
}

.section-header {
  margin-bottom: 6px;
}

.section-header h3::before {
  background: var(--ant-color-primary);
}
</style>
