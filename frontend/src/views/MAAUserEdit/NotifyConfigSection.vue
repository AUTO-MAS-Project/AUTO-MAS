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
        <a-switch v-model:checked="formData.Notify.Enabled" :disabled="loading" />
        <span class="switch-description">启用后将发送此用户的任务通知到选中的渠道</span>
      </a-col>
    </a-row>
    <!-- 发送统计/六星等可选通知 -->
    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="6">
        <span style="font-weight: 500">通知内容</span>
      </a-col>
      <a-col :span="18" style="display: flex; gap: 32px">
        <a-checkbox
          v-model:checked="formData.Notify.IfSendStatistic"
          :disabled="loading || !formData.Notify.Enabled"
          >统计信息
        </a-checkbox>
        <a-checkbox
          v-model:checked="formData.Notify.IfSendSixStar"
          :disabled="loading || !formData.Notify.Enabled"
          >公开招募高资喜报
        </a-checkbox>
      </a-col>
    </a-row>

    <!-- 邮件通知 -->
    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="6">
        <a-checkbox
          v-model:checked="formData.Notify.IfSendMail"
          :disabled="loading || !formData.Notify.Enabled"
          >邮件通知
        </a-checkbox>
      </a-col>
      <a-col :span="18">
        <a-input
          v-model:value="formData.Notify.ToAddress"
          placeholder="请输入收件人邮箱地址"
          :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfSendMail"
          size="large"
          style="width: 100%"
        />
      </a-col>
    </a-row>

    <!-- Server酱通知 -->
    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="6">
        <a-checkbox
          v-model:checked="formData.Notify.IfServerChan"
          :disabled="loading || !formData.Notify.Enabled"
          >Server酱
        </a-checkbox>
      </a-col>
      <a-col :span="18" style="display: flex; gap: 8px">
        <a-input
          v-model:value="formData.Notify.ServerChanKey"
          placeholder="请输入SENDKEY"
          :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfServerChan"
          size="large"
          style="flex: 2"
        />
      </a-col>
    </a-row>

    <!-- 自定义 Webhook 通知 -->
    <div style="margin-top: 16px">
      <WebhookManager
        v-model:webhooks="formData.Notify.CustomWebhooks"
        @change="handleWebhookChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import WebhookManager from '@/components/WebhookManager.vue'

defineProps<{
  formData: any
  loading: boolean
}>()

// 处理 Webhook 变化
const handleWebhookChange = () => {
  // 这里可以添加额外的处理逻辑，比如验证或保存
  console.log('User webhooks changed:', formData.Notify.CustomWebhooks)
  // 注意：实际保存会在用户点击保存按钮时进行，这里只是更新本地数据
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
