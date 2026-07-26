<script setup lang="ts">
import {
  HomeOutlined,
  GithubOutlined,
  QqOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { GlobalConfig, VersionOut } from '@/api'
import { handleExternalLink } from '@/utils/openExternal'
import SettingTabHeader from './SettingTabHeader.vue'
import type { SettingsCategory } from '@/composables/useSettingsFormGuard'

const logger = window.electronAPI.getLogger('设置-其他')

const {
  version,
  backendUpdateInfo,
  settings,
  updateSourceOptions,
  updateChannelOptions,
  handleSettingChange,
  checkUpdate,
  getEffectiveValue,
  getError,
  clearError,
  hasPending,
  pendingCount,
  retryPending,
  restoreDefaults,
  isSaving,
} = defineProps<{
  version: string
  backendUpdateInfo: VersionOut | null
  settings: GlobalConfig
  updateSourceOptions: { label: string; value: string }[]
  updateChannelOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
  checkUpdate: () => Promise<void>
  /** Lane 8：表单保护 */
  getEffectiveValue: <T>(
    settings: GlobalConfig,
    category: SettingsCategory,
    key: string
  ) => T | undefined
  getError: (category: SettingsCategory) => string | null
  clearError: (category: SettingsCategory) => void
  hasPending: boolean
  pendingCount: number
  retryPending: (category: SettingsCategory) => Promise<void>
  revertField: (category: SettingsCategory, key: string) => void
  restoreDefaults: (category: SettingsCategory) => Promise<void>
  isSaving: (category: SettingsCategory, key: string) => boolean
}>()

// Lane 8：Update category 辅助
const CATEGORY: SettingsCategory = 'Update'
const eff = <T,>(key: string): T | undefined => getEffectiveValue<T>(settings, CATEGORY, key)
const saving = (key: string): boolean => isSaving(CATEGORY, key)
const errorMsg = (): string | null => getError(CATEGORY)
const onClearError = (): void => clearError(CATEGORY)
const onRetryPending = (): Promise<void> => retryPending(CATEGORY)
const onRestoreDefaults = (): Promise<void> => restoreDefaults(CATEGORY)

// 复制所有版本信息到剪贴板
const copyAllInfo = async () => {
  try {
    const copyText = [
      `软件版本：${version}`,
      `后端日期：${backendUpdateInfo?.current_time || '未知'}`,
      `后端哈希：${backendUpdateInfo?.current_hash || '未知'}`,
    ].join('\n')

    await navigator.clipboard.writeText(copyText)
    message.success('版本信息已复制到剪贴板')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`复制失败: ${errorMsg}`)
    // 降级方案：创建临时input元素
    const textArea = document.createElement('textarea')
    textArea.value = [
      `软件版本：${version}`,
      `后端日期：${backendUpdateInfo?.current_time || '未知'}`,
      `后端哈希：${backendUpdateInfo?.current_hash || '未知'}`,
    ].join('\n')
    document.body.appendChild(textArea)
    textArea.select()
    try {
      document.execCommand('copy')
      message.success('版本信息已复制到剪贴板')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`降级复制也失败: ${errorMsg}`)
      message.error('复制失败')
    }
    document.body.removeChild(textArea)
  }
}
</script>
<template>
  <div class="tab-content">
    <!-- 统一 Tab 状态条：说明、错误、恢复默认和重试 -->
    <SettingTabHeader
      description="配置更新源、网络代理、查看项目链接和应用版本信息。"
      :error="errorMsg()"
      :has-pending="hasPending"
      :pending-count="pendingCount"
      :retrying="false"
      :restoring="false"
      :can-restore-defaults="true"
      @clear-error="onClearError"
      @retry-pending="onRetryPending"
      @restore-defaults="onRestoreDefaults"
    >
      <template #extra-actions>
        <a-button type="primary" size="small" class="section-update-button" @click="checkUpdate">
          <template #icon>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path
                d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"
              />
            </svg>
          </template>
          检查更新
        </a-button>
      </template>
    </SettingTabHeader>

    <!-- ── 更新配置 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>更新配置</h3>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">启动时尝试更新后端</span>
          <span class="row-help">启动时尝试更新后端组件。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="启动时尝试更新后端组件">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('IfAutoUpdate')"
            :loading="saving('IfAutoUpdate')"
            aria-label="启动时尝试更新后端"
            @change="(checked: any) => handleSettingChange('Update', 'IfAutoUpdate', checked)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">更新源</span>
          <span class="row-help">选择下载软件更新的来源。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="选择下载软件更新的来源">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-select
            :value="eff<string>('Source')"
            :options="updateSourceOptions"
            size="middle"
            style="min-width: 160px"
            :loading="saving('Source')"
            @change="(value: any) => handleSettingChange('Update', 'Source', value)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">更新渠道</span>
          <span class="row-help">
            稳定版：BUG 较少，无法第一时间体验新功能；公测版：包含最新功能，但可能存在较多 BUG。
          </span>
        </div>
        <div class="row-control">
          <a-tooltip
            title="稳定版：BUG 较少，无法第一时间体验新功能；公测版：包含最新功能，但可能存在较多 BUG"
          >
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-select
            :value="eff<string>('Channel')"
            :options="updateChannelOptions"
            size="middle"
            style="min-width: 160px"
            :loading="saving('Channel')"
            @change="(value: any) => handleSettingChange('Update', 'Channel', value)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">网络代理地址</span>
          <span class="row-help">
            使用网络代理软件时，若出现网络连接问题，请尝试设置代理地址，此设置全局生效。
          </span>
        </div>
        <div class="row-control row-control-full">
          <a-input
            :value="eff<string>('ProxyAddress')"
            placeholder="请输入网络代理地址"
            size="middle"
            @blur="(e: any) => handleSettingChange('Update', 'ProxyAddress', e.target.value)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">Mirror酱 CDK</span>
          <span class="row-help">
            Mirror酱 CDK 是使用 Mirror 源进行高速下载的凭证，可前往 Mirror酱 官网获取。
          </span>
        </div>
        <div class="row-control row-control-full">
          <a-tooltip>
            <template #title>
              <div>
                Mirror酱CDK是使用Mirror源进行高速下载的凭证，可前往
                <a
                  href="https://mirrorchyan.com/zh/get-start?source=auto-mas-setting"
                  class="tooltip-link"
                  @click="handleExternalLink"
                  >Mirror酱官网</a
                >
                获取
              </div>
            </template>
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <!-- Lane 8：MirrorChyanCDK 为敏感字段，使用 password 类型输入 -->
          <a-input-password
            :value="eff<string>('MirrorChyanCDK')"
            :disabled="eff<string>('Source') !== 'MirrorChyan'"
            placeholder="使用Mirror源时请输入Mirror酱CDK"
            :visibility-toggle="true"
            size="middle"
            @blur="(e: any) => handleSettingChange('Update', 'MirrorChyanCDK', e.target.value)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">GitHub token / API key</span>
          <span class="row-help">用于 GitHub 更新请求的可选 token / API key。</span>
        </div>
        <div class="row-control row-control-full">
          <a-tooltip title="用于 GitHub 更新请求的可选 token/API key">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <!-- Lane 8：GitHubToken 为敏感字段，使用 password 类型输入 -->
          <a-input-password
            :value="eff<string>('GitHubToken')"
            :disabled="eff<string>('Source') !== 'GitHub'"
            placeholder="可选"
            :visibility-toggle="true"
            size="middle"
            @blur="(e: any) => handleSettingChange('Update', 'GitHubToken', e.target.value)"
          />
        </div>
      </div>
    </section>

    <!-- ── 项目链接 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>项目链接</h3>
      </header>
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">相关资源</span>
          <span class="row-help">访问官网、源代码仓库或加入用户社区。</span>
        </div>
        <div class="row-control row-control-full">
          <div class="link-grid">
            <div class="link-item">
              <div class="link-card">
                <div class="link-icon">
                  <HomeOutlined />
                </div>
                <div class="link-content">
                  <h4>软件官网</h4>
                  <p>查看最新版本和功能介绍</p>
                  <a href="https://auto-mas.top" class="link-button" @click="handleExternalLink"
                    >访问官网</a
                  >
                </div>
              </div>
            </div>
            <div class="link-item">
              <div class="link-card">
                <div class="link-icon">
                  <GithubOutlined />
                </div>
                <div class="link-content">
                  <h4>GitHub 仓库</h4>
                  <p>查看源代码、提交 issue 和捐赠</p>
                  <a
                    href="https://github.com/AUTO-MAS-Project/AUTO-MAS"
                    class="link-button"
                    @click="handleExternalLink"
                    >访问仓库</a
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
                  <h4>用户 QQ 群</h4>
                  <p>加入社区，获取帮助和交流</p>
                  <a
                    href="https://qm.qq.com/q/bd9fISNoME"
                    class="link-button"
                    @click="handleExternalLink"
                    >加入群聊</a
                  >
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── 应用信息 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>应用信息</h3>
        <a-button size="small" class="section-update-button" @click="copyAllInfo">
          复制版本信息
        </a-button>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">软件名</span>
          <span class="row-help">应用产品名称。</span>
        </div>
        <div class="row-control">
          <span class="info-value">AUTO-MAS</span>
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">开发者</span>
          <span class="row-help">应用维护团队。</span>
        </div>
        <div class="row-control">
          <span class="info-value">AUTO-MAS Team</span>
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">许可证</span>
          <span class="row-help">开源协议。</span>
        </div>
        <div class="row-control">
          <span class="info-value">AGPL-3.0 license</span>
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">软件版本</span>
          <span class="row-help">点击右侧徽章可复制完整版本信息到剪贴板。</span>
        </div>
        <div class="row-control">
          <a-tag color="blue" class="info-badge" @click="copyAllInfo">
            {{ version }}
          </a-tag>
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">后端日期</span>
          <span class="row-help">后端构建时间。</span>
        </div>
        <div class="row-control">
          <a-tag color="orange" class="info-badge" @click="copyAllInfo">
            {{ backendUpdateInfo?.current_time || '未知' }}
          </a-tag>
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">后端哈希</span>
          <span class="row-help">后端 Git 提交哈希。</span>
        </div>
        <div class="row-control">
          <a-tag color="purple" class="info-badge" @click="copyAllInfo">
            {{
              backendUpdateInfo?.current_hash
                ? backendUpdateInfo.current_hash.substring(0, 8)
                : '未知'
            }}
          </a-tag>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.help-icon {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-sm);
}

.info-value {
  color: var(--v6-color-text-secondary);
  font-variant-numeric: tabular-nums;
  font-size: var(--v6-font-size-sm);
}

/* Responsive grid for link cards: ensures cards expand to fill available width */
.link-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--v6-space-3);
  align-items: stretch;
  width: 100%;
  margin-top: var(--v6-space-1);
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

/* 右侧徽章样式 */
.info-badge {
  cursor: pointer;
  transition: all var(--v6-motion-fast) var(--v6-ease-out);
  user-select: none;
  margin: 0;
}

.info-badge:hover {
  transform: translateY(-1px);
  box-shadow: var(--v6-shadow-sm);
}

.info-badge:active {
  transform: translateY(0);
}

@container settings-content (max-width: 640px) {
  .link-grid {
    grid-template-columns: 1fr;
  }
}
</style>
