<template>
  <div class="form-section">
    <div class="section-header">
      <h3>送货配置</h3>
    </div>

    <a-row :gutter="24" align="middle">
      <a-col :span="6">
        <a-form-item name="IfSeizeDeliveryJobs">
          <template #label>
            <span class="form-label">
              抢委托送货
              <a-tooltip title="送货阶段独立运行抢委托送货任务，与日常任务开关分开控制">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-switch
            v-model:checked="formData.Task.IfSeizeDeliveryJobs"
            :disabled="loading"
            @change="handleEnabledChange"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row v-if="formData.Task.IfSeizeDeliveryJobs" :gutter="24">
      <a-col :span="8">
        <a-form-item name="SeizeDeliveryJobsReward">
          <template #label>
            <span class="form-label">
              最低接取价格（万）
              <a-tooltip title="只接取价格不低于该数值的委托">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input-number
            v-model:value="formData.Task.SeizeDeliveryJobsReward"
            :min="0"
            :step="0.1"
            :disabled="loading"
            style="width: 100%"
            @change="handleRewardChange"
            @blur="handleRewardBlur"
          />
        </a-form-item>
      </a-col>

      <a-col :span="8">
        <a-form-item name="SeizeDeliveryJobsCommissionSource" label="委托接收点">
          <a-select
            v-model:value="formData.Task.SeizeDeliveryJobsCommissionSource"
            :options="MAAEND_DELIVERY_COMMISSION_SOURCE_OPTIONS"
            :disabled="loading"
            @change="handleCommissionSourceChange"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import {
  MAAEND_DELIVERY_COMMISSION_SOURCE_OPTIONS,
  type MaaEndDeliveryCommissionSource,
} from '@/utils/maaEndProtocolSpace'

const props = defineProps<{
  formData: any
  loading: boolean
}>()

const formData = props.formData

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

const handleEnabledChange = (value: boolean) => {
  formData.Task.IfSeizeDeliveryJobs = value
  emitSave('Task.IfSeizeDeliveryJobs', value)
}

const handleRewardChange = (value: number | string | null) => {
  const normalizedValue = Number(value)
  formData.Task.SeizeDeliveryJobsReward =
    Number.isFinite(normalizedValue) && normalizedValue >= 0 ? normalizedValue : 15.9
}

const handleRewardBlur = () => {
  emitSave('Task.SeizeDeliveryJobsReward', formData.Task.SeizeDeliveryJobsReward)
}

const handleCommissionSourceChange = (value: MaaEndDeliveryCommissionSource) => {
  formData.Task.SeizeDeliveryJobsCommissionSource = value
  emitSave('Task.SeizeDeliveryJobsCommissionSource', value)
}
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
}
</style>
