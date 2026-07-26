<template>
  <div class="form-section">
    <div class="section-header">
      <h3>通知</h3>
    </div>
    <div class="notify-channel-list">
      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <div class="notify-channel-info">
            <span class="notify-channel-name">启用通知</span>
            <span class="notify-channel-desc">控制所有通知渠道的总开关</span>
          </div>
          <a-switch
            v-model:checked="formData.Notify.Enabled"
            checked-children="启用"
            un-checked-children="关闭"
            @change="emitSave('Notify.Enabled', formData.Notify.Enabled)"
          />
        </div>
      </div>
      <div class="notify-channel-item">
        <div class="notify-channel-header">
          <div class="notify-channel-info">
            <span class="notify-channel-name">发送统计</span>
            <span class="notify-channel-desc">在通知内容中附带运行统计信息</span>
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
            <span class="notify-channel-name">邮件通知</span>
            <span class="notify-channel-desc">发送运行结果到邮箱</span>
          </div>
          <a-switch
            v-model:checked="formData.Notify.IfSendMail"
            @change="emitSave('Notify.IfSendMail', formData.Notify.IfSendMail)"
          />
        </div>
        <Transition name="notify-expand">
          <div v-if="formData.Notify.IfSendMail" class="notify-channel-config">
            <a-form-item label="收件地址">
              <a-input
                v-model:value="formData.Notify.ToAddress"
                type="email"
                inputmode="email"
                autocomplete="email"
                placeholder="邮件收件地址…"
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
            <span class="notify-channel-name">Server 酱</span>
            <span class="notify-channel-desc">通过 Server 酱推送运行结果</span>
          </div>
          <a-switch
            v-model:checked="formData.Notify.IfServerChan"
            @change="emitSave('Notify.IfServerChan', formData.Notify.IfServerChan)"
          />
        </div>
        <Transition name="notify-expand">
          <div v-if="formData.Notify.IfServerChan" class="notify-channel-config">
            <a-form-item label="Server 酱密钥">
              <div class="sensitive-field">
                <a-input-password
                  :value="serverChanKeyDraft"
                  autocomplete="new-password"
                  :placeholder="serverChanKeyPlaceholder"
                  size="large"
                  :disabled="!formData.Notify.IfServerChan"
                  @update:value="updateServerChanKeyDraft"
                />
                <a-space>
                  <a-button
                    type="primary"
                    ghost
                    :disabled="!formData.Notify.IfServerChan || !serverChanKeyDraft"
                    @click="saveServerChanKey"
                  >
                    保存新值
                  </a-button>
                  <a-button
                    v-if="hasStoredServerChanKey"
                    danger
                    :disabled="!formData.Notify.IfServerChan"
                    @click="clearServerChanKey"
                  >
                    清空原值
                  </a-button>
                </a-space>
              </div>
            </a-form-item>
          </div>
        </Transition>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Modal } from 'ant-design-vue'
import type { MaaFWUserConfig } from '@/types/script'

const props = defineProps<{
  formData: MaaFWUserConfig
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
  sensitiveSave: [key: 'Notify.ServerChanKey', intent: 'replace' | 'clear', value?: string]
  sensitiveDirtyChange: [key: 'Notify.ServerChanKey', dirty: boolean]
}>()

const serverChanKeyDraft = ref('')
const hasStoredServerChanKey = computed(() => Boolean(props.formData.Notify.ServerChanKey))
const serverChanKeyPlaceholder = computed(() =>
  hasStoredServerChanKey.value ? '已保存；输入新值后明确保存' : 'Server 酱 SendKey…'
)

const updateServerChanKeyDraft = (value: string) => {
  serverChanKeyDraft.value = value
  emit('sensitiveDirtyChange', 'Notify.ServerChanKey', Boolean(value))
}

const saveServerChanKey = () => {
  if (!serverChanKeyDraft.value) return
  emit('sensitiveSave', 'Notify.ServerChanKey', 'replace', serverChanKeyDraft.value)
}

const clearServerChanKey = () => {
  Modal.confirm({
    title: '清空 Server 酱密钥？',
    content: '清空后 Server 酱通知将无法发送，且原值不可恢复。',
    okText: '清空',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => emit('sensitiveSave', 'Notify.ServerChanKey', 'clear', ''),
  })
}

defineExpose({
  resetServerChanKeyDraft: () => {
    serverChanKeyDraft.value = ''
    emit('sensitiveDirtyChange', 'Notify.ServerChanKey', false)
  },
})

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

.sensitive-field {
  display: grid;
  gap: var(--v6-space-2);
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
