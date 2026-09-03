<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  HomeOutlined,
  GithubOutlined,
  QqOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { GlobalConfig, VersionOut } from '@/api'
import { MAS_QQ_GROUP_URL, handleExternalLink } from '@/utils/openExternal'

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

const buildCopyText = () =>
  [
    t('setting.others.copyVersion', { version }),
    t('setting.others.copyBackendDate', {
      date: backendUpdateInfo?.current_time || t('common.unknown'),
    }),
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
        <a-col :span="12">
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
        <a-col :span="12">
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
          </div>
          <div class="info-item">
            <span class="info-label">{{ t('setting.others.backendDate') }}</span>
            <a-tag color="orange" class="info-badge" @click="copyAllInfo">
              {{ backendUpdateInfo?.current_time || t('common.unknown') }}
            </a-tag>
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
</template>

<style scoped>
.section-update-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
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
