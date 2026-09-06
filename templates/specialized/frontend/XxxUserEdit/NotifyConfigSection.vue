<template>
  <div class="form-section">
    <div class="section-header">
      <h3>通知配置</h3>
    </div>

    <a-row :gutter="24" align="middle">
      <a-col :span="6"><span class="field-label">启用通知</span></a-col>
      <a-col :span="18">
        <a-switch
          v-model:checked="formData.Notify.Enabled"
          :disabled="loading"
          @change="emitSave('Notify.Enabled', formData.Notify.Enabled)"
        />
        <span class="switch-description">启用后发送该用户的专项任务通知</span>
      </a-col>
    </a-row>

    <a-row :gutter="24" class="notify-row">
      <a-col :span="6"><span class="field-label">通知内容</span></a-col>
      <a-col :span="18">
        <a-checkbox
          v-model:checked="formData.Notify.IfSendStatistic"
          :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)"
          >统计信息</a-checkbox
        >
      </a-col>
    </a-row>

    <a-row :gutter="24" class="notify-row">
      <a-col :span="6">
        <a-checkbox
          v-model:checked="formData.Notify.IfSendMail"
          :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfSendMail', formData.Notify.IfSendMail)"
          >邮件通知</a-checkbox
        >
      </a-col>
      <a-col :span="18">
        <a-input
          v-model:value="formData.Notify.ToAddress"
          placeholder="请输入收件人邮箱地址"
          :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfSendMail"
          size="large"
          @blur="emitSave('Notify.ToAddress', formData.Notify.ToAddress)"
        />
      </a-col>
    </a-row>

    <a-row :gutter="24" class="notify-row">
      <a-col :span="6">
        <a-checkbox
          v-model:checked="formData.Notify.IfServerChan"
          :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfServerChan', formData.Notify.IfServerChan)"
          >Server 酱</a-checkbox
        >
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

    <div class="webhook-wrapper">
      <WebhookManager
        mode="user"
        :script-id="props.scriptId"
        :user-id="props.userId"
        @change="handleWebhookChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import WebhookManager from '@/components/WebhookManager.vue'

interface NotifyFormData {
  Notify: {
    Enabled: boolean
    IfSendStatistic: boolean
    IfSendMail: boolean
    ToAddress: string
    IfServerChan: boolean
    ServerChanKey: string
  }
}

const props = defineProps<{
  formData: NotifyFormData
  loading: boolean
  scriptId?: string
  userId?: string
}>()
const loading = computed(() => props.loading)

const formData = reactive<NotifyFormData>({
  Notify: { ...props.formData.Notify },
})

watch(
  () => props.formData,
  value => {
    Object.assign(formData.Notify, value.Notify)
  },
  { deep: true }
)

const emit = defineEmits<{
  save: [key: string, value: string | boolean]
}>()

const emitSave = (key: string, value: string | boolean) => {
  emit('save', key, value)
}

const handleWebhookChange = () => {
  window.electronAPI
    .getLogger('专项通知配置')
    .info(`Webhook 已更新: script=${props.scriptId ?? '-'}, user=${props.userId ?? '-'}`)
}
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  padding-left: 12px;
  border-left: 4px solid var(--ant-color-primary);
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
}

.field-label {
  color: var(--ant-color-text);
  font-weight: 500;
}

.switch-description {
  margin-left: 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.notify-row {
  margin-top: 16px;
}

.webhook-wrapper {
  margin-top: 16px;
}
</style>
