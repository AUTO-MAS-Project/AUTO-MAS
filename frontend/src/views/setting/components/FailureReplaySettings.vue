<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import { FolderOpenOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import { useObsReplayApi } from '@/composables/useObsReplayApi'
import type { ObsReplayCheckResult } from '@/types/replay'

const { t } = useI18n()

const props = defineProps<{
  settings: GlobalConfig
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: unknown) => Promise<void>
}>()

const replaySettings = computed(() => props.settings.Replay ?? null)
const replayEnabled = computed(() => replaySettings.value?.Enabled ?? false)
const replayPort = computed(() => replaySettings.value?.Port ?? 4455)
const maxReplayCount = computed(() => replaySettings.value?.MaxReplayCount ?? 3)
const passwordConfiguredOverride = ref<boolean | null>(null)
const passwordConfigured = computed(
  () => passwordConfiguredOverride.value ?? replaySettings.value?.PasswordConfigured ?? false
)

const password = ref('')
const savingPassword = ref(false)
const checking = ref(false)
const savingReplay = ref(false)
const checkResult = ref<ObsReplayCheckResult | null>(null)
const { checkObsReplay, saveObsReplay, listObsReplays } = useObsReplayApi()

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

const savePassword = async () => {
  const value = password.value
  if (!value) {
    message.warning(t('setting.replay.passwordEmpty'))
    return
  }

  savingPassword.value = true
  try {
    if (!(await updateReplaySetting('Password', value))) return
    password.value = ''
    passwordConfiguredOverride.value = true
    message.success(t('setting.replay.passwordSaved'))
  } finally {
    savingPassword.value = false
  }
}

const clearPassword = () => {
  Modal.confirm({
    // 与 a-modal 的 :z-index="900" 同理：遮罩整体压在标题栏（1000）之下，窗口控制按钮不被挡住
    zIndex: 900,
    title: t('setting.replay.clearPasswordTitle'),
    content: t('setting.replay.clearPasswordContent'),
    okText: t('setting.replay.clearPassword'),
    cancelText: t('common.cancel'),
    okButtonProps: { danger: true },
    onOk: async () => {
      if (!(await updateReplaySetting('Password', '')))
        throw new Error(t('setting.toast.saveFailed'))
      password.value = ''
      passwordConfiguredOverride.value = false
      message.success(t('setting.replay.passwordCleared'))
    },
  })
}

const runConnectionCheck = async () => {
  checking.value = true
  try {
    checkResult.value = await checkObsReplay()
    if (checkResult.value.connected && checkResult.value.replayActive) {
      message.success(t('setting.replay.checkDone'))
    }
  } catch (error) {
    checkResult.value = null
    message.error(error instanceof Error ? error.message : t('setting.replay.checkFailed'))
  } finally {
    checking.value = false
  }
}

const runSaveReplay = async () => {
  savingReplay.value = true
  try {
    const response = await saveObsReplay()
    if (response.replay) {
      message.success(t('setting.replay.saveDone'))
    } else {
      message.warning(t('setting.replay.saveEmpty'))
    }
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('setting.replay.saveFailed'))
  } finally {
    savingReplay.value = false
  }
}

const openReplayDirectory = async () => {
  try {
    if (!window.electronAPI?.openFile) {
      message.error(t('history.replays.openDirectoryUnsupported'))
      return
    }
    const directory = checkResult.value?.directory || (await listObsReplays()).directory
    if (!directory) throw new Error(t('setting.replay.directoryUnavailable'))
    const result = await window.electronAPI.openFile(directory)
    if (!result.success) message.error(result.error || t('setting.replay.openDirectoryFailed'))
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('setting.replay.openDirectoryFailed'))
  }
}
</script>

<template>
  <div class="form-section replay-settings">
    <div class="section-header">
      <h3>{{ t('setting.replay.section') }}</h3>
    </div>

    <a-alert type="info" show-icon class="replay-intro">
      <template #message>{{ t('setting.replay.intro') }}</template>
      <template #description>
        <p>{{ t('setting.replay.obsGuide') }}</p>
        <p>{{ t('setting.replay.durationGuide') }}</p>
      </template>
    </a-alert>

    <a-row :gutter="24">
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.replay.enable') }}</span>
            <a-tooltip :title="t('setting.replay.enableTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-switch
            :checked="replayEnabled"
            :checked-children="t('common.yes')"
            :un-checked-children="t('common.no')"
            @change="(checked: boolean) => updateReplaySetting('Enabled', checked)"
          />
        </div>
      </a-col>
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.replay.port') }}</span>
            <a-tooltip :title="t('setting.replay.portTip')">
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
            <span class="form-label">{{ t('setting.replay.maxCount') }}</span>
            <a-tooltip :title="t('setting.replay.maxCountTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-input-number
            :value="maxReplayCount"
            :min="1"
            :max="20"
            :precision="0"
            :disabled="!replayEnabled"
            size="large"
            style="width: 100%"
            @change="
              (value: number | null) =>
                value !== null && updateReplaySetting('MaxReplayCount', value)
            "
          />
        </div>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.replay.password') }}</span>
            <a-tooltip :title="t('setting.replay.passwordTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-input-group compact>
            <a-input-password
              v-model:value="password"
              :disabled="!replayEnabled"
              :placeholder="t('setting.replay.passwordPlaceholder')"
              style="width: calc(100% - 160px)"
              @press-enter="savePassword"
            />
            <a-button
              :disabled="!replayEnabled || !password"
              :loading="savingPassword"
              @click="savePassword"
            >
              {{ t('setting.replay.savePassword') }}
            </a-button>
          </a-input-group>
          <div class="replay-password-status">
            <a-tag :color="passwordConfigured ? 'success' : 'default'">
              {{
                passwordConfigured
                  ? t('setting.replay.passwordConfigured')
                  : t('setting.replay.passwordNotConfigured')
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
              {{ t('setting.replay.clearPassword') }}
            </a-button>
          </div>
        </div>
      </a-col>
      <a-col :span="12">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.replay.actions') }}</span>
          </div>
          <a-space wrap>
            <a-button :disabled="!replayEnabled" :loading="checking" @click="runConnectionCheck">
              {{ t('setting.replay.check') }}
            </a-button>
            <a-button :disabled="!replayEnabled" :loading="savingReplay" @click="runSaveReplay">
              {{ t('setting.replay.saveTest') }}
            </a-button>
            <a-button @click="openReplayDirectory">
              <template #icon><FolderOpenOutlined /></template>
              {{ t('setting.replay.openDirectory') }}
            </a-button>
          </a-space>
        </div>
      </a-col>
    </a-row>

    <a-alert
      v-if="checkResult"
      :type="checkResult.connected && checkResult.replayActive ? 'success' : 'warning'"
      show-icon
      class="replay-check-result"
    >
      <template #message>
        {{
          checkResult.connected && checkResult.replayActive
            ? t('setting.replay.checkPassed')
            : t('setting.replay.checkIssue')
        }}
      </template>
      <template #description>
        <div>
          {{ t('setting.replay.connection') }}:
          {{ checkResult.connected ? t('common.yes') : t('common.no') }}
        </div>
        <div>
          {{ t('setting.replay.buffer') }}:
          {{ checkResult.replayActive ? t('setting.replay.active') : t('setting.replay.inactive') }}
        </div>
        <div v-if="checkResult.version">
          {{ t('setting.replay.version') }}: {{ checkResult.version }}
        </div>
        <div v-if="checkResult.directory" class="replay-path">{{ checkResult.directory }}</div>
      </template>
    </a-alert>
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

.replay-check-result {
  margin-top: 4px;
}

.replay-path {
  margin-top: 4px;
  color: var(--ant-color-text-secondary);
  overflow-wrap: anywhere;
}
</style>
