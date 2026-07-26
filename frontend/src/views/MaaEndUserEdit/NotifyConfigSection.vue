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
        <!--
          Lane 06 任务书第 1、2 条：
          - ServerChanKey 是敏感字段（schema 中 sensitive=True，见 HSRUserNotifyConfig.ServerChanKey）。
          - 不得使用普通 a-input 直接绑定解密明文；改为 a-input-password + 草稿驱动。
          - 保存语义与 BasicInfoSection/SkylandConfigSection 一致：
            keep（省略） / replace（新值） / clear（空串）。
        -->
        <div class="sensitive-field-row">
          <a-input-password
            :value="serverChanKeyDraft"
            :placeholder="serverChanKeyPlaceholder"
            :disabled="loading || !formData.Notify.Enabled || !formData.Notify.IfServerChan"
            size="large"
            autocomplete="new-password"
            @update:value="(val: string) => handleServerChanKeyInput(val)"
            @blur="handleServerChanKeyBlur"
          />
          <a-button
            v-if="
              !loading &&
              formData.Notify.Enabled &&
              formData.Notify.IfServerChan &&
              hasStoredServerChanKey
            "
            size="small"
            type="link"
            danger
            :disabled="serverChanKeyExplicitlyCleared"
            @click="handleClearServerChanKey"
          >
            {{ serverChanKeyExplicitlyCleared ? '已清空' : '清空原值' }}
          </a-button>
        </div>
      </a-col>
    </a-row>

    <div style="margin-top: 16px">
      <WebhookManager mode="user" :script-id="scriptId" :user-id="userId" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import WebhookManager from '@/components/WebhookManager.vue'

const props = defineProps<{
  formData: any
  loading: boolean
  scriptId?: string
  userId?: string
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
  /**
   * 敏感字段保存意图（与 BasicInfoSection/SkylandConfigSection 一致，Lane 06 任务书第 2 条）：
   * - `keep`：未触碰 → 不发送给后端。
   * - `replace`：输入新值 → 发送新明文。
   * - `clear`：显式清空 → 发送空串 `""`。
   */
  sensitiveSave: [key: string, intent: 'keep' | 'replace' | 'clear', value?: string]
  sensitiveDirtyChange: [key: string, dirty: boolean]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}

// ============================================================
// ServerChanKey 敏感字段：草稿驱动，不在 DOM 显示明文
// ============================================================

const serverChanKeyDraft = ref('')
const serverChanKeyExplicitlyCleared = ref(false)

const hasStoredServerChanKey = computed(() => {
  const stored = props.formData?.Notify?.ServerChanKey
  return typeof stored === 'string' && stored.length > 0
})

const serverChanKeyPlaceholder = computed(() => {
  if (serverChanKeyExplicitlyCleared.value) {
    return '已清空。留空保持清空状态，输入新值替换'
  }
  if (hasStoredServerChanKey.value) {
    return '已保存。留空保持原值，输入新值替换'
  }
  return '请输入 SENDKEY'
})

const handleServerChanKeyInput = (val: string) => {
  serverChanKeyDraft.value = val
  if (val !== '' && serverChanKeyExplicitlyCleared.value) {
    serverChanKeyExplicitlyCleared.value = false
  }
  emit(
    'sensitiveDirtyChange',
    'Notify.ServerChanKey',
    val !== '' || serverChanKeyExplicitlyCleared.value
  )
}

const handleClearServerChanKey = () => {
  if (!hasStoredServerChanKey.value) {
    return
  }
  serverChanKeyDraft.value = ''
  serverChanKeyExplicitlyCleared.value = true
  emit('sensitiveDirtyChange', 'Notify.ServerChanKey', true)
}

const handleServerChanKeyBlur = () => {
  if (serverChanKeyExplicitlyCleared.value) {
    emit('sensitiveSave', 'Notify.ServerChanKey', 'clear', '')
    return
  }
  if (serverChanKeyDraft.value === '') {
    emit('sensitiveSave', 'Notify.ServerChanKey', 'keep')
    return
  }
  emit('sensitiveSave', 'Notify.ServerChanKey', 'replace', serverChanKeyDraft.value)
}

watch(
  () => props.formData?.Notify?.ServerChanKey,
  () => {
    serverChanKeyDraft.value = ''
    serverChanKeyExplicitlyCleared.value = false
    emit('sensitiveDirtyChange', 'Notify.ServerChanKey', false)
  }
)

defineExpose({
  resetServerChanKeyDraft: () => {
    serverChanKeyDraft.value = ''
    serverChanKeyExplicitlyCleared.value = false
  },
  isServerChanKeyDirty: () =>
    serverChanKeyDraft.value !== '' || serverChanKeyExplicitlyCleared.value,
})
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

.sensitive-field-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  width: 100%;
}

.sensitive-field-row :deep(.ant-input-password) {
  width: 100%;
}

.sensitive-field-row :deep(.ant-btn-link) {
  padding: 0;
  height: auto;
  font-size: 12px;
  line-height: 1.5;
}
</style>
