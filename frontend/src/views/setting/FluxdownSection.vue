<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { computed, onMounted, ref } from 'vue'
import { ApiError, GetService } from '@/api'
import type { GlobalConfig, FluxdownRecord, FluxdownReleaseOut } from '@/api'
import { useSettingsApi } from '@/composables/useSettingsApi'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import { useFluxdownInstallApi } from '@/composables/useFluxdownInstallApi'
import { handleExternalLink } from '@/utils/openExternal'

const logger = window.electronAPI.getLogger('设置-FluxDown')

const { t } = useI18n()

const { getSettings } = useSettingsApi()
const { fetchRelease, installFluxdown } = useFluxdownInstallApi()
const emit = defineEmits<{ installed: [] }>()

const props = defineProps<{
  settings: GlobalConfig
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
}>()

// FluxDown 路径：文件夹选择 + 全盘自动检测（CLI 便携版优先，无 CLI 只有全量版时警告）
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
      message.warning(t('core.setting.others.fluxdownDetectNotFound'))
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

// 下载历史：后端按追加顺序保存，展示时倒序（最新在上）。
// 父页面只在挂载时读取一次设置，下载终态后快照不会自动更新；打开面板时
// 拉取一次最新配置，避免刚产生的失败记录要离页重进才能看到/导出
const fetchedHistory = ref<FluxdownRecord[] | null>(null)
const historyLoading = ref(false)

const updateHistory = computed(() =>
  [...(fetchedHistory.value ?? props.settings.Update?.LastUpdateHistory ?? [])].reverse()
)

const openUpdateHistory = async () => {
  showUpdateHistory.value = true
  historyLoading.value = true
  try {
    const data = await getSettings()
    // 读取失败时 getSettings 返回 null（基础层已提示），此时保留原快照，
    // 不能把已有历史清成空
    const history = data?.Update?.LastUpdateHistory
    if (history) fetchedHistory.value = history
  } finally {
    historyLoading.value = false
  }
}

// 历史记录的状态是后端英文枚举，展示时按当前语言映射，未知值原样显示
const historyStatusLabels = computed<Record<string, string>>(() => ({
  success: t('core.setting.others.historyStatusSuccess'),
  failed: t('core.setting.others.historyStatusFailed'),
  checksum_fail: t('core.setting.others.historyStatusChecksumFail'),
  interrupted: t('core.setting.others.historyStatusInterrupted'),
  fluxdown_fallback: t('core.setting.others.historyStatusFluxdownFallback'),
}))

const formatHistoryStatus = (status?: string | null) =>
  (status && historyStatusLabels.value[status]) || status || t('core.common.unknown')

const formatHistorySize = (size?: number | null) =>
  size ? `${(size / 1024 / 1024).toFixed(1)} MB` : '-'

const formatHistoryDuration = (ms?: number | null) => (ms ? `${(ms / 1000).toFixed(1)}s` : '-')

// 失败/回退记录可导出：把这条下载记录存成 JSON 文件
const handleExportHistory = async (item: FluxdownRecord) => {
  try {
    const fileName = `fluxdown-download-${(item.timestamp ?? '').replace(/[: ]/g, '-')}.json`
    const result = await window.electronAPI.saveTextFile(
      fileName,
      JSON.stringify(item, null, 2),
      [{ name: 'JSON', extensions: ['json'] }],
      {
        dialogTitle: t('core.setting.others.historyExportDialogTitle'),
        buttonLabel: t('core.setting.others.historyExportSaveLabel'),
      }
    )
    if (result.success) {
      message.success(t('core.setting.others.historyExportSuccess'))
    } else if (result.error && result.error !== '用户取消') {
      message.error(result.error)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`导出下载日志失败: ${errorMsg}`)
    message.error(t('core.setting.others.historyExportFailed'))
  }
}

const showUpdateHistory = ref(false)

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
onMounted(loadFluxdownRelease)

// 镜像只作用于本次下载，不落配置；下载失败时用户可直接换一个再试
const installMirror = ref('auto')
const mirrorOptions = computed(() => [
  { label: t('core.setting.others.fluxdownMirrorAuto'), value: 'auto' },
  { label: t('core.setting.others.fluxdownMirrorOfficial'), value: 'official' },
  { label: t('core.setting.others.fluxdownMirrorGhproxy'), value: 'ghproxy' },
  { label: t('core.setting.others.fluxdownMirrorGhfast'), value: 'ghfast' },
  { label: t('core.setting.others.fluxdownMirrorGithub'), value: 'github' },
])
const installing = ref(false)
const installState = ref<{
  type: 'secondary' | 'success' | 'warning'
  text: string
}>({ type: 'secondary', text: '' })

const handleMasInstall = async () => {
  installing.value = true
  installState.value = {
    type: 'secondary',
    text: t('core.setting.others.fluxdownInstallDownloading'),
  }
  try {
    const result = await installFluxdown(installMirror.value)
    if (!isDetectSuccess(result) || !result.path) {
      throw new Error(result.message || t('core.setting.others.fluxdownInstallFailed'))
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
  }
}
</script>

<template>
  <!-- FluxDown 下载器配置 -->
  <a-row :gutter="24">
    <a-col :span="8">
      <div class="form-item-vertical">
        <div class="form-label-wrapper">
          <span class="form-label">{{ t('core.setting.others.downloader') }}</span>
          <a-tooltip :title="t('core.setting.others.downloaderTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <a-select
          :value="settings.Update?.Downloader ?? 'builtin'"
          size="large"
          style="width: 100%"
          @change="(value: any) => handleSettingChange('Update', 'Downloader', value)"
        >
          <a-select-option value="builtin">{{
            t('core.setting.others.downloaderBuiltin')
          }}</a-select-option>
          <a-select-option value="fluxdown">{{
            t('core.setting.others.downloaderFluxdown')
          }}</a-select-option>
        </a-select>
      </div>
    </a-col>
    <a-col :span="8">
      <div class="form-item-vertical">
        <div class="form-label-wrapper">
          <span class="form-label">{{ t('core.setting.others.fluxdownSegments') }}</span>
          <a-tooltip :title="t('core.setting.others.fluxdownSegmentsTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <a-input-number
          :value="settings.Update?.FluxdownSegments ?? 8"
          :min="1"
          :max="32"
          size="large"
          style="width: 100%"
          :disabled="settings.Update?.Downloader !== 'fluxdown'"
          @change="(value: any) => handleSettingChange('Update', 'FluxdownSegments', value)"
        />
      </div>
    </a-col>
    <a-col :span="8">
      <div class="form-item-vertical">
        <div class="form-label-wrapper">
          <a-checkbox
            :checked="!!settings.Update?.FluxdownTakeoverAll"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('Update', 'FluxdownTakeoverAll', event.target.checked)
            "
          >
            {{ t('core.setting.others.fluxdownTakeover') }}
          </a-checkbox>
          <a-tooltip :title="t('core.setting.others.fluxdownTakeoverTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
      </div>
    </a-col>
  </a-row>
  <a-row :gutter="24">
    <a-col :span="16">
      <div class="form-item-vertical">
        <div class="form-label-wrapper">
          <span class="form-label">{{ t('core.setting.others.fluxdownPath') }}</span>
          <a-tooltip :title="t('core.setting.others.fluxdownPathTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <div class="fluxdown-path-row">
          <a-input
            :value="settings.Update?.FluxdownPath ?? ''"
            :placeholder="t('core.setting.others.fluxdownPathPlaceholder')"
            size="large"
            style="flex: 1"
            @blur="(e: any) => handleSettingChange('Update', 'FluxdownPath', e.target.value)"
          />
          <a-button size="large" @click="handleFluxdownBrowse">
            {{ t('core.setting.others.fluxdownBrowse') }}
          </a-button>
          <a-button size="large" :loading="fluxdownDetecting" @click="handleFluxdownDetect">
            {{ t('core.setting.others.fluxdownDetect') }}
          </a-button>
        </div>
        <div v-if="fluxdownOnlyFull" class="fluxdown-only-full-warning">
          {{ t('core.setting.others.fluxdownOnlyFullWarning') }}
        </div>
      </div>
    </a-col>
    <a-col :span="8">
      <div class="form-item-vertical">
        <div class="form-label-wrapper">
          <a-checkbox
            :checked="settings.Update?.FluxdownServerMode ?? true"
            :disabled="settings.Update?.Downloader !== 'fluxdown'"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('Update', 'FluxdownServerMode', event.target.checked)
            "
          >
            {{ t('core.setting.others.fluxdownServerMode') }}
          </a-checkbox>
          <a-tooltip :title="t('core.setting.others.fluxdownServerModeTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
      </div>
    </a-col>
  </a-row>
  <a-row :gutter="24">
    <a-col :span="8">
      <div class="form-item-vertical">
        <div class="form-label-wrapper">
          <span class="form-label">{{ t('core.setting.others.lastUpdateHistory') }}</span>
          <a-tooltip :title="t('core.setting.others.lastUpdateHistoryTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <a-button block size="large" :loading="historyLoading" @click="openUpdateHistory">
          {{ t('core.setting.others.viewHistory') }} ({{ updateHistory.length }})
        </a-button>
      </div>
    </a-col>
    <a-col :span="16">
      <div class="fluxdown-install-hint">
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
            style="width: 120px"
          />
          <a-button type="link" size="small" :loading="installing" @click="handleMasInstall">
            {{ t('core.setting.others.fluxdownInstallMasDownload') }}
          </a-button>
          <a-typography-text v-if="installState.text" :type="installState.type">
            {{ installState.text }}
          </a-typography-text>
        </div>
      </div>
    </a-col>
  </a-row>

  <a-modal
    v-model:open="showUpdateHistory"
    :title="t('core.setting.others.lastUpdateHistory')"
    :width="700"
    :footer="null"
    class="update-history-modal"
  >
    <a-spin :spinning="historyLoading">
      <a-timeline v-if="updateHistory.length">
        <a-timeline-item
          v-for="(item, idx) in updateHistory"
          :key="idx"
          :color="
            item.status === 'success'
              ? 'green'
              : item.status === 'checksum_fail'
                ? 'red'
                : item.status === 'fluxdown_fallback'
                  ? 'orange'
                  : 'red'
          "
        >
          <div class="history-item-title">
            {{ item.timestamp }} — {{ formatHistoryStatus(item.status) }}
          </div>
          <div class="history-item-path">{{ item.destination || item.url?.slice(0, 80) }}</div>
          <div class="history-item-meta">
            {{ formatHistorySize(item.size) }} ·
            {{ formatHistoryDuration(item.duration_ms) }}
            <span v-if="item.error" class="history-item-error"> — {{ item.error }}</span>
            <a-button
              v-if="item.status && item.status !== 'success'"
              type="link"
              size="small"
              class="history-export-button"
              @click="handleExportHistory(item)"
            >
              {{ t('core.setting.others.historyExport') }}
            </a-button>
          </div>
        </a-timeline-item>
      </a-timeline>
      <NoData v-else :description="t('core.setting.others.noHistory')" />
    </a-spin>
  </a-modal>
</template>

<style scoped>
.fluxdown-path-row {
  display: flex;
  gap: 8px;
}

.fluxdown-only-full-warning {
  margin-top: 6px;
  color: var(--ant-color-error);
  font-size: 12px;
  line-height: 1.5;
}

/* 与 Mirror 酱 CDK 下方的提示同款：小号、三级文字色、链接主色下划线 */
.fluxdown-install-hint {
  margin-top: 6px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.5;
}

.fluxdown-install-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.fluxdown-install-links a {
  color: var(--ant-color-primary);
  text-decoration: underline;
}

.fluxdown-install-links a:hover {
  color: var(--ant-color-primary-hover);
}

.fluxdown-install-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.update-history-modal :deep(.ant-modal-body) {
  padding: 24px;
}

.history-item-title {
  font-weight: 500;
  color: var(--ant-color-text);
}

.history-item-path {
  margin-top: 2px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  word-break: break-all;
}

.history-item-meta {
  margin-top: 2px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.history-item-error {
  color: var(--ant-color-error);
}

.history-export-button {
  padding: 0 0 0 8px;
  height: auto;
  font-size: 12px;
}
</style>
