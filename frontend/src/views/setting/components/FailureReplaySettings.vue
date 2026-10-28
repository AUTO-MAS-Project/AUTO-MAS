<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import { useObsReplayApi } from '@/composables/useObsReplayApi'
import type { ObsReplayCheckResult } from '@/types/replay'

const { t } = useI18n()

const props = defineProps<{
  settings: GlobalConfig
  handleSettingChange: (
    category: keyof GlobalConfig,
    key: string,
    value: unknown
  ) => Promise<boolean>
}>()

const replaySettings = computed(() => props.settings.Replay ?? null)
const replayEnabled = computed(() => replaySettings.value?.Enabled ?? false)
const frameReplayEnabled = computed(() => replaySettings.value?.FrameReplay ?? false)
const replayPort = computed(() => replaySettings.value?.Port ?? 4455)
const videoStorageLimit = computed(() => replaySettings.value?.VideoStorageLimitMiB ?? 1024)
const videoStorageLimitDraft = ref<number | null>(videoStorageLimit.value)
const capturePath = ref<string | null>(null)
const passwordConfiguredOverride = ref<boolean | null>(null)
const passwordConfigured = computed(
  () => passwordConfiguredOverride.value ?? replaySettings.value?.PasswordConfigured ?? false
)

const password = ref('')
const savingPassword = ref(false)
const checking = ref(false)
const savingReplay = ref(false)
const savingVideoStorageLimit = ref(false)
const checkResult = ref<ObsReplayCheckResult | null>(null)
const { checkObsReplay, saveObsReplay } = useObsReplayApi()

const canSaveVideoStorageLimit = computed(
  () =>
    videoStorageLimitDraft.value !== null &&
    Number.isInteger(videoStorageLimitDraft.value) &&
    videoStorageLimitDraft.value >= 1 &&
    videoStorageLimitDraft.value <= 1048576 &&
    videoStorageLimitDraft.value !== videoStorageLimit.value
)

watch(videoStorageLimit, (value, previousValue) => {
  // 设置刷新只同步未修改的输入，保留尚未保存或保存失败的容量草稿。
  if (videoStorageLimitDraft.value === previousValue) videoStorageLimitDraft.value = value
})

const updateReplaySetting = async (key: string, value: unknown) => {
  try {
    await props.handleSettingChange('Replay', key, value)
    if (key === 'Port' || key === 'Password' || key === 'Enabled') checkResult.value = null
    return true
  } catch {
    // 设置页已经展示保存失败；保留当前输入供重试。
    return false
  }
}

const saveVideoStorageLimit = async () => {
  if (savingVideoStorageLimit.value || !canSaveVideoStorageLimit.value) return

  savingVideoStorageLimit.value = true
  try {
    // 调整容量会立即回收视频，仅在用户明确保存后提交最终值。
    await updateReplaySetting('VideoStorageLimitMiB', videoStorageLimitDraft.value)
  } finally {
    savingVideoStorageLimit.value = false
  }
}

const savePassword = async () => {
  const value = password.value
  if (!value) {
    message.warning(t('core.setting.replay.passwordEmpty'))
    return
  }

  savingPassword.value = true
  try {
    if (!(await updateReplaySetting('Password', value))) return
    password.value = ''
    passwordConfiguredOverride.value = true
    message.success(t('core.setting.replay.passwordSaved'))
  } finally {
    savingPassword.value = false
  }
}

const clearPassword = () => {
  Modal.confirm({
    // 与 a-modal 的 :z-index="900" 同理：遮罩整体压在标题栏（1000）之下，窗口控制按钮不被挡住
    zIndex: 900,
    title: t('core.setting.replay.clearPasswordTitle'),
    content: t('core.setting.replay.clearPasswordContent'),
    okText: t('core.setting.replay.clearPassword'),
    cancelText: t('core.common.cancel'),
    okButtonProps: { danger: true },
    onOk: async () => {
      if (!(await updateReplaySetting('Password', '')))
        throw new Error(t('core.setting.toast.saveFailed'))
      password.value = ''
      passwordConfiguredOverride.value = false
      message.success(t('core.setting.replay.passwordCleared'))
    },
  })
}

const runConnectionCheck = async () => {
  checking.value = true
  try {
    checkResult.value = await checkObsReplay()
    if (checkResult.value.connected && checkResult.value.replayActive) {
      message.success(t('core.setting.replay.checkDone'))
    }
  } catch (error) {
    checkResult.value = null
    message.error(error instanceof Error ? error.message : t('core.setting.replay.checkFailed'))
  } finally {
    checking.value = false
  }
}

const runSaveReplay = async () => {
  savingReplay.value = true
  try {
    capturePath.value = null
    const response = await saveObsReplay()
    capturePath.value = response.capture_path ?? null
    if (response.capture_path) {
      message.success(t('core.setting.replay.saveDone'))
    } else {
      message.warning(t('core.setting.replay.saveEmpty'))
    }
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('core.setting.replay.saveFailed'))
  } finally {
    savingReplay.value = false
  }
}
</script>

<template>
  <div class="form-section replay-settings">
    <div class="section-header">
      <h3>{{ t('core.setting.replay.section') }}</h3>
    </div>

    <a-alert type="info" show-icon class="replay-intro">
      <template #message>{{ t('core.setting.replay.intro') }}</template>
      <template #description>
        <p>{{ t('core.setting.replay.obsGuide') }}</p>
        <p>{{ t('core.setting.replay.durationGuide') }}</p>
      </template>
    </a-alert>

    <a-row :gutter="24">
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('core.setting.replay.enable') }}</span>
            <a-tooltip :title="t('core.setting.replay.enableTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-select
            :value="replayEnabled"
            size="large"
            style="width: 100%"
            @change="(value: any) => updateReplaySetting('Enabled', value)"
          >
            <a-select-option :value="true">{{ t('core.common.yes') }}</a-select-option>
            <a-select-option :value="false">{{ t('core.common.no') }}</a-select-option>
          </a-select>
        </div>
      </a-col>
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('core.setting.replay.port') }}</span>
            <a-tooltip :title="t('core.setting.replay.portTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-input-number
            :value="replayPort"
            :min="1"
            :max="65535"
            :precision="0"
            :disabled="!replayEnabled"
            size="large"
            style="width: 100%"
            @change="(value: number | null) => value !== null && updateReplaySetting('Port', value)"
          />
        </div>
      </a-col>
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('core.setting.replay.videoLimit') }}</span>
            <a-tooltip :title="t('core.setting.replay.videoLimitTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-space-compact size="large" style="width: 100%">
            <a-input-number
              v-model:value="videoStorageLimitDraft"
              :min="1"
              :max="1048576"
              :precision="0"
              :disabled="savingVideoStorageLimit"
              class="replay-limit-input"
            />
            <a-button
              :disabled="!canSaveVideoStorageLimit"
              :loading="savingVideoStorageLimit"
              @click="saveVideoStorageLimit"
            >
              {{ t('core.setting.replay.saveVideoLimit') }}
            </a-button>
          </a-space-compact>
        </div>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('core.setting.replay.password') }}</span>
            <a-tooltip :title="t('core.setting.replay.passwordTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-input-group compact>
            <a-input-password
              v-model:value="password"
              :disabled="!replayEnabled"
              :placeholder="t('core.setting.replay.passwordPlaceholder')"
              style="width: calc(100% - 160px)"
              @press-enter="savePassword"
            />
            <a-button
              :disabled="!replayEnabled || !password"
              :loading="savingPassword"
              @click="savePassword"
            >
              {{ t('core.setting.replay.savePassword') }}
            </a-button>
          </a-input-group>
          <div class="replay-password-status">
            <a-tag :color="passwordConfigured ? 'success' : 'default'">
              {{
                passwordConfigured
                  ? t('core.setting.replay.passwordConfigured')
                  : t('core.setting.replay.passwordNotConfigured')
              }}
            </a-tag>
            <a-button
              v-if="passwordConfigured"
              type="link"
              danger
              size="small"
              :disabled="!replayEnabled"
              @click="clearPassword"
            >
              {{ t('core.setting.replay.clearPassword') }}
            </a-button>
          </div>
        </div>
      </a-col>
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('core.setting.replay.actions') }}</span>
          </div>
          <a-space wrap>
            <a-button :disabled="!replayEnabled" :loading="checking" @click="runConnectionCheck">
              {{ t('core.setting.replay.check') }}
            </a-button>
            <a-button :disabled="!replayEnabled" :loading="savingReplay" @click="runSaveReplay">
              {{ t('core.setting.replay.saveTest') }}
            </a-button>
          </a-space>
        </div>
      </a-col>
    </a-row>

    <a-alert
      v-if="capturePath"
      type="info"
      show-icon
      class="replay-check-result"
      :message="t('core.setting.replay.capturePath')"
      :description="capturePath"
    />
    <a-alert
      v-if="checkResult"
      :type="checkResult.connected && checkResult.replayActive ? 'success' : 'warning'"
      show-icon
      class="replay-check-result"
    >
      <template #message>
        {{
          checkResult.connected && checkResult.replayActive
            ? t('core.setting.replay.checkPassed')
            : t('core.setting.replay.checkIssue')
        }}
      </template>
      <template #description>
        <div>
          {{ t('core.setting.replay.connection') }}:
          {{ checkResult.connected ? t('core.common.yes') : t('core.common.no') }}
        </div>
        <div>
          {{ t('core.setting.replay.buffer') }}:
          {{
            checkResult.replayActive
              ? t('core.setting.replay.active')
              : t('core.setting.replay.inactive')
          }}
        </div>
        <div v-if="checkResult.version">
          {{ t('core.setting.replay.version') }}: {{ checkResult.version }}
        </div>
        <div v-if="checkResult.directory" class="replay-path">{{ checkResult.directory }}</div>
      </template>
    </a-alert>

    <a-row :gutter="24">
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('core.setting.replay.frameEnable') }}</span>
            <a-tooltip :title="t('core.setting.replay.frameEnableTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-select
            :value="frameReplayEnabled"
            size="large"
            style="width: 100%"
            @change="(value: any) => updateReplaySetting('FrameReplay', value)"
          >
            <a-select-option :value="true">{{ t('core.common.yes') }}</a-select-option>
            <a-select-option :value="false">{{ t('core.common.no') }}</a-select-option>
          </a-select>
        </div>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.replay-intro {
  margin-bottom: 16px;
}

.replay-intro p {
  margin: 0 0 4px;
}

.replay-intro p:last-child {
  margin-bottom: 0;
}

.replay-password-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.replay-limit-input {
  flex: 1;
  min-width: 0;
}

.replay-check-result {
  margin-top: 4px;
}

.replay-path {
  margin-top: 4px;
  color: var(--ant-color-text-secondary);
  overflow-wrap: anywhere;
}
</style>
