<template>
  <div class="form-section">
    <div v-if="!hideSectionHeader" class="section-header">
      <h3>{{ t('core.edit.notificationSettings') }}</h3>
    </div>

    <div class="notify-channel-list">
      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">{{ t('core.edit.enableNotifications') }}</span>
          <a-switch
            v-model:checked="notify.Enabled"
            :disabled="loading"
            @change="emitSave('Notify.Enabled', notify.Enabled)"
          />
        </div>
      </div>

      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">{{ t('core.edit.statistics') }}</span>
          <a-switch
            v-model:checked="notify.IfSendStatistic"
            :disabled="loading || !notify.Enabled"
            @change="emitSave('Notify.IfSendStatistic', notify.IfSendStatistic)"
          />
        </div>
      </div>

      <div v-if="showInventory" class="notify-channel-item">
        <div class="notify-channel-header">
          <span>{{ t('core.edit.maaEndImsNotify') }}</span>
          <a-switch
            v-model:checked="notify.IfSendInventory"
            :disabled="loading || !notify.Enabled"
            @change="emitSave('Notify.IfSendInventory', notify.IfSendInventory)"
          />
        </div>
        <div class="notify-channel-config">{{ t('core.edit.maaEndImsNotifyHint') }}</div>
      </div>

      <div v-if="showSixStar" class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">{{ t('core.edit.notifyRecruit') }}</span>
          <a-switch
            v-model:checked="notify.IfSendSixStar"
            :disabled="loading || !notify.Enabled"
            @change="emitSave('Notify.IfSendSixStar', notify.IfSendSixStar)"
          />
        </div>
      </div>

      <div v-if="showDropStatistics" class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">{{ t('core.edit.notifyDropStatistics') }}</span>
          <a-switch
            v-model:checked="notify.IfSendDropStatistics"
            :disabled="loading || !notify.Enabled"
            @change="emitSave('Notify.IfSendDropStatistics', notify.IfSendDropStatistics)"
          />
        </div>
      </div>

      <!-- 节点详情推送模式（任务报告分步节点）：仅 BetterGI 用户编辑页启用 -->
      <div v-if="showPushLogMode" class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">
            {{ t('core.edit.collectNodeDetails') }}
            <a-tooltip mouse-enter-delay="0.5" :title="t('core.edit.collectsKeyMomentsFrom')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
        </div>
        <div class="notify-channel-config">
          <a-select
            v-model:value="notify.PushLogMode"
            :options="pushLogModeOptions"
            size="large"
            @change="emitSave('Notify.PushLogMode', notify.PushLogMode)"
          />
        </div>
      </div>

      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">{{ t('core.edit.emailNotification') }}</span>
          <a-switch
            v-model:checked="notify.IfSendMail"
            :disabled="loading || !notify.Enabled"
            @change="emitSave('Notify.IfSendMail', notify.IfSendMail)"
          />
        </div>
        <div v-if="notify.IfSendMail" class="notify-channel-config">
          <a-form-item :label="t('core.edit.recipient')">
            <a-input
              v-model:value="notify.ToAddress"
              type="email"
              inputmode="email"
              autocomplete="email"
              :placeholder="t('core.edit.enterRecipientAddress')"
              size="large"
              :disabled="loading || !notify.Enabled"
              @blur="emitSave('Notify.ToAddress', notify.ToAddress)"
            />
          </a-form-item>
        </div>
      </div>

      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <span class="notify-channel-name">{{ t('core.edit.serverchan') }}</span>
          <a-switch
            v-model:checked="notify.IfServerChan"
            :disabled="loading || !notify.Enabled"
            @change="emitSave('Notify.IfServerChan', notify.IfServerChan)"
          />
        </div>
        <div v-if="notify.IfServerChan" class="notify-channel-config">
          <a-form-item :label="t('core.edit.serverchan')">
            <a-input-password
              v-model:value="notify.ServerChanKey"
              autocomplete="off"
              :placeholder="t('core.edit.enterSendkey')"
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
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import WebhookManager from '@/components/WebhookManager.vue'

type UserNotifyConfigData = {
  Enabled?: boolean | null
  IfSendStatistic?: boolean | null
  IfSendInventory?: boolean | null
  IfSendSixStar?: boolean | null
  IfSendDropStatistics?: boolean | null
  PushLogMode?: string | null
  IfSendMail?: boolean | null
  ToAddress?: string | null
  IfServerChan?: boolean | null
  ServerChanKey?: string | null
}

const { t } = useI18n()

// 节点详情推送模式（value 为后端 Notify.PushLogMode 取值，驱动逻辑需保持原样；label 走词表）
const pushLogModeOptions = [
  { label: t('core.edit.pushLogModeOff'), value: '关闭' },
  { label: t('core.edit.pushLogModeList'), value: '逐条' },
  { label: t('core.edit.pushLogModeSummary'), value: '汇总' },
]

const notify = defineModel<UserNotifyConfigData>({ required: true })

withDefaults(
  defineProps<{
    loading?: boolean
    scriptId?: string | null
    userId?: string | null
    showSixStar?: boolean
    showInventory?: boolean
    // 掉落统计开关（BGI「奖励识别」汇总）：仅 BetterGI 用户编辑页启用
    showDropStatistics?: boolean
    // 节点详情推送模式（任务报告分步节点）：仅 BetterGI 用户编辑页启用
    showPushLogMode?: boolean
    // 卡片化页面（如 MaaEnd 用户编辑页）由外层卡片提供标题时隐藏内部标题
    hideSectionHeader?: boolean
  }>(),
  {
    loading: false,
    scriptId: null,
    userId: null,
    showSixStar: false,
    showInventory: false,
    showDropStatistics: false,
    showPushLogMode: false,
    hideSectionHeader: false,
  }
)

const emit = defineEmits<{
  save: [key: string, value: unknown]
}>()

const emitSave = (key: string, value: unknown) => emit('save', key, value)
</script>

<style scoped>
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

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.webhook-manager {
  margin-top: 16px;
}
</style>
