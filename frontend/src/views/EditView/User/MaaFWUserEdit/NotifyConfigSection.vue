<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.notifications') }}</h3>
    </div>
    <div class="notify-channel-list">
      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <div class="notify-channel-info">
            <span class="notify-channel-name">{{ t('edit.enableNotifications') }}</span>
            <span class="notify-channel-desc">{{ t('edit.masterSwitchEveryNotification') }}</span>
          </div>
          <a-switch
            v-model:checked="formData.Notify.Enabled"
            :checked-children="t('edit.enabled3')"
            :un-checked-children="t('edit.off')"
            @change="emitSave('Notify.Enabled', formData.Notify.Enabled)"
          />
        </div>
      </div>
      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <div class="notify-channel-info">
            <span class="notify-channel-name">{{ t('edit.sendStatistics') }}</span>
            <span class="notify-channel-desc">{{
              t('edit.includeRunStatisticsNotification')
            }}</span>
          </div>
          <a-switch
            v-model:checked="formData.Notify.IfSendStatistic"
            @change="emitSave('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)"
          />
        </div>
      </div>
      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <div class="notify-channel-info">
            <span class="notify-channel-name">{{ t('edit.emailNotification') }}</span>
            <span class="notify-channel-desc">{{ t('edit.emailRunResult') }}</span>
          </div>
          <a-switch
            v-model:checked="formData.Notify.IfSendMail"
            @change="emitSave('Notify.IfSendMail', formData.Notify.IfSendMail)"
          />
        </div>
        <Transition name="notify-expand">
          <div v-if="formData.Notify.IfSendMail" class="notify-channel-config">
            <a-form-item :label="t('edit.recipient')">
              <a-input
                v-model:value="formData.Notify.ToAddress"
                type="email"
                inputmode="email"
                autocomplete="email"
                :placeholder="t('edit.recipientAddress')"
                size="large"
                :disabled="!formData.Notify.IfSendMail"
                @blur="emitSave('Notify.ToAddress', formData.Notify.ToAddress)"
              />
            </a-form-item>
          </div>
        </Transition>
      </div>
      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <div class="notify-channel-info">
            <span class="notify-channel-name">{{ t('edit.serverchan2') }}</span>
            <span class="notify-channel-desc">{{ t('edit.pushRunResultThrough') }}</span>
          </div>
          <a-switch
            v-model:checked="formData.Notify.IfServerChan"
            @change="emitSave('Notify.IfServerChan', formData.Notify.IfServerChan)"
          />
        </div>
        <Transition name="notify-expand">
          <div v-if="formData.Notify.IfServerChan" class="notify-channel-config">
            <a-form-item :label="t('edit.serverchanKey')">
              <a-input-password
                v-model:value="formData.Notify.ServerChanKey"
                autocomplete="off"
                :placeholder="t('edit.serverchanSendkey')"
                size="large"
                :disabled="!formData.Notify.IfServerChan"
                @blur="emitSave('Notify.ServerChanKey', formData.Notify.ServerChanKey)"
              />
            </a-form-item>
          </div>
        </Transition>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { MaaFWUserConfig } from '@/types/script'

const { t } = useI18n()

defineProps<{
  formData: MaaFWUserConfig
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
}>()

const emitSave = (key: string, value: unknown) => {
  emit('save', key, value)
}
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
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  padding: 4px 16px;
}

.notify-channel-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.notify-channel-item:last-child {
  border-bottom: none;
}

.notify-channel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.notify-channel-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.notify-channel-name {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.notify-channel-desc {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.notify-channel-config {
  padding-top: 12px;
}

.notify-channel-config :deep(.ant-form-item) {
  margin-bottom: 0;
}

.notify-expand-enter-active,
.notify-expand-leave-active {
  overflow: hidden;
  transition:
    opacity 0.2s ease,
    max-height 0.2s ease,
    padding-top 0.2s ease;
}

.notify-expand-enter-from,
.notify-expand-leave-to {
  max-height: 0;
  opacity: 0;
  padding-top: 0;
}

@media (max-width: 768px) {
  .notify-channel-header {
    align-items: flex-start;
  }
}
</style>
