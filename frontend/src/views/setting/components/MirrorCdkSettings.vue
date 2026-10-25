<script setup lang="ts">
import { onScopeDispose, ref, watch } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig, SettingMirrorCdkData } from '@/api'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import MirrorCdkStatusHint from '@/components/MirrorCdkStatusHint.vue'
import { handleExternalLink } from '@/utils/openExternal'

const props = defineProps<{
  settings: GlobalConfig
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: unknown) => Promise<void>
}>()

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
</script>

<template>
  <div class="form-item-vertical">
    <div class="form-label-wrapper">
      <span class="form-label">{{ $t('setting.others.cdk') }}</span>
      <a-tooltip>
        <template #title>
          <div>
            {{ $t('setting.others.cdkIntro') }}
            <a
              href="https://mirrorchyan.com/zh/get-start?source=auto-mas-setting"
              class="tooltip-link"
              @click="handleExternalLink"
              >{{ $t('setting.others.cdkSite') }}</a
            >
            {{ $t('setting.others.cdkGet') }}
          </div>
        </template>
        <QuestionCircleOutlined class="help-icon" />
      </a-tooltip>
    </div>
    <a-input-password
      :value="cdk"
      :disabled="settings.Update?.Source !== 'MirrorChyan'"
      :placeholder="$t('setting.others.cdkPlaceholder')"
      :visibility-toggle="true"
      size="large"
      autocomplete="off"
      @update:value="handleInput"
      @blur="handleBlur"
    />
    <MirrorCdkStatusHint :state="state" :checking="checking" @retry="refresh" />
    <div class="form-hint">
      {{ $t('setting.others.cdkHint') }}
      <a
        href="https://mirrorchyan.com?source=automas_settings"
        class="form-hint-link"
        @click="handleExternalLink"
        >{{ $t('setting.others.cdkGetLink') }}</a
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

.form-hint-link {
  margin-left: 4px;
  color: var(--ant-color-primary);
  text-decoration: underline;
}

.form-hint-link:hover {
  color: var(--ant-color-primary-hover);
}
</style>
