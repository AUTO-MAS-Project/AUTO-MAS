<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import { VideoCameraOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import { useObsReplayApi } from '@/composables/useObsReplayApi'
import type { ObsReplayCheckResult } from '@/types/replay'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
import StatusChip from '@/components/ui/StatusChip.vue'

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

// 开启前才需要读一次的说明，收进卡片副标题，不占正文一行
const replayIntro = computed(() =>
  [
    t('core.setting.replay.intro'),
    t('core.setting.replay.obsGuide'),
    t('core.setting.replay.durationGuide'),
  ].join('')
)

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
  <SectionCard
    :title="t('core.setting.replay.section')"
    :subtitle="replayIntro"
    :icon="VideoCameraOutlined"
  >
    <SettingRow :label="t('core.setting.replay.enable')" :hint="t('core.setting.replay.enableTip')">
      <a-switch
        :checked="replayEnabled"
        :aria-label="t('core.setting.replay.enable')"
        @change="(checked: boolean | string | number) => updateReplaySetting('Enabled', !!checked)"
      />
    </SettingRow>

    <SettingRow :label="t('core.setting.replay.port')" :hint="t('core.setting.replay.portTip')">
      <a-input-number
        :value="replayPort"
        :min="1"
        :max="65535"
        :precision="0"
        :disabled="!replayEnabled"
        class="number-input"
        @change="(value: number | null) => value !== null && updateReplaySetting('Port', value)"
      />
    </SettingRow>

    <SettingRow
      :label="t('core.setting.replay.videoLimit')"
      :hint="t('core.setting.replay.videoLimitTip')"
    >
      <a-input-number
        v-model:value="videoStorageLimitDraft"
        :min="1"
        :max="1048576"
        :precision="0"
        :disabled="savingVideoStorageLimit"
        class="number-input"
      />
      <a-button
        :disabled="!canSaveVideoStorageLimit"
        :loading="savingVideoStorageLimit"
        @click="saveVideoStorageLimit"
      >
        {{ t('core.setting.replay.saveVideoLimit') }}
      </a-button>
    </SettingRow>

    <SettingRow
      :label="t('core.setting.replay.password')"
      :hint="t('core.setting.replay.passwordTip')"
    >
      <div class="password-control">
        <div class="password-control-main">
          <a-input-password
            v-model:value="password"
            :disabled="!replayEnabled"
            :placeholder="t('core.setting.replay.passwordPlaceholder')"
            class="password-input"
            autocomplete="off"
            @press-enter="savePassword"
          />
          <a-button
            :disabled="!replayEnabled || !password"
            :loading="savingPassword"
            @click="savePassword"
          >
            {{ t('core.setting.replay.savePassword') }}
          </a-button>
          <a-button
            v-if="passwordConfigured"
            type="link"
            danger
            size="small"
            class="clear-password-button"
            :disabled="!replayEnabled"
            @click="clearPassword"
          >
            {{ t('core.setting.replay.clearPassword') }}
          </a-button>
        </div>
        <StatusChip :tone="passwordConfigured ? 'success' : 'neutral'" :dot="false">
          {{
            passwordConfigured
              ? t('core.setting.replay.passwordConfigured')
              : t('core.setting.replay.passwordNotConfigured')
          }}
        </StatusChip>
      </div>
    </SettingRow>

    <SettingRow :label="t('core.setting.replay.actions')">
      <a-button :disabled="!replayEnabled" :loading="checking" @click="runConnectionCheck">
        {{ t('core.setting.replay.check') }}
      </a-button>
      <a-button :disabled="!replayEnabled" :loading="savingReplay" @click="runSaveReplay">
        {{ t('core.setting.replay.saveTest') }}
      </a-button>
    </SettingRow>

    <a-alert
      v-if="capturePath"
      type="info"
      show-icon
      class="replay-result"
      :message="t('core.setting.replay.capturePath')"
      :description="capturePath"
    />
    <a-alert
      v-if="checkResult"
      :type="checkResult.connected && checkResult.replayActive ? 'success' : 'warning'"
      show-icon
      class="replay-result"
    >
      <template #message>
        {{
          checkResult.connected && checkResult.replayActive
            ? t('core.setting.replay.checkPassed')
            : t('core.setting.replay.checkIssue')
        }}
      </template>
      <template #description>
        <div class="result-lines">
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
        </div>
      </template>
    </a-alert>
  </SectionCard>
</template>

<style scoped>
.number-input {
  width: 140px;
}

.password-control {
  display: flex;
  width: 100%;
  min-width: 0;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.password-control-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.password-input {
  width: 220px;
}

.clear-password-button {
  padding: 0;
  height: auto;
}

.replay-result {
  margin-top: 12px;
}

.result-lines {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.replay-path {
  color: var(--ant-color-text-secondary);
  overflow-wrap: anywhere;
}
</style>
