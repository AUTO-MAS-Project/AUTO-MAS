<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section form-section-alt">
    <div class="section-header">
      <h3>运行配置</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip
              title="external 启动项目自己的界面让它自运行；embedded 由 AUTO-MAS 直接驱动项目的 MaaFramework，启动更快、日志统一，但尚未经过真机验证"
            >
              <span class="form-label">
                运行引擎
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="maafwConfig.Run.Engine ?? 'external'"
            size="large"
            :options="engineOptions"
            style="width: 100%"
            @change="(value: unknown) => emit('change', 'Run', 'Engine', value)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-alert
      v-if="(maafwConfig.Run.Engine ?? 'external') === 'embedded'"
      class="engine-experimental-alert"
      type="warning"
      show-icon
      message="内置运行为实验性功能 · 未经真机验证"
      description="AUTO-MAS 会在自己的进程内加载该项目的 MaaFramework 直接运行，不启动项目界面。该路径尚未经过真机验证，遇到问题请切回「外部运行」。"
    />

    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item label="用户单日代理次数上限">
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
        <a-form-item label="代理重试次数限制">
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
        <a-form-item label="单次运行时间限制（分钟）">
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
            <a-tooltip title="任务在今日正常完成一次后，今日后续运行会自动跳过">
              <span class="form-label">
                每日完成后跳过
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
            placeholder="先读取 interface 后选择任务"
            @change="(value: string[]) => emit('period-task-change', 'DailyOnceTasks', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip title="任务在本周正常完成一次后，本周后续运行会自动跳过">
              <span class="form-label">
                每周完成后跳过
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
            placeholder="先读取 interface 后选择任务"
            @change="(value: string[]) => emit('period-task-change', 'WeeklyOnceTasks', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip title="任务在本月正常完成一次后，本月后续运行会自动跳过">
              <span class="form-label">
                每月完成后跳过
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
            placeholder="先读取 interface 后选择任务"
            @change="(value: string[]) => emit('period-task-change', 'MonthlyOnceTasks', value)"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaFWScriptConfig } from '@/types/script'

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

const engineOptions = [
  { label: '外部运行（推荐）', value: 'external' },
  { label: '内置运行（实验性 · 未经真机验证）', value: 'embedded' },
]
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

.engine-experimental-alert {
  margin-bottom: 24px;
}
</style>
