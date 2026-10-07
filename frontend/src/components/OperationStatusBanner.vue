<template>
  <div class="operation-status-banner">
    <a-alert :type="alertType" show-icon :message="resolvedMessage">
      <template v-if="state === 'loading'" #icon>
        <LoadingOutlined spin />
      </template>
      <template v-if="retryable" #action>
        <a-button type="link" size="small" @click="emit('retry')">
          {{ t('common.retry') }}
        </a-button>
      </template>
    </a-alert>
    <DiagnosticsDetails v-if="detail" :detail="detail" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoadingOutlined } from '@ant-design/icons-vue'

import DiagnosticsDetails from './DiagnosticsDetails.vue'

defineOptions({ name: 'OperationStatusBanner' })

const props = defineProps<{
  state: 'loading' | 'success' | 'error' | 'warning' | 'unknown'
  messageKey?: string
  message?: string
  retryable?: boolean
  detail?: string
}>()

const emit = defineEmits<{ retry: [] }>()

const { t } = useI18n()

const ALERT_TYPES = {
  loading: 'info',
  success: 'success',
  error: 'error',
  warning: 'warning',
  unknown: 'warning',
} as const

const alertType = computed(() => ALERT_TYPES[props.state])
// 主文案只走 i18n 或调用方给的整句，技术原文不进来。
const resolvedMessage = computed(
  () => props.message ?? (props.messageKey ? t(props.messageKey) : '')
)
</script>

<style scoped>
.operation-status-banner {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
