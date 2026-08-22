<template>
  <div class="form-section">
    <div class="section-header">
      <h3>任务配置</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="6">
        <a-form-item name="IfStartUp" label="开始唤醒">
          <a-switch v-model:checked="formData.Task.IfStartUp" :disabled="loading"
            @change="emitSave('Task.IfStartUp', formData.Task.IfStartUp)" />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="IfFight" label="理智作战">
          <a-switch v-model:checked="formData.Task.IfFight" :disabled="loading"
            @change="emitSave('Task.IfFight', formData.Task.IfFight)" />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="IfInfrast" label="基建换班">
          <a-switch v-model:checked="formData.Task.IfInfrast" :disabled="loading"
            @change="emitSave('Task.IfInfrast', formData.Task.IfInfrast)" />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="IfRecruit" label="自动公招">
          <a-switch v-model:checked="formData.Task.IfRecruit" :disabled="loading"
            @change="emitSave('Task.IfRecruit', formData.Task.IfRecruit)" />
        </a-form-item>
      </a-col>
    </a-row>
    <a-row :gutter="24">
      <a-col :span="6">
        <a-form-item name="IfMall" label="信用收支">
          <a-switch v-model:checked="formData.Task.IfMall" :disabled="loading"
            @change="emitSave('Task.IfMall', formData.Task.IfMall)" />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="IfAward" label="领取奖励">
          <a-switch v-model:checked="formData.Task.IfAward" :disabled="loading"
            @change="emitSave('Task.IfAward', formData.Task.IfAward)" />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="IfRoguelike">
          <template #label>
            <a-tooltip title="你也许需要注意：长时间的自动肉鸽可能会导致你自动调度任务被误判超时">
              <span>自动肉鸽 </span>
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </template>
          <a-switch v-model:checked="formData.Task.IfRoguelike" :disabled="loading"
            @change="emitSave('Task.IfRoguelike', formData.Task.IfRoguelike)" />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item name="IfReclamation">
          <template #label>
            <a-tooltip title="暂不支持，等待适配中~">
              <span>生息演算 </span>
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </template>
          <a-switch v-model:checked="formData.Task.IfReclamation" :disabled="true" />
        </a-form-item>
      </a-col>
    </a-row>
    <a-alert
      v-if="activityStageError"
      :message="activityStageError"
      type="warning"
      show-icon
      class="activity-stage-alert"
    />
    <a-row :gutter="24">
      <a-col :span="6">
        <a-form-item label="优先刷取活动关">
          <a-switch
            v-model:checked="activityFirst"
            :disabled="loading"
            @change="emitSave('Task.IfActivityFirst', $event)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip
              title="按列表序号保存；活动更新后自动选择相同序号的新关卡，序号失效时回退到第一项"
            >
              <span>活动关卡 </span>
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </template>
          <a-select
            :value="displayActivityStageIndex"
            :options="activityStageOptions"
            :loading="activityStageLoading"
            :disabled="
              loading || activityStageLoading || !activityFirst || activityStageOptions.length === 0
            "
            :placeholder="activityStageOptions.length ? '请选择活动关卡' : '当前无可刷活动关'"
            show-search
            option-filter-prop="label"
            size="large"
            @change="handleActivityStageChange"
          />
        </a-form-item>
      </a-col>
      <a-col :span="6">
        <a-form-item>
          <template #label>
            <a-tooltip
              title="活动关优先任务使用的理智药数量，不影响普通理智作战"
            >
              <span>活动关理智药 </span>
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </template>
          <a-input-number
            :value="formData.Task.ActivityMedicineNumb"
            :min="0"
            :max="9999"
            :disabled="loading || !activityFirst"
            placeholder="0"
            size="large"
            style="width: 100%"
            @change="handleActivityMedicineChange"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

defineProps<{
  formData: any
  loading: boolean
  activityStageOptions: Array<{ label: string; value: number }>
  activityStageLoading: boolean
  activityStageError: string
  displayActivityStageIndex?: number
}>()

const activityFirst = defineModel<boolean>('activityFirst', { required: true })
const activityStageIndex = defineModel<number>('activityStageIndex', { required: true })

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

const handleActivityStageChange = (value: number) => {
  activityStageIndex.value = value
  emitSave('Task.ActivityStageIndex', value)
}

const handleActivityMedicineChange = (value: number | null) => {
  emitSave('Task.ActivityMedicineNumb', value ?? 0)
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
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.activity-stage-alert {
  margin-bottom: 16px;
}
</style>
