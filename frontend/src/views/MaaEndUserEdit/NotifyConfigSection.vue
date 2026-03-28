<!-- eslint-disable vue/no-mutating-props -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>通知配置</h3>
    </div>
    <a-row :gutter="24" align="middle">
      <a-col :span="6">
        <span style="font-weight: 500">启用通知</span>
      </a-col>
      <a-col :span="18">
        <a-switch
          v-model:checked="formData.Notify.Enabled"
          :disabled="loading"
          @change="emitSave('Notify.Enabled', formData.Notify.Enabled)"
        />
      </a-col>
    </a-row>

    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="6">
        <span style="font-weight: 500">通知内容</span>
      </a-col>
      <a-col :span="18">
        <a-checkbox
          v-model:checked="formData.Notify.IfSendStatistic"
          :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)"
        >
          统计信息
        </a-checkbox>
      </a-col>
    </a-row>

    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="6">
        <a-checkbox
          v-model:checked="formData.Notify.IfSendMail"
          :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfSendMail', formData.Notify.IfSendMail)"
        >
          邮件通知
        </a-checkbox>
      </a-col>
      <a-col :span="18">
        <a-input
          v-model:value="formData.Notify.ToAddress"
          placeholder="请输入收件邮箱"
          :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfSendMail"
          size="large"
          @blur="emitSave('Notify.ToAddress', formData.Notify.ToAddress)"
        />
      </a-col>
    </a-row>

    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="6">
        <a-checkbox
          v-model:checked="formData.Notify.IfServerChan"
          :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfServerChan', formData.Notify.IfServerChan)"
        >
          Server酱
        </a-checkbox>
      </a-col>
      <a-col :span="18">
        <a-input
          v-model:value="formData.Notify.ServerChanKey"
          placeholder="请输入 SENDKEY"
          :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfServerChan"
          size="large"
          @blur="emitSave('Notify.ServerChanKey', formData.Notify.ServerChanKey)"
        />
      </a-col>
    </a-row>

    <div style="margin-top: 16px">
      <WebhookManager mode="user" :script-id="scriptId" :user-id="userId" />
    </div>
  </div>
</template>

<script setup lang="ts">
import WebhookManager from '@/components/WebhookManager.vue'

defineProps<{
  formData: any
  loading: boolean
  scriptId?: string
  userId?: string
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
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
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
</style>
