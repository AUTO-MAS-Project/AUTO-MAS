<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { FolderOpenOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ApiError, GetService } from '@/api'
import type { GlobalConfig, FluxdownReleaseOut } from '@/api'
import { useFluxdownInstallApi } from '@/composables/useFluxdownInstallApi'
import { subscribe, unsubscribe } from '@/composables/useWebSocket'
import {
  WS_FLUXDOWN_INSTALL_PROGRESS,
  WS_ID_UPDATE,
  type WSFluxdownInstallProgressData,
} from '@/services/websocket/types'
import SettingRow from '@/components/ui/SettingRow.vue'
import DownloadHistorySettings from './components/DownloadHistorySettings.vue'
import { handleExternalLink } from '@/utils/openExternal'

const logger = window.electronAPI.getLogger('设置-FluxDown')

const { t } = useI18n()

const { fetchRelease, installFluxdown } = useFluxdownInstallApi()
const emit = defineEmits<{ installed: [] }>()

const props = defineProps<{
  settings: GlobalConfig
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
}>()

// FluxDown 路径：只自动选中 CLI + Agent/Daemon 均在同一目录的安装。
const fluxdownDetecting = ref(false)
const fluxdownOnlyFull = ref(false)

const handleFluxdownBrowse = async () => {
  const dir = await window.electronAPI.selectFolder()
  if (dir) {
    const saved = await props.handleSettingChange('Update', 'FluxdownPath', dir)
    if (saved) fluxdownOnlyFull.value = false
  }
}

// 后端内部异常时仍返回 HTTP 200，业务失败信息在 code/status 里，不能当成"未找到"
const isDetectSuccess = (result: { code?: number; status?: string }): boolean =>
  (result.code == null || result.code === 200) && result.status !== 'error'

const handleFluxdownDetect = async () => {
  fluxdownDetecting.value = true
  try {
    const result = await GetService.detectFluxdownApiUpdateFluxdownDetectGet()
    if (!isDetectSuccess(result)) {
      throw new Error(result.message || t('core.setting.others.fluxdownDetectFailed'))
    }
    if (result.path) {
      const saved = await props.handleSettingChange('Update', 'FluxdownPath', result.path)
      if (saved) {
        fluxdownOnlyFull.value = result.only_full_warning ?? false
        message.success(t('core.setting.others.fluxdownDetectFound', { path: result.path }))
      }
    } else {
      fluxdownOnlyFull.value = false
      message.warning(
        result.candidates?.length
          ? t('core.setting.others.fluxdownInstallMissing')
          : t('core.setting.others.fluxdownDetectNotFound')
      )
    }
  } catch (error) {
    const errorMsg =
      error instanceof ApiError && typeof error.body?.message === 'string'
        ? error.body.message
        : error instanceof Error
          ? error.message
          : String(error)
    logger.error(`FluxDown 自动检测失败: ${errorMsg}`)
    message.error(errorMsg)
  } finally {
    fluxdownDetecting.value = false
  }
}

// FluxDown 安装说明：两个发布包的 GitHub 直链 + 「由 MAS 代为下载」。
// Release 信息只在挂载时取一次；取不到时链接回退到 Release 页，安装入口照常可用
const release = ref<FluxdownReleaseOut | null>(null)
const fluxdownReleasePage = computed(
  () => release.value?.release_page || 'https://github.com/zerx-lab/FluxDown/releases/latest'
)

const loadFluxdownRelease = async () => {
  try {
    const result = await fetchRelease()
    if (isDetectSuccess(result)) release.value = result
    else logger.warn(`获取 FluxDown Release 信息失败: ${result.message ?? ''}`)
  } catch (error) {
    logger.warn(`获取 FluxDown Release 信息失败: ${String(error)}`)
  }
}
onMounted(() => {
  void loadFluxdownRelease()
  progressSubscription = subscribe(
    { id: WS_ID_UPDATE, type: WS_FLUXDOWN_INSTALL_PROGRESS },
    ({ data }) => {
      if (installing.value) installProgress.value = data
    }
  )
})
onBeforeUnmount(() => {
  if (progressSubscription) unsubscribe(progressSubscription)
})

// 镜像只作用于本次下载，不落配置；下载失败时用户可直接换一个再试
const installMirror = ref('auto')
const mirrorOptions = computed(() => [
  { label: t('core.setting.others.fluxdownMirrorAuto'), value: 'auto' },
  { label: t('core.setting.others.fluxdownMirrorOfficial'), value: 'official' },
  { label: t('core.setting.others.fluxdownMirrorGhproxy'), value: 'ghproxy' },
  { label: t('core.setting.others.fluxdownMirrorGhfast'), value: 'ghfast' },
  { label: t('core.setting.others.fluxdownMirrorGithub'), value: 'github' },
])
// 下载器二选一：两项都短，用分段控件直接摊开，省一次下拉展开
const downloaderOptions = computed(() => [
  { label: t('core.setting.others.downloaderBuiltin'), value: 'builtin' },
  { label: t('core.setting.others.downloaderFluxdown'), value: 'fluxdown' },
])

const installing = ref(false)
const installProgress = ref<WSFluxdownInstallProgressData | null>(null)
let progressSubscription: string | null = null

const formatBytes = (size: number) =>
  size >= 1024 * 1024
    ? `${(size / (1024 * 1024)).toFixed(1)} MB`
    : `${(size / 1024).toFixed(1)} KB`

const progressPercent = computed(() => {
  const progress = installProgress.value
  return progress?.total
    ? Math.min(100, Math.round((progress.downloaded / progress.total) * 100))
    : 0
})

const progressDescription = computed(() => {
  const progress = installProgress.value
  if (!progress) return ''
  const stages: Record<WSFluxdownInstallProgressData['stage'], string> = {
    check: 'fluxdownInstallChecking',
    download: 'fluxdownInstallDownloading',
    verify: 'fluxdownInstallVerifying',
    extract: 'fluxdownInstallExtracting',
    install: 'fluxdownInstallApplying',
    save: 'fluxdownInstallSaving',
    done: 'fluxdownInstallDownloading',
    failed: 'fluxdownInstallFailed',
  }
  return t(`core.setting.others.${stages[progress.stage]}`)
})
const installState = ref<{
  type: 'secondary' | 'success' | 'warning'
  text: string
}>({ type: 'secondary', text: '' })

const handleMasInstall = async () => {
  installing.value = true
  installProgress.value = null
  installState.value = {
    type: 'secondary',
    text: t('core.setting.others.fluxdownInstallDownloading'),
  }
  try {
    const result = await installFluxdown(installMirror.value)
    if (!isDetectSuccess(result) || !result.path) {
      throw new Error(result.message || t('core.setting.others.fluxdownInstallFailed'))
    }
    // 下载与安装成功不等于可用：自动走与「自动检测」按钮相同的后端入口。
    const detection = await GetService.detectFluxdownApiUpdateFluxdownDetectGet()
    if (
      !isDetectSuccess(detection) ||
      !detection.path ||
      detection.path.toLowerCase() !== result.path.toLowerCase()
    ) {
      throw new Error(t('core.setting.others.fluxdownInstallVerifyFailed'))
    }
    emit('installed')
    fluxdownOnlyFull.value = false
    const text = t('core.setting.others.fluxdownInstallSuccess', {
      version: result.version ?? '',
      path: result.path,
    })
    installState.value = { type: 'success', text }
    message.success(text)
  } catch (error) {
    const errorMsg =
      error instanceof ApiError && typeof error.body?.message === 'string'
        ? error.body.message
        : error instanceof Error
          ? error.message
          : String(error)
    logger.error(`FluxDown 代为下载失败: ${errorMsg}`)
    message.error(errorMsg)
    installState.value = {
      type: 'warning',
      text: t('core.setting.others.fluxdownInstallFailed'),
    }
  } finally {
    installing.value = false
    installProgress.value = null
  }
}
</script>

<template>
  <!-- 下载与安装：与更新源同属一张卡片，每项一行 -->
  <SettingRow
    :label="t('core.setting.others.downloader')"
    :hint="t('core.setting.others.downloaderTip')"
  >
    <a-segmented
      :value="settings.Update?.Downloader ?? 'builtin'"
      :options="downloaderOptions"
      @change="(value: any) => handleSettingChange('Update', 'Downloader', value)"
    />
  </SettingRow>

  <SettingRow
    :label="t('core.setting.others.fluxdownPath')"
    :hint="t('core.setting.others.fluxdownPathTip')"
  >
    <div class="path-control">
      <div class="path-control-main">
        <a-input
          :value="settings.Update?.FluxdownPath ?? ''"
          :placeholder="t('core.setting.others.fluxdownPathPlaceholder')"
          class="path-input"
          @blur="(e: any) => handleSettingChange('Update', 'FluxdownPath', e.target.value)"
        />
        <a-tooltip :title="t('core.setting.others.fluxdownBrowse')">
          <a-button
            :aria-label="t('core.setting.others.fluxdownBrowse')"
            @click="handleFluxdownBrowse"
          >
            <template #icon><FolderOpenOutlined /></template>
          </a-button>
        </a-tooltip>
        <a-button
          type="link"
          size="small"
          :loading="fluxdownDetecting"
          @click="handleFluxdownDetect"
        >
          {{ t('core.setting.others.fluxdownDetect') }}
        </a-button>
      </div>
      <div v-if="fluxdownOnlyFull" class="fluxdown-only-full-warning">
        {{ t('core.setting.others.fluxdownOnlyFullWarning') }}
      </div>
      <!-- 未安装时需要的两个发布包链接与镜像选择，收在路径行下方，不再另开一块正文 -->
      <div v-if="settings.Update?.Downloader === 'fluxdown'" class="fluxdown-install-hint">
        <div>{{ t('core.setting.others.fluxdownInstallHint') }}</div>
        <div class="fluxdown-install-links">
          <template v-if="release?.cli_url && release?.server_url">
            <a :href="release.cli_url" @click="handleExternalLink">
              {{ t('core.setting.others.fluxdownInstallCliLink', { version: release.version }) }}
            </a>
            <a :href="release.server_url" @click="handleExternalLink">
              {{ t('core.setting.others.fluxdownInstallServerLink', { version: release.version }) }}
            </a>
          </template>
          <a v-else :href="fluxdownReleasePage" @click="handleExternalLink">
            {{ t('core.setting.others.fluxdownInstallReleasePage') }}
          </a>
        </div>
        <div class="fluxdown-install-actions">
          <span>{{ t('core.setting.others.fluxdownInstallMirror') }}</span>
          <a-select
            v-model:value="installMirror"
            :options="mirrorOptions"
            size="small"
            style="width: 104px"
          />
          <a-button type="link" size="small" :loading="installing" @click="handleMasInstall">
            {{ t('core.setting.others.fluxdownInstallMasDownload') }}
          </a-button>
          <a-typography-text v-if="installState.text" :type="installState.type">
            {{ installState.text }}
          </a-typography-text>
        </div>
        <div v-if="installing && installProgress" class="fluxdown-progress" role="status">
          <div class="fluxdown-progress-info">
            {{ progressDescription }}
            <span v-if="installProgress.name">{{ installProgress.name }}</span>
          </div>
          <template v-if="installProgress.stage === 'download'">
            <a-progress
              v-if="installProgress.total > 0"
              :percent="progressPercent"
              size="small"
              :stroke-width="6"
              :show-info="true"
            />
            <div class="fluxdown-progress-info">
              {{ formatBytes(installProgress.downloaded) }}
              <template v-if="installProgress.total > 0">
                / {{ formatBytes(installProgress.total) }}
              </template>
              <template v-if="installProgress.speed > 0">
                · {{ formatBytes(installProgress.speed) }}/s
              </template>
            </div>
          </template>
        </div>
      </div>
    </div>
  </SettingRow>

  <SettingRow
    :label="t('core.setting.others.fluxdownSegments')"
    :hint="t('core.setting.others.fluxdownSegmentsTip')"
  >
    <a-input-number
      :value="settings.Update?.FluxdownSegments ?? 8"
      :min="1"
      :max="32"
      :precision="0"
      :disabled="settings.Update?.Downloader !== 'fluxdown'"
      :aria-label="t('core.setting.others.fluxdownSegments')"
      @change="
        (value: number | string | null) =>
          typeof value === 'number' && handleSettingChange('Update', 'FluxdownSegments', value)
      "
    />
  </SettingRow>

  <SettingRow
    :label="t('core.setting.others.fluxdownTakeover')"
    :hint="t('core.setting.others.fluxdownTakeoverTip')"
  >
    <a-switch
      :checked="!!settings.Update?.FluxdownTakeoverAll"
      :aria-label="t('core.setting.others.fluxdownTakeover')"
      @change="
        (checked: boolean | string | number) =>
          handleSettingChange('Update', 'FluxdownTakeoverAll', !!checked)
      "
    />
  </SettingRow>

  <SettingRow
    :label="t('core.setting.others.fluxdownServerMode')"
    :hint="t('core.setting.others.fluxdownServerModeTip')"
  >
    <a-switch
      :checked="settings.Update?.FluxdownServerMode ?? true"
      :disabled="settings.Update?.Downloader !== 'fluxdown'"
      :aria-label="t('core.setting.others.fluxdownServerMode')"
      @change="
        (checked: boolean | string | number) =>
          handleSettingChange('Update', 'FluxdownServerMode', !!checked)
      "
    />
  </SettingRow>

  <DownloadHistorySettings :settings="settings" />
</template>

<style scoped>
.path-control {
  display: flex;
  width: 100%;
  min-width: 0;
  flex-direction: column;
  align-items: flex-end;
}

.path-control-main {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.path-input {
  width: 260px;
}

.fluxdown-only-full-warning {
  margin-top: 6px;
  color: var(--ant-color-error);
  font-size: 12px;
  line-height: 1.5;
}

/* 与 Mirror 酱 CDK 的状态行同款：小号、三级文字色、链接主色 */
.fluxdown-install-hint {
  margin-top: 6px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.5;
  text-align: right;
}

.fluxdown-install-links {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.fluxdown-install-links a {
  color: var(--ant-color-primary);
  text-decoration: underline;
}

.fluxdown-install-links a:hover {
  color: var(--ant-color-primary-hover);
}

.fluxdown-progress {
  margin-top: 8px;
  width: 100%;
  max-width: 400px;
  text-align: left;
}

.fluxdown-progress-info {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.fluxdown-install-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
