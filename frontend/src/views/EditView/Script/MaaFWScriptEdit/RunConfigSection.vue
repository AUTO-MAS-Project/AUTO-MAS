<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section">
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
            <span class="form-label">{{ t('edit.skipOnceDoneToday') }}</span>
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
            <span class="form-label">{{ t('edit.skipOnceDoneThis') }}</span>
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
            <span class="form-label">{{ t('edit.skipOnceDoneThis2') }}</span>
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

    <a-row :gutter="24" class="task-time-limit-row">
      <a-col :span="12">
        <a-form-item :label="t('edit.singleTaskTimeLimit')">
          <a-input-number
            v-model:value="maafwConfig.Run.TaskTimeLimit"
            :min="0"
            :max="9999"
            size="large"
            class="modern-number-input"
            style="width: 100%"
            @blur="emit('change', 'Run', 'TaskTimeLimit', maafwConfig.Run.TaskTimeLimit)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <!-- 按任务单独设置：摘要 + 弹窗，存的仍是 Run.TaskTimeLimitOverrides 的 JSON 字符串；
             原地打转检测（Run.LoopGuard）的开关也在这个弹窗里 -->
        <MaaFWTaskTimeLimitField
          :value="maafwConfig.Run.TaskTimeLimitOverrides"
          :loop-guard="Boolean(maafwConfig.Run.LoopGuard)"
          :tasks="periodTaskOptions"
          :default-minutes="maafwConfig.Run.TaskTimeLimit ?? 0"
          :disabled="interfaceDependentDisabled || periodTaskOptions.length === 0"
          @save="handleTaskTimeLimitOverridesSave"
        />
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type {
  MaaFWScriptRunSectionEmits,
  MaaFWScriptRunSectionProps,
} from '../../MaaFWFlavor/sectionContracts'
import MaaFWTaskTimeLimitField from './MaaFWTaskTimeLimitField.vue'

const { t } = useI18n()

// props / 事件的契约在 sectionContracts（特调替换这个分节时按同一份契约接收）
const props = defineProps<MaaFWScriptRunSectionProps>()

const emit = defineEmits<MaaFWScriptRunSectionEmits>()

const handleTaskTimeLimitOverridesSave = (value: string, loopGuard: boolean) => {
  props.maafwConfig.Run.TaskTimeLimitOverrides = value
  emit('change', 'Run', 'TaskTimeLimitOverrides', value)
  if (loopGuard !== Boolean(props.maafwConfig.Run.LoopGuard)) {
    props.maafwConfig.Run.LoopGuard = loopGuard
    emit('change', 'Run', 'LoopGuard', loopGuard)
  }
}
</script>

<style scoped>
.form-section {
  margin-bottom: 40px;
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

.task-time-limit-row {
  margin-top: 8px;
}
</style>
