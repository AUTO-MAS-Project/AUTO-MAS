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
  if (props.checking) return t('core.setting.others.cdkChecking')
  if (!props.state) return ''
  if (props.state.status === 'error') return t('core.setting.others.cdkCheckFailed')
  if (props.state.status === 'absent') return t('core.edit.cdkHintAbsent')
  const value = hint.value
  if (!value) return props.state.status === 'ok' ? t('core.setting.others.cdkValid') : ''
  const date = value.dateText ?? ''
  const remaining =
    value.daysLeft === null || !date
      ? ''
      : value.daysLeft < 1
        ? t('core.edit.cdkHintLessThanDay', { date })
        : t('core.edit.cdkHintRemaining', { days: value.daysLeft, date })
  switch (value.kind) {
    case 'remaining':
      return `${t('core.setting.others.cdkValid')} · ${remaining}`
    case 'expired':
      return date ? t('core.edit.cdkHintExpiredOn', { date }) : t('core.edit.cdkHintExpired')
    case 'invalid':
      return t('core.edit.cdkHintInvalid')
    case 'quota':
      return remaining
        ? t('core.edit.cdkHintQuotaRemaining', { remaining })
        : t('core.edit.cdkHintQuota')
    case 'mismatched':
      return t('core.edit.cdkHintMismatched')
    case 'blocked':
      return t('core.edit.cdkHintBlocked')
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
        {{ t('core.edit.cdkHintGlobal') }} ·
      </template>
      {{ hintText }}
    </a-typography-text>
    <a-button
      v-if="state?.status === 'error' && !checking"
      type="link"
      size="small"
      @click="$emit('retry')"
    >
      {{ t('core.apiErrors.retry') }}
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
