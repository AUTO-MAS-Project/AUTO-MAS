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
        <a-switch v-model:checked="formData.Notify.Enabled" :disabled="loading"
          @change="emitSave('Notify.Enabled', formData.Notify.Enabled)" />
        <span class="switch-description">启用后将发送此用户的任务通知到选中的渠道</span>
      </a-col>
    </a-row>
    <!-- 发送统计/六星等可选通知 -->
    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="6">
        <span style="font-weight: 500">通知内容</span>
      </a-col>
      <a-col :span="18" style="display: flex; gap: 32px">
        <a-checkbox v-model:checked="formData.Notify.IfSendStatistic" :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)">统计信息
        </a-checkbox>
        <a-checkbox v-model:checked="formData.Notify.IfSendSixStar" :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfSendSixStar', formData.Notify.IfSendSixStar)">公开招募高资喜报
        </a-checkbox>
      </a-col>
    </a-row>

    <!-- 邮件通知 -->
    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="6">
        <a-checkbox v-model:checked="formData.Notify.IfSendMail" :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfSendMail', formData.Notify.IfSendMail)">邮件通知
        </a-checkbox>
      </a-col>
      <a-col :span="18">
        <a-input v-model:value="formData.Notify.ToAddress" placeholder="请输入收件人邮箱地址"
          :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfSendMail" size="large"
          style="width: 100%" @blur="emitSave('Notify.ToAddress', formData.Notify.ToAddress)" />
      </a-col>
    </a-row>

    <!-- Server酱通知 -->
    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="6">
        <a-checkbox v-model:checked="formData.Notify.IfServerChan" :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfServerChan', formData.Notify.IfServerChan)">Server酱
        </a-checkbox>
      </a-col>
      <a-col :span="18" style="display: flex; gap: 8px">
        <a-input v-model:value="formData.Notify.ServerChanKey" placeholder="请输入SENDKEY"
          :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfServerChan" size="large" style="flex: 2"
          @blur="emitSave('Notify.ServerChanKey', formData.Notify.ServerChanKey)" />
      </a-col>
    </a-row>

    <!-- 自定义 Webhook 通知 -->
    <div style="margin-top: 16px">
      <WebhookManager mode="user" :script-id="props.scriptId" :user-id="props.userId" @change="handleWebhookChange" />
    </div>
  </div>
</template>

<script setup lang="ts">
import WebhookManager from '@/components/WebhookManager.vue'

const logger = window.electronAPI.getLogger('通知配置组件')

const props = defineProps<{
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

// 处理 Webhook 变化
const handleWebhookChange = () => {
  // Webhook 有自己的保存逻辑，这里只记录日志
  logger.info('User webhooks changed for script:', props.scriptId, 'user:', props.userId)
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

.switch-description {
  margin-left: 12px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-input:hover {
  border-color: var(--ant-color-primary-hover);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}
</style>
