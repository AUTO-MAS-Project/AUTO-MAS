<template>
  <div class="form-section">
    <div class="section-header">
      <h3>通知配置</h3>
    </div>

    <div class="notify-channel-list">
      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">启用通知</span>
          <a-switch
            v-model:checked="notify.Enabled"
            :disabled="loading"
            @change="emitSave('Notify.Enabled', notify.Enabled)"
          />
        </div>
      </div>

      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">统计信息</span>
          <a-switch
            v-model:checked="notify.IfSendStatistic"
            :disabled="loading || !notify.Enabled"
            @change="emitSave('Notify.IfSendStatistic', notify.IfSendStatistic)"
          />
        </div>
      </div>

      <div v-if="showSixStar" class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">公开招募高资喜报</span>
          <a-switch
            v-model:checked="notify.IfSendSixStar"
            :disabled="loading || !notify.Enabled"
            @change="emitSave('Notify.IfSendSixStar', notify.IfSendSixStar)"
          />
        </div>
      </div>

      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">邮件通知</span>
          <a-switch
            v-model:checked="notify.IfSendMail"
            :disabled="loading || !notify.Enabled"
            @change="emitSave('Notify.IfSendMail', notify.IfSendMail)"
          />
        </div>
        <div v-if="notify.IfSendMail" class="notify-channel-config">
          <a-form-item label="收件地址">
            <a-input
              v-model:value="notify.ToAddress"
              type="email"
              inputmode="email"
              autocomplete="email"
              placeholder="请输入收件邮箱"
              size="large"
              :disabled="loading || !notify.Enabled"
              @blur="emitSave('Notify.ToAddress', notify.ToAddress)"
            />
          </a-form-item>
        </div>
      </div>

      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">Server 酱</span>
          <a-switch
            v-model:checked="notify.IfServerChan"
            :disabled="loading || !notify.Enabled"
            @change="emitSave('Notify.IfServerChan', notify.IfServerChan)"
          />
        </div>
        <div v-if="notify.IfServerChan" class="notify-channel-config">
          <a-form-item label="SendKey">
            <a-input-password
              v-model:value="notify.ServerChanKey"
              autocomplete="off"
              placeholder="请输入 SENDKEY"
              size="large"
              :disabled="loading || !notify.Enabled"
              @blur="emitSave('Notify.ServerChanKey', notify.ServerChanKey)"
            />
          </a-form-item>
        </div>
      </div>
    </div>

    <WebhookManager
      v-if="scriptId && userId"
      class="webhook-manager"
      mode="user"
      :script-id="scriptId"
      :user-id="userId"
    />
  </div>
</template>

<script setup lang="ts">
import WebhookManager from '@/components/WebhookManager.vue'

type UserNotifyConfigData = {
  Enabled?: boolean | null
  IfSendStatistic?: boolean | null
  IfSendSixStar?: boolean | null
  IfSendMail?: boolean | null
  ToAddress?: string | null
  IfServerChan?: boolean | null
  ServerChanKey?: string | null
}

const notify = defineModel<UserNotifyConfigData>({ required: true })

withDefaults(
  defineProps<{
    loading?: boolean
    scriptId?: string | null
    userId?: string | null
    showSixStar?: boolean
  }>(),
  {
    loading: false,
    scriptId: null,
    userId: null,
    showSixStar: false,
  }
)

const emit = defineEmits<{
  save: [key: string, value: unknown]
}>()

const emitSave = (key: string, value: unknown) => emit('save', key, value)
</script>

<style scoped>
.form-section {
  margin-bottom: 24px;
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
  background: var(--ant-color-primary);
  border-radius: 2px;
}

.notify-channel-list {
  padding: 4px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.notify-channel-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.notify-channel-item:last-child {
  border-bottom: 0;
}

.notify-channel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.notify-channel-name {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.notify-channel-config {
  padding-top: 12px;
}

.notify-channel-config :deep(.ant-form-item) {
  margin-bottom: 0;
}

.webhook-manager {
  margin-top: 16px;
}
</style>
