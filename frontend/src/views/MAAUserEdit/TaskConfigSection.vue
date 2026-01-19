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
  </div>
</template>

<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

defineProps<{
  formData: any
  loading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
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
</style>
