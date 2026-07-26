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
          @change="emitSave('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)"
          >统计信息
        </a-checkbox>
        <a-checkbox
          v-model:checked="formData.Notify.IfSendSixStar"
          :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfSendSixStar', formData.Notify.IfSendSixStar)"
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
          @change="emitSave('Notify.IfSendMail', formData.Notify.IfSendMail)"
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
          @blur="emitSave('Notify.ToAddress', formData.Notify.ToAddress)"
        />
      </a-col>
    </a-row>

    <!-- Server酱通知 -->
    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="6">
        <a-checkbox
          v-model:checked="formData.Notify.IfServerChan"
          :disabled="loading || !formData.Notify.Enabled"
          @change="emitSave('Notify.IfServerChan', formData.Notify.IfServerChan)"
          >Server酱
        </a-checkbox>
      </a-col>
      <a-col :span="18">
        <div class="sensitive-field">
          <a-input-password
            :value="serverChanKeyDraft"
            :placeholder="serverChanKeyPlaceholder"
            :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfServerChan"
            size="large"
            autocomplete="new-password"
            @update:value="serverChanKeyDraft = $event"
          />
          <div class="sensitive-actions">
            <span class="sensitive-hint">已保存 SENDKEY 不回显，避免无意覆盖</span>
            <a-space size="small">
              <a-button
                v-if="hasStoredServerChanKey"
                size="small"
                danger
                :disabled="loading || !formData.Notify.IfServerChan"
                @click="clearServerChanKey"
              >
                清空原值
              </a-button>
              <a-button
                type="primary"
                size="small"
                :disabled="
                  loading ||
                  !formData.Notify.Enabled ||
                  !formData.Notify.IfServerChan ||
                  !serverChanKeyDraft
                "
                @click="saveServerChanKey"
              >
                保存新值
              </a-button>
            </a-space>
          </div>
        </div>
      </a-col>
    </a-row>

    <!-- 自定义 Webhook 通知 -->
    <div style="margin-top: 16px">
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
import { computed, ref } from 'vue'
import { Modal } from 'ant-design-vue'
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
  sensitiveSave: [key: 'Notify.ServerChanKey', intent: 'replace' | 'clear', value?: string]
}>()

const serverChanKeyDraft = ref('')
const hasStoredServerChanKey = computed(() => Boolean(props.formData?.Notify?.ServerChanKey))
const serverChanKeyPlaceholder = computed(() =>
  hasStoredServerChanKey.value ? '已保存；输入新值后明确保存' : '请输入 SENDKEY'
)

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

const saveServerChanKey = () => {
  if (!serverChanKeyDraft.value) return
  emit('sensitiveSave', 'Notify.ServerChanKey', 'replace', serverChanKeyDraft.value)
}

const clearServerChanKey = () => {
  Modal.confirm({
    title: '清空 Server 酱 SENDKEY？',
    content: '清空后该通知渠道将无法发送消息，直到重新填写。',
    okText: '清空',
    cancelText: '取消',
    okType: 'danger',
    centered: true,
    onOk: () => emit('sensitiveSave', 'Notify.ServerChanKey', 'clear', ''),
  })
}

defineExpose({
  resetServerChanKeyDraft: () => {
    serverChanKeyDraft.value = ''
  },
})

// 处理 Webhook 变化
const handleWebhookChange = () => {
  // Webhook 有自己的保存逻辑，这里只记录日志
  logger.info(`Webhook changed for script: ${props.scriptId}, user: ${props.userId}`)
}
</script>

<style scoped>
.form-section {
  margin-bottom: var(--v6-space-4);
}

.section-header {
  margin-bottom: var(--v6-space-4);
  padding-bottom: var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.switch-description {
  margin-left: var(--v6-space-3);
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text-secondary);
}

.modern-input {
  border-radius: var(--v6-radius-md);
  border: 1px solid var(--v6-color-border);
  background: var(--v6-color-surface);
  transition: all var(--v6-motion-fast) var(--v6-ease-out);
}

.modern-input:hover {
  border-color: var(--v6-color-info);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--v6-color-info);
  box-shadow: var(--v6-shadow-focus-ring);
}

.sensitive-field {
  display: grid;
  gap: var(--v6-space-2);
}

.sensitive-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-3);
}

.sensitive-hint {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-sm);
}

@media (max-width: 768px) {
  .sensitive-actions {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
