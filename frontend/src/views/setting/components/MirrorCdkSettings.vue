<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoadingOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig, SettingMirrorCdkData } from '@/api'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { resolveCdkHint } from '@/utils/mirrorCdk'
import { handleExternalLink } from '@/utils/openExternal'

const props = defineProps<{
  settings: GlobalConfig
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: unknown) => Promise<void>
}>()

const { t } = useI18n()
const { queryMirrorCdk } = useSettingsApi()
const { enqueue } = useSaveQueue()
const cdk = ref('')
const checking = ref(false)
const state = ref<SettingMirrorCdkData | null>(null)
let querySequence = 0
let draftSequence = 0
let savedDraftSequence = 0

const invalidate = () => {
  querySequence += 1
  checking.value = false
  state.value = null
}

const refresh = async () => {
  const value = cdk.value.trim()
  if (!value || checking.value || (state.value && state.value.status !== 'error')) return
  const sequence = ++querySequence
  checking.value = true
  try {
    const result = await queryMirrorCdk(value)
    if (sequence === querySequence) state.value = result
  } finally {
    if (sequence === querySequence) checking.value = false
  }
}

const handleInput = (value: string) => {
  cdk.value = value
  draftSequence += 1
  invalidate()
}

// 打开页面、配置变化与失焦时才查询；编辑序号也能识别改回原值的草稿。
watch(
  () => [
    props.settings.Update?.MirrorChyanCDK,
    props.settings.Update?.Channel,
    props.settings.Update?.ProxyAddress,
  ],
  (values, previous) => {
    // 保存回读不能覆盖继续编辑的草稿；同一个值也不重复查询。
    const hasNewerDraft = draftSequence !== savedDraftSequence
    if (
      previous &&
      (hasNewerDraft || values[0] === cdk.value) &&
      values[1] === previous[1] &&
      values[2] === previous[2]
    )
      return
    if (!hasNewerDraft && (!previous || values[0] !== previous[0])) cdk.value = values[0] ?? ''
    invalidate()
    void refresh()
  },
  { immediate: true }
)
onScopeDispose(invalidate)

const handleBlur = async () => {
  const sequence = draftSequence
  const value = cdk.value
  void refresh()
  await enqueue(() => props.handleSettingChange('Update', 'MirrorChyanCDK', value))
  if (sequence === draftSequence && cdk.value === props.settings.Update?.MirrorChyanCDK) {
    savedDraftSequence = sequence
  }
}

const hint = computed(() => resolveCdkHint(state.value?.status, state.value?.expiredTime))
const hintText = computed(() => {
  if (checking.value) return t('setting.others.cdkChecking')
  if (!state.value) return ''
  if (state.value.status === 'error') return t('setting.others.cdkCheckFailed')
  const value = hint.value
  if (!value) return state.value.status === 'ok' ? t('setting.others.cdkValid') : ''
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
  if (checking.value) return 'secondary'
  return state.value?.status !== 'ok' || hint.value?.warning ? 'warning' : 'success'
})
</script>

<template>
  <div class="form-item-vertical">
    <div class="form-label-wrapper">
      <span class="form-label">{{ t('setting.others.cdk') }}</span>
      <a-tooltip>
        <template #title>
          <div>
            {{ t('setting.others.cdkIntro') }}
            <a
              href="https://mirrorchyan.com/zh/get-start?source=auto-mas-setting"
              class="tooltip-link"
              @click="handleExternalLink"
              >{{ t('setting.others.cdkSite') }}</a
            >
            {{ t('setting.others.cdkGet') }}
          </div>
        </template>
        <QuestionCircleOutlined class="help-icon" />
      </a-tooltip>
    </div>
    <a-input-password
      :value="cdk"
      :disabled="settings.Update?.Source !== 'MirrorChyan'"
      :placeholder="t('setting.others.cdkPlaceholder')"
      :visibility-toggle="true"
      size="large"
      autocomplete="off"
      @update:value="handleInput"
      @blur="handleBlur"
    />
    <div v-if="hintText" class="form-hint" role="status" aria-live="polite">
      <a-typography-text :type="hintType">
        <LoadingOutlined v-if="checking" />
        {{ hintText }}
      </a-typography-text>
      <a-button
        v-if="state?.status === 'error' && !checking"
        type="link"
        size="small"
        @click="refresh"
      >
        {{ t('apiErrors.retry') }}
      </a-button>
    </div>
    <div class="form-hint">
      {{ t('setting.others.cdkHint') }}
      <a
        href="https://mirrorchyan.com?source=automas_settings"
        class="form-hint-link"
        @click="handleExternalLink"
        >{{ t('setting.others.cdkGetLink') }}</a
      >
    </div>
  </div>
</template>

<style scoped>
.form-hint {
  margin-top: 6px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.5;
}

.form-hint :deep(.ant-typography) {
  font-size: inherit;
}

.form-hint-link {
  margin-left: 4px;
  color: var(--ant-color-primary);
  text-decoration: underline;
}

.form-hint-link:hover {
  color: var(--ant-color-primary-hover);
}
</style>
