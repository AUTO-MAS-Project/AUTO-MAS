<template>
  <div class="retryable-error-state">
    <a-alert type="error" show-icon :message="title" :description="recovery">
      <template v-if="canRetry" #action>
        <a-button type="primary" size="small" @click="emit('retry')">
          {{ t('common.retryAction') }}
        </a-button>
      </template>
    </a-alert>
    <DiagnosticsDetails :detail="error?.detail" :context="error?.context" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { AppErrorKind, AppRequestError } from '@/utils/appError'

import DiagnosticsDetails from './DiagnosticsDetails.vue'

defineOptions({ name: 'RetryableErrorState' })

const props = defineProps<{
  error?: AppRequestError | null
  messageKey?: string
  retryable?: boolean
}>()

const emit = defineEmits<{ retry: [] }>()

const { t } = useI18n()

const KIND_KEYS: Record<AppErrorKind, string> = {
  network_unavailable: 'error.kind.networkUnavailable',
  backend_unavailable: 'error.kind.backendUnavailable',
  invalid_input: 'error.kind.invalidInput',
  conflict: 'error.kind.conflict',
  protected_discard: 'error.kind.protectedDiscard',
  external_program: 'error.kind.externalProgram',
  permission_denied: 'error.kind.permissionDenied',
  unknown: 'error.kind.unknown',
}

const RECOVERY_KEYS: Record<AppErrorKind, string> = {
  network_unavailable: 'error.recovery.networkUnavailable',
  backend_unavailable: 'error.recovery.backendUnavailable',
  invalid_input: 'error.recovery.invalidInput',
  conflict: 'error.recovery.conflict',
  protected_discard: 'error.recovery.protectedDiscard',
  external_program: 'error.recovery.externalProgram',
  permission_denied: 'error.recovery.permissionDenied',
  unknown: 'error.recovery.unknown',
}

const kind = computed<AppErrorKind>(() => props.error?.kind ?? 'unknown')
// 每个失败都必须给一条下一步动作，不能只报「失败」。
const recovery = computed(() => t(RECOVERY_KEYS[kind.value]))
const title = computed(() => (props.messageKey ? t(props.messageKey) : t(KIND_KEYS[kind.value])))
const canRetry = computed(() => props.retryable ?? props.error?.retryable ?? true)
</script>

<style scoped>
.retryable-error-state {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
