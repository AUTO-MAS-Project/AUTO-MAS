<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section form-section-alt">
    <div class="section-header">
      <h3>{{ t('edit.runConfiguration') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item :label="t('edit.runsPerDayThis')">
          <a-input-number
            v-model:value="maafwConfig.Run.ProxyTimesLimit"
            :min="0"
            :max="9999"
            size="large"
            class="modern-number-input"
            style="width: 100%"
            @blur="emit('change', 'Run', 'ProxyTimesLimit', maafwConfig.Run.ProxyTimesLimit)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item :label="t('edit.retryLimit')">
          <a-input-number
            v-model:value="maafwConfig.Run.RunTimesLimit"
            :min="1"
            :max="9999"
            size="large"
            class="modern-number-input"
            style="width: 100%"
            @blur="emit('change', 'Run', 'RunTimesLimit', maafwConfig.Run.RunTimesLimit)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item :label="t('edit.singleRunTimeLimit')">
          <a-input-number
            v-model:value="maafwConfig.Run.RunTimeLimit"
            :min="1"
            :max="9999"
            size="large"
            class="modern-number-input"
            style="width: 100%"
            @blur="emit('change', 'Run', 'RunTimeLimit', maafwConfig.Run.RunTimeLimit)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24" class="period-task-row">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.onceTaskCompletesNormally')">
              <span class="form-label">
                {{ t('edit.skipOnceDoneToday') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="dailyOnceTasks"
            mode="multiple"
            size="large"
            :options="periodTaskOptions"
            :disabled="interfaceDependentDisabled"
            option-filter-prop="label"
            show-search
            :max-tag-count="'responsive'"
            :placeholder="t('edit.readInterfaceFirstThen')"
            @change="(value: string[]) => emit('period-task-change', 'DailyOnceTasks', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.onceTaskCompletesNormally2')">
              <span class="form-label">
                {{ t('edit.skipOnceDoneThis') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="weeklyOnceTasks"
            mode="multiple"
            size="large"
            :options="periodTaskOptions"
            :disabled="interfaceDependentDisabled"
            option-filter-prop="label"
            show-search
            :max-tag-count="'responsive'"
            :placeholder="t('edit.readInterfaceFirstThen')"
            @change="(value: string[]) => emit('period-task-change', 'WeeklyOnceTasks', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.onceTaskCompletesNormally3')">
              <span class="form-label">
                {{ t('edit.skipOnceDoneThis2') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="monthlyOnceTasks"
            mode="multiple"
            size="large"
            :options="periodTaskOptions"
            :disabled="interfaceDependentDisabled"
            option-filter-prop="label"
            show-search
            :max-tag-count="'responsive'"
            :placeholder="t('edit.readInterfaceFirstThen')"
            @change="(value: string[]) => emit('period-task-change', 'MonthlyOnceTasks', value)"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaFWScriptConfig } from '@/types/script'

const { t } = useI18n()

defineProps<{
  maafwConfig: MaaFWScriptConfig
  dailyOnceTasks: string[]
  weeklyOnceTasks: string[]
  monthlyOnceTasks: string[]
  periodTaskOptions: Array<{ label: string; value: string }>
  interfaceDependentDisabled: boolean
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
  'period-task-change': [
    key: 'DailyOnceTasks' | 'WeeklyOnceTasks' | 'MonthlyOnceTasks',
    values: string[],
  ]
}>()
</script>

<style scoped>
.form-section {
  margin-bottom: 40px;
}

.form-section-alt {
  margin: 0 -24px;
  padding: 24px 24px 32px;
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.section-header {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 20px;
  background: var(--ant-color-text-quaternary);
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.modern-number-input {
  border-radius: 8px;
}

.period-task-row {
  margin-top: 8px;
}
</style>
