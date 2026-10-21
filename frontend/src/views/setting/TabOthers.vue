<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  HomeOutlined,
  GithubOutlined,
  QqOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { computed, ref } from 'vue'
import { ApiError, GetService } from '@/api'
import type { GlobalConfig, FluxdownRecord, VersionOut } from '@/api'
import ChangelogView from '@/components/ChangelogView.vue'
import type { ChangelogData } from '@/utils/changelog'
import { MAS_QQ_GROUP_URL, handleExternalLink } from '@/utils/openExternal'
import { formatPauseUntil, getPauseDisabledDate, isUpdatePaused } from '@/composables/updatePause'
import { formatConfigDate, serializeConfigTime } from '@/utils/configDateTime'

const logger = window.electronAPI.getLogger('设置-其他')

const { t } = useI18n()

const {
  version,
  backendUpdateInfo,
  settings,
  updateSourceOptions,
  updateChannelOptions,
  handleSettingChange,
  checkUpdate,
} = defineProps<{
  version: string
  backendUpdateInfo: VersionOut | null
  settings: GlobalConfig
  updateSourceOptions: { label: string; value: string }[]
  updateChannelOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<void>
  checkUpdate: () => Promise<void>
}>()

// MFW 项目包的 GitHub 加速镜像：与后端 Update.GitHubMirror 的 OptionsValidator 一致，
// 多给一项用户选了就会被静默纠回
const githubMirrorOptions = computed(() => [
  { label: t('setting.others.githubMirrorAuto'), value: 'Auto' },
  { label: t('setting.others.githubMirrorOff'), value: 'Off' },
])

// 暂停更新：暂停中只展示状态条，未暂停展示日期选择器（最短 1 天、最长 35 天）
const pauseUntil = computed(() => settings.Update?.PauseUntil ?? '')
const isPaused = computed(() => isUpdatePaused(pauseUntil.value))
// 回调内会取当前日期，创建一次即可（跨午夜也不会按旧边界放行）
const pauseDisabledDate = getPauseDisabledDate()
const pauseUntilDisplay = computed(() => formatPauseUntil(pauseUntil.value))

const handlePauseUntilChange = (value: string | null) => {
  void handleSettingChange(
    'Update',
    'PauseUntil',
    value ? serializeConfigTime(`${value}T00:00:00`) : null
  )
}

// 下载历史：后端按追加顺序保存，展示时倒序（最新在上）
const updateHistory = computed(() => [...(settings.Update?.LastUpdateHistory ?? [])].reverse())

const formatHistorySize = (size?: number | null) =>
  size ? `${(size / 1024 / 1024).toFixed(1)} MB` : '-'

const formatHistoryDuration = (ms?: number | null) =>
  ms ? `${(ms / 1000).toFixed(1)}s` : '-'

// FluxDown 路径：文件夹选择 + 全盘自动检测（CLI 便携版优先，无 CLI 只有全量版时警告）
const fluxdownDetecting = ref(false)
const fluxdownOnlyFull = ref(false)

const handleFluxdownBrowse = async () => {
  const dir = await window.electronAPI.selectFolder()
  if (dir) {
    fluxdownOnlyFull.value = false
    await handleSettingChange('Update', 'FluxdownPath', dir)
  }
}

const handleFluxdownDetect = async () => {
  fluxdownDetecting.value = true
  try {
    const result = await GetService.detectFluxdownApiUpdateFluxdownDetectGet()
    if (result.path) {
      fluxdownOnlyFull.value = result.only_full_warning ?? false
      await handleSettingChange('Update', 'FluxdownPath', result.path)
      message.success(t('setting.others.fluxdownDetectFound', { path: result.path }))
    } else {
      fluxdownOnlyFull.value = false
      message.warning(t('setting.others.fluxdownDetectNotFound'))
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

// 失败/回退记录可导出：把这条下载记录存成 JSON 文件
const handleExportHistory = async (item: FluxdownRecord) => {
  try {
    const fileName = `fluxdown-download-${(item.timestamp ?? '').replace(/[: ]/g, '-')}.json`
    const result = await window.electronAPI.saveTextFile(
      fileName,
      JSON.stringify(item, null, 2),
      [{ name: 'JSON', extensions: ['json'] }],
    )
    if (result.success) {
      message.success(t('setting.others.historyExportSuccess'))
    } else if (result.error && result.error !== '用户取消') {
      message.error(result.error)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`导出下载日志失败: ${errorMsg}`)
    message.error(t('setting.others.historyExportFailed'))
  }
}

// 当前版本的更新日志在编译期从 res/version.json 注入（res/ 不进 Electron 产物）
const changelogVisible = ref(false)
const showUpdateHistory = ref(false)
const unreleasedChangelog = import.meta.env.VITE_APP_CHANGELOG_UNRELEASED ?? {}
const currentChangelog: ChangelogData = {
  [version]: import.meta.env.VITE_APP_CHANGELOG ?? {},
  // 开发构建里把还没进版本的「未发布」段也列出来，发布构建没有这一段
  ...(Object.keys(unreleasedChangelog).length > 0 ? { 未发布: unreleasedChangelog } : {}),
}

const buildCopyText = () =>
  [
    t('setting.others.copyVersion', { version }),
    t('setting.others.copyBackendHash', {
      hash: backendUpdateInfo?.current_hash || t('common.unknown'),
    }),
  ].join('\n')

// 复制所有版本信息到剪贴板
const copyAllInfo = async () => {
  try {
    const copyText = buildCopyText()

    await navigator.clipboard.writeText(copyText)
    message.success(t('setting.toast.versionCopied'))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`复制失败: ${errorMsg}`)
    // 降级方案：创建临时input元素
    const textArea = document.createElement('textarea')
    textArea.value = buildCopyText()
    document.body.appendChild(textArea)
    textArea.select()
    try {
      document.execCommand('copy')
      message.success(t('setting.toast.versionCopied'))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`降级复制也失败: ${errorMsg}`)
      message.error(t('setting.toast.copyFailed'))
    }
    document.body.removeChild(textArea)
  }
}
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.others.updateSection') }}</h3>
        <a-button type="primary" size="small" class="section-update-button" @click="checkUpdate">
          <template #icon>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path
                d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"
              />
            </svg>
          </template>
          {{ t('setting.others.checkUpdate') }}
        </a-button>
      </div>
      <!-- 暂停中：显著状态条（含副标题提示）；日期选择器常驻，暂停期间也可改截止日期 -->
      <a-alert
        v-if="isPaused"
        type="info"
        show-icon
        class="pause-status-alert"
        :message="t('setting.others.pauseStatus', { date: pauseUntilDisplay })"
        :description="t('setting.others.pauseStatusHint')"
      />
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.others.pauseUpdates') }}</span>
              <a-tooltip :title="t('setting.others.pauseUpdatesTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-date-picker
              :value="formatConfigDate(pauseUntil) || undefined"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              :disabled-date="pauseDisabledDate"
              :placeholder="t('setting.others.pausePlaceholder')"
              size="large"
              style="width: 100%"
              @change="handlePauseUntilChange"
            />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.others.updateBackend') }}</span>
              <a-tooltip :title="t('setting.others.updateBackendTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Update?.IfAutoUpdate"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Update', 'IfAutoUpdate', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.others.updateSource') }}</span>
              <a-tooltip :title="t('setting.others.updateSourceTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Update?.Source"
              :options="updateSourceOptions"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Update', 'Source', value)"
            />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.others.updateChannel') }}</span>
              <a-tooltip :title="t('setting.others.updateChannelTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Update?.Channel"
              :options="updateChannelOptions"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Update', 'Channel', value)"
            />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.others.proxy') }}</span>
              <a-tooltip :title="t('setting.others.proxyTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="settings.Update?.ProxyAddress"
              :placeholder="t('setting.others.proxyPlaceholder')"
              size="large"
              @blur="(e: any) => handleSettingChange('Update', 'ProxyAddress', e.target.value)"
            />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.others.githubMirror') }}</span>
              <a-tooltip :title="t('setting.others.githubMirrorTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <!-- 只管 MFW 项目包从 GitHub Release 下载；MAS 自身更新与 Mirror 酱源不受影响 -->
            <a-select
              :value="settings.Update?.GitHubMirror ?? 'Auto'"
              :options="githubMirrorOptions"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Update', 'GitHubMirror', value)"
            />
          </div>
        </a-col>
        <a-col :span="8">
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
              :value="settings.Update?.MirrorChyanCDK"
              :disabled="settings.Update?.Source !== 'MirrorChyan'"
              :placeholder="t('setting.others.cdkPlaceholder')"
              :visibility-toggle="true"
              size="large"
              @blur="(e: any) => handleSettingChange('Update', 'MirrorChyanCDK', e.target.value)"
            />
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
        </a-col>
      </a-row>

      <!-- FluxDown 下载器配置 -->
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.others.downloader') }}</span>
              <a-tooltip :title="t('setting.others.downloaderTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Update?.Downloader ?? 'builtin'"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Update', 'Downloader', value)"
            >
              <a-select-option value="builtin">{{ t('setting.others.downloaderBuiltin') }}</a-select-option>
              <a-select-option value="fluxdown">{{ t('setting.others.downloaderFluxdown') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.others.fluxdownSegments') }}</span>
              <a-tooltip :title="t('setting.others.fluxdownSegmentsTip')">
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
              <span class="form-label">{{ t('setting.others.fluxdownTakeover') }}</span>
              <a-tooltip :title="t('setting.others.fluxdownTakeoverTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="!!settings.Update?.FluxdownTakeoverAll"
              size="large"
              style="width: 100%"
              :disabled="settings.Update?.Downloader !== 'fluxdown'"
              @change="(checked: any) => handleSettingChange('Update', 'FluxdownTakeoverAll', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="16">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.others.fluxdownPath') }}</span>
              <a-tooltip :title="t('setting.others.fluxdownPathTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <div class="fluxdown-path-row">
              <a-input
                :value="settings.Update?.FluxdownPath ?? ''"
                :placeholder="t('setting.others.fluxdownPathPlaceholder')"
                size="large"
                style="flex: 1"
                @blur="(e: any) => handleSettingChange('Update', 'FluxdownPath', e.target.value)"
              />
              <a-button size="large" @click="handleFluxdownBrowse">
                {{ t('setting.others.fluxdownBrowse') }}
              </a-button>
              <a-button size="large" :loading="fluxdownDetecting" @click="handleFluxdownDetect">
                {{ t('setting.others.fluxdownDetect') }}
              </a-button>
            </div>
            <div v-if="fluxdownOnlyFull" class="fluxdown-only-full-warning">
              {{ t('setting.others.fluxdownOnlyFullWarning') }}
            </div>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.others.fluxdownServerMode') }}</span>
              <a-tooltip :title="t('setting.others.fluxdownServerModeTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Update?.FluxdownServerMode ?? true"
              size="large"
              style="width: 100%"
              :disabled="settings.Update?.Downloader !== 'fluxdown'"
              @change="(checked: any) => handleSettingChange('Update', 'FluxdownServerMode', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.others.lastUpdateHistory') }}</span>
              <a-tooltip :title="t('setting.others.lastUpdateHistoryTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-button
              block
              size="large"
              :disabled="!settings.Update?.LastUpdateHistory?.length"
              @click="showUpdateHistory = true"
            >
              {{ t('setting.others.viewHistory') }} ({{ settings.Update?.LastUpdateHistory?.length ?? 0 }})
            </a-button>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.others.linkSection') }}</h3>
      </div>
      <div class="link-grid">
        <div class="link-item">
          <div class="link-card">
            <div class="link-icon">
              <HomeOutlined />
            </div>
            <div class="link-content">
              <h4>{{ t('setting.others.site') }}</h4>
              <p>{{ t('setting.others.siteDesc') }}</p>
              <a href="https://auto-mas.top" class="link-button" @click="handleExternalLink">{{
                t('setting.others.visitSite')
              }}</a>
            </div>
          </div>
        </div>
        <div class="link-item">
          <div class="link-card">
            <div class="link-icon">
              <GithubOutlined />
            </div>
            <div class="link-content">
              <h4>{{ t('setting.others.repo') }}</h4>
              <p>{{ t('setting.others.repoDesc') }}</p>
              <a
                href="https://github.com/AUTO-MAS-Project/AUTO-MAS"
                class="link-button"
                @click="handleExternalLink"
                >{{ t('setting.others.visitRepo') }}</a
              >
            </div>
          </div>
        </div>
        <div class="link-item">
          <div class="link-card">
            <div class="link-icon">
              <QqOutlined />
            </div>
            <div class="link-content">
              <h4>{{ t('setting.others.qq') }}</h4>
              <p>{{ t('setting.others.qqDesc') }}</p>
              <a :href="MAS_QQ_GROUP_URL" class="link-button" @click="handleExternalLink">{{
                t('setting.others.joinQq')
              }}</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.others.appSection') }}</h3>
      </div>
      <div class="app-info-container">
        <div class="app-info-left">
          <div class="info-item">
            <span class="info-label">{{ t('setting.others.appName') }}</span>
            <span class="info-value">AUTO-MAS</span>
          </div>
          <div class="info-item">
            <span class="info-label">{{ t('setting.others.developer') }}</span>
            <span class="info-value">AUTO-MAS Team</span>
          </div>
          <div class="info-item">
            <span class="info-label">{{ t('setting.others.license') }}</span>
            <span class="info-value">AGPL-3.0 license</span>
          </div>
        </div>
        <div class="app-info-right">
          <div class="info-item">
            <span class="info-label">{{ t('setting.others.appVersion') }}</span>
            <a-tag color="blue" class="info-badge" @click="copyAllInfo">
              {{ version }}
            </a-tag>
            <a-button
              type="link"
              size="small"
              class="changelog-button"
              @click="changelogVisible = true"
            >
              {{ t('setting.others.viewChangelog') }}
            </a-button>
          </div>
          <div class="info-item">
            <span class="info-label">{{ t('setting.others.backendHash') }}</span>
            <a-tag color="purple" class="info-badge" @click="copyAllInfo">
              {{
                backendUpdateInfo?.current_hash
                  ? backendUpdateInfo.current_hash.substring(0, 8)
                  : t('common.unknown')
              }}
            </a-tag>
          </div>
        </div>
      </div>
    </div>
  </div>

  <a-modal
    v-model:open="changelogVisible"
    :title="t('setting.others.changelogTitle', { version })"
    :width="800"
    :footer="null"
    class="changelog-modal"
  >
    <div class="changelog-modal-body">
      <ChangelogView :data="currentChangelog" />
    </div>
  </a-modal>

  <a-modal
    v-model:open="showUpdateHistory"
    :title="t('setting.others.lastUpdateHistory')"
    :width="700"
    :footer="null"
    class="update-history-modal"
  >
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
        <div class="history-item-title">{{ item.timestamp }} — {{ item.status }}</div>
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
            {{ t('setting.others.historyExport') }}
          </a-button>
        </div>
      </a-timeline-item>
    </a-timeline>
    <a-empty v-else :description="t('setting.others.noHistory')" />
  </a-modal>
</template>

<style scoped>
.changelog-button {
  padding: 0 4px;
  height: auto;
}

.changelog-modal :deep(.ant-modal-body) {
  padding: 16px 24px;
}

.changelog-modal-body {
  max-height: 60vh;
  overflow-y: auto;
  padding-right: 8px;
}

.section-update-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.pause-status-alert {
  margin-bottom: 16px;
}

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

/* Responsive grid for link cards: ensures cards expand to fill available width */
.link-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 24px;
  align-items: stretch;
  width: 100%;
}

.link-item {
  display: flex;
}

/* Make sure link-card fills its grid cell */
.link-card {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.link-content {
  flex: 1 1 auto;
}

/* 应用信息布局 */
.app-info-container {
  display: flex;
  gap: 32px;
  align-items: flex-start;
}

.app-info-left {
  flex: 1;
  min-width: 300px;
}

.app-info-right {
  flex: 1;
  min-width: 300px;
}

/* 右侧徽章样式 */
.info-badge {
  position: relative;
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
  margin-left: 8px;
}

.info-badge:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.info-badge:active {
  transform: translateY(0);
}

/* 响应式布局 */
@media (max-width: 768px) {
  .app-info-container {
    flex-direction: column;
    gap: 24px;
  }

  .app-info-left,
  .app-info-right {
    min-width: auto;
  }

  .badge-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .badge-label {
    min-width: auto;
  }

  .info-badge {
    align-self: stretch;
    justify-content: center;
  }
}
</style>
