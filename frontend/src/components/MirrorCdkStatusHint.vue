<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoadingOutlined } from '@ant-design/icons-vue'
import { resolveCdkHint } from '@/utils/mirrorCdk'

const props = defineProps<{
  state: { status: string; expiredTime?: number | null; usingGlobalCdk?: boolean } | null
  checking: boolean
}>()
defineEmits<{ retry: [] }>()
const { t } = useI18n()

const hint = computed(() => resolveCdkHint(props.state?.status, props.state?.expiredTime))
const hintText = computed(() => {
  if (props.checking) return t('setting.others.cdkChecking')
  if (!props.state) return ''
  if (props.state.status === 'error') return t('setting.others.cdkCheckFailed')
  if (props.state.status === 'absent') return t('edit.cdkHintAbsent')
  const value = hint.value
  if (!value) return props.state.status === 'ok' ? t('setting.others.cdkValid') : ''
  const date = value.dateText ?? ''
  const remaining =
    value.daysLeft === null || !date
      ? ''
      : value.daysLeft < 1
        ? t('edit.cdkHintLessThanDay', { date })
        : t('edit.cdkHintRemaining', { days: value.daysLeft, date })
  switch (value.kind) {
    case 'remaining':
      return `${t('setting.others.cdkValid')} · ${remaining}`
    case 'expired':
      return date ? t('edit.cdkHintExpiredOn', { date }) : t('edit.cdkHintExpired')
    case 'invalid':
      return t('edit.cdkHintInvalid')
    case 'quota':
      return remaining ? t('edit.cdkHintQuotaRemaining', { remaining }) : t('edit.cdkHintQuota')
    case 'mismatched':
      return t('edit.cdkHintMismatched')
    case 'blocked':
      return t('edit.cdkHintBlocked')
  }
  return ''
})
const hintType = computed(() => {
  if (props.checking || props.state?.status === 'absent') return 'secondary'
  return props.state?.status !== 'ok' || hint.value?.warning ? 'warning' : 'success'
})
</script>

<template>
  <div v-if="hintText" class="cdk-status-hint" role="status" aria-live="polite">
    <a-typography-text :type="hintType">
      <LoadingOutlined v-if="checking" />
      <template v-if="state?.usingGlobalCdk && !checking && state.status !== 'absent'">
        {{ t('edit.cdkHintGlobal') }} ·
      </template>
      {{ hintText }}
    </a-typography-text>
    <a-button
      v-if="state?.status === 'error' && !checking"
      type="link"
      size="small"
      @click="$emit('retry')"
    >
      {{ t('apiErrors.retry') }}
    </a-button>
  </div>
</template>

<style scoped>
.cdk-status-hint {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
}

.cdk-status-hint :deep(.ant-typography) {
  font-size: inherit;
}
</style>
