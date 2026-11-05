<script setup lang="ts">
import { onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig, SettingMirrorCdkData } from '@/api'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import MirrorCdkStatusHint from '@/components/MirrorCdkStatusHint.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
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
</script>
<template>
  <!-- 行内控件：标签与 ⓘ 提示由 SettingRow 承担，这里只放输入、状态与续期入口 -->
  <SettingRow>
    <template #label>
      <a-tooltip>
        <template #title>
          <div>
            {{ t('core.setting.others.cdkIntro') }}
            <a
              href="https://mirrorchyan.com/zh/get-start?source=auto-mas-setting"
              class="tooltip-link"
              @click="handleExternalLink"
              >{{ t('core.setting.others.cdkSite') }}</a
            >
            {{ t('core.setting.others.cdkGet') }}
          </div>
          <div>{{ t('core.setting.others.cdkHint') }}</div>
        </template>
        <span class="cdk-label" tabindex="0">
          {{ t('core.setting.others.cdk') }}
          <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
        </span>
      </a-tooltip>
    </template>
    <div class="cdk-control">
      <div class="cdk-control-main">
        <a-input-password
          :value="cdk"
          :disabled="settings.Update?.Source !== 'MirrorChyan'"
          :placeholder="t('core.setting.others.cdkPlaceholder')"
          :visibility-toggle="true"
          class="cdk-input"
          autocomplete="off"
          @update:value="handleInput"
          @blur="handleBlur"
        />
        <a
          class="cdk-link"
          href="https://mirrorchyan.com?source=automas_settings"
          @click="handleExternalLink"
          >{{ t('core.setting.others.cdkGetLink') }}</a
        >
      </div>
      <MirrorCdkStatusHint :state="state" :checking="checking" @retry="refresh" />
    </div>
  </SettingRow>
</template>

<style scoped>
.cdk-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  cursor: help;
}

.cdk-label:focus-visible {
  border-radius: 3px;
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.cdk-control {
  display: flex;
  width: 100%;
  min-width: 0;
  flex-direction: column;
  align-items: flex-end;
}

.cdk-control-main {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.cdk-input {
  width: 260px;
}

.cdk-link {
  flex: 0 0 auto;
  color: var(--ant-color-primary);
  font-size: 13px;
}

.cdk-link:hover {
  color: var(--ant-color-primary-hover);
}
</style>
