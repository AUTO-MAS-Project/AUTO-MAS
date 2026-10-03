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
      <a-col :span="8">
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
      <a-col :span="16">
        <a-form-item>
          <template #label>
            <span class="form-label">{{ t('edit.taskTimeLimitOverrides') }}</span>
          </template>
          <div class="task-limit-overrides">
            <div
              v-for="(row, index) in taskLimitOverrideRows"
              :key="index"
              class="task-limit-override"
            >
              <a-select
                :value="row.name || undefined"
                size="large"
                :options="overrideTaskOptions(row.name)"
                :disabled="interfaceDependentDisabled"
                option-filter-prop="label"
                show-search
                :placeholder="t('edit.readInterfaceFirstThen')"
                class="task-limit-override-task"
                @change="(value: string) => updateTaskLimitOverrideRow(index, { name: value })"
              />
              <a-input-number
                :value="row.minutes"
                :min="0"
                :max="9999"
                size="large"
                class="modern-number-input task-limit-override-minutes"
                @change="(value: unknown) => setTaskLimitOverrideMinutes(index, value)"
              />
              <a-button
                type="text"
                danger
                :title="t('edit.delete')"
                @click="removeTaskLimitOverrideRow(index)"
              >
                <template #icon><DeleteOutlined /></template>
              </a-button>
            </div>
            <a-button
              type="dashed"
              block
              :disabled="interfaceDependentDisabled || overrideTaskOptions('').length === 0"
              @click="addTaskLimitOverrideRow"
            >
              <template #icon><PlusOutlined /></template>
              {{ t('edit.addTaskTimeLimitOverride') }}
            </a-button>
          </div>
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type {
  MaaFWScriptRunSectionEmits,
  MaaFWScriptRunSectionProps,
} from '../../MaaFWFlavor/sectionContracts'
import type { TaskLimitOverrideRow } from './periodTasks'

const { t } = useI18n()

// props / 事件的契约在 sectionContracts（特调替换这个分节时按同一份契约接收）
const props = defineProps<MaaFWScriptRunSectionProps>()

const emit = defineEmits<MaaFWScriptRunSectionEmits>()

/** 每行可选的任务：排掉已被其它行占用（以及本行当前选中）的任务，一个任务只配一条覆盖 */
const overrideTaskOptions = (name: string) => {
  const used = new Set(
    props.taskLimitOverrideRows.filter(row => row.name !== name).map(row => row.name)
  )
  return props.periodTaskOptions.filter(option => !used.has(option.value))
}

const emitTaskLimitOverrideChange = (rows: TaskLimitOverrideRow[]) => {
  emit('task-limit-override-change', rows)
}

const updateTaskLimitOverrideRow = (index: number, patch: Partial<TaskLimitOverrideRow>) => {
  emitTaskLimitOverrideChange(
    props.taskLimitOverrideRows.map((row, i) => (i === index ? { ...row, ...patch } : row))
  )
}

/** 分钟输入框允许被清空（null）或给出字符串，统一按整数分钟收口 */
const setTaskLimitOverrideMinutes = (index: number, value: unknown) => {
  updateTaskLimitOverrideRow(index, { minutes: Math.trunc(Number(value)) || 0 })
}

const removeTaskLimitOverrideRow = (index: number) => {
  emitTaskLimitOverrideChange(props.taskLimitOverrideRows.filter((_, i) => i !== index))
}

const addTaskLimitOverrideRow = () => {
  const next = overrideTaskOptions('')[0]
  if (!next) return
  emitTaskLimitOverrideChange([
    ...props.taskLimitOverrideRows,
    { name: next.value, minutes: props.maafwConfig.Run.TaskTimeLimit ?? 0 },
  ])
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

.task-limit-overrides {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-limit-override {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-limit-override-task {
  flex: 1;
}

.task-limit-override-minutes {
  width: 120px;
}
</style>
