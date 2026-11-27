<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { QrcodeOutlined } from '@ant-design/icons-vue'
import type { CredentialField } from '../gameSignAccounts'

/** 这一行凭据能走的自动获取方式；null 表示只能手填 */
export type CredentialAction = 'qr' | 'password' | 'sms'

const props = defineProps<{
  field: CredentialField
  /** 已经翻译好的平台名 */
  label: string
  placeholder: string
  value: string
  action: CredentialAction | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:value': [value: string]
  clear: []
  action: []
}>()

const { t } = useI18n()

const bound = computed(() => props.value.trim().length > 0)

const actionLabel = computed(() => {
  if (props.action === 'qr') return t('core.signflow.edit.qrLogin')
  if (props.action === 'password') return t('core.signflow.edit.passwordLogin')
  if (props.action === 'sms') return t('core.signflow.edit.smsLogin')
  return ''
})

const onInput = (value: string) => emit('update:value', value)
</script>

<template>
  <section class="credential-row">
    <div class="row-head">
      <span class="row-title">{{ props.label }}</span>
      <span class="row-tools">
        <a-button v-if="bound" type="link" size="small" :disabled="disabled" @click="emit('clear')">
          {{ t('core.signflow.cred.clear') }}
        </a-button>
        <a-button
          v-if="action"
          type="link"
          size="small"
          :disabled="disabled"
          @click="emit('action')"
        >
          <template v-if="action === 'qr'" #icon><QrcodeOutlined /></template>
          {{ actionLabel }}
        </a-button>
        <span v-else class="row-manual">{{ t('core.signflow.account.manualHint') }}</span>
      </span>
    </div>
    <a-input-password
      :value="props.value"
      size="large"
      allow-clear
      :disabled="disabled"
      :placeholder="props.placeholder"
      @update:value="onInput"
    />
  </section>
</template>

<style scoped>
.credential-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.row-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.row-tools {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.row-manual {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>
