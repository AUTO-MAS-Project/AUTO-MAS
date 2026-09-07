<template>
  <div class="form-section">
    <a-row :gutter="24" align="middle">
      <a-col :span="6">
        <a-form-item name="IfSeizeDeliveryJobs">
          <template #label>
            <span class="form-label">
              {{ t('edit.maaEndSeizeDeliveryJobs') }}
              <a-tooltip :title="t('edit.maaEndSeizeDeliveryJobsHint')">
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

      <template v-if="formData.Task.IfSeizeDeliveryJobs">
        <a-col :span="8">
          <a-form-item name="SeizeDeliveryJobsReward">
            <template #label>
              <span class="form-label">
                {{ t('edit.maaEndSeizeDeliveryJobsReward') }}
                <a-tooltip :title="t('edit.maaEndSeizeDeliveryJobsRewardHint')">
                  <QuestionCircleOutlined class="help-icon" />
                </a-tooltip>
              </span>
            </template>
            <a-input-number
              v-model:value="formData.Task.SeizeDeliveryJobsReward"
              :min="0"
              :step="0.1"
              :disabled="loading"
              size="large"
              style="width: 100%"
              @change="handleRewardChange"
              @blur="handleRewardBlur"
            />
          </a-form-item>
        </a-col>

        <a-col :span="8">
          <a-form-item
            name="SeizeDeliveryJobsCommissionSource"
            :label="t('edit.maaEndDeliveryCommissionSource')"
          >
            <a-select
              v-model:value="formData.Task.SeizeDeliveryJobsCommissionSource"
              :options="MAAEND_DELIVERY_COMMISSION_SOURCE_OPTIONS"
              :disabled="loading"
              size="large"
              @change="handleCommissionSourceChange"
            />
          </a-form-item>
        </a-col>
      </template>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import {
  MAAEND_DELIVERY_COMMISSION_SOURCE_OPTIONS,
  type MaaEndDeliveryCommissionSource,
} from '@/utils/maaEndProtocolSpace'

const { t } = useI18n()

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
