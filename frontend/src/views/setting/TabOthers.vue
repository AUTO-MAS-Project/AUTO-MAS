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

const logger = window.electronAPI.getLogger('设置-其他')

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
    <div class="form-section">
      <div class="section-header">
        <h3>更新配置</h3>
        <a-button type="primary" size="small" class="section-update-button" @click="checkUpdate">
          <template #icon>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path
                d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z" />
            </svg>
          </template>
          检查更新
        </a-button>
      </div>
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启动时尝试更新后端</span>
              <a-tooltip title="启动时尝试更新后端组件">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Update?.IfAutoUpdate" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Update', 'IfAutoUpdate', checked)">
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">更新源</span>
              <a-tooltip title="选择下载软件更新的来源">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Update?.Source" :options="updateSourceOptions" size="large" style="width: 100%"
              @change="(value: any) => handleSettingChange('Update', 'Source', value)" />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">更新渠道</span>
              <a-tooltip title="稳定版：BUG 较少，无法第一时间体验新功能；公测版：包含最新功能，但可能存在较多 BUG">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Update?.Channel" :options="updateChannelOptions" size="large" style="width: 100%"
              @change="(value: any) => handleSettingChange('Update', 'Channel', value)" />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">网络代理地址</span>
              <a-tooltip title="使用网络代理软件时，若出现网络连接问题，请尝试设置代理地址，此设置全局生效">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input :value="settings.Update?.ProxyAddress" placeholder="请输入网络代理地址" size="large"
              @blur="(e: any) => handleSettingChange('Update', 'ProxyAddress', e.target.value)" />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">Mirror酱 CDK</span>
              <a-tooltip>
                <template #title>
                  <div>
                    Mirror酱CDK是使用Mirror源进行高速下载的凭证，可前往
                    <a href="https://mirrorchyan.com/zh/get-start?source=auto-mas-setting" class="tooltip-link"
                      @click="handleExternalLink">Mirror酱官网</a>
                    获取
                  </div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input-password :value="settings.Update?.MirrorChyanCDK"
              :disabled="settings.Update?.Source !== 'MirrorChyan'" placeholder="使用Mirror源时请输入Mirror酱CDK"
              :visibility-toggle="true" size="large"
              @blur="(e: any) => handleSettingChange('Update', 'MirrorChyanCDK', e.target.value)" />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>项目链接</h3>
      </div>
      <div class="link-grid">
        <div class="link-item">
          <div class="link-card">
            <div class="link-icon">
              <HomeOutlined />
            </div>
            <div class="link-content">
              <h4>软件官网</h4>
              <p>查看最新版本和功能介绍</p>
              <a href="https://auto-mas.top" class="link-button" @click="handleExternalLink">访问官网</a>
            </div>
          </div>
        </div>
        <div class="link-item">
          <div class="link-card">
            <div class="link-icon">
              <GithubOutlined />
            </div>
            <div class="link-content">
              <h4>GitHub仓库</h4>
              <p>查看源代码、提交issue和捐赠</p>
              <a href="https://github.com/AUTO-MAS-Project/AUTO-MAS" class="link-button"
                @click="handleExternalLink">访问仓库</a>
            </div>
          </div>
        </div>
        <div class="link-item">
          <div class="link-card">
            <div class="link-icon">
              <QqOutlined />
            </div>
            <div class="link-content">
              <h4>用户QQ群</h4>
              <p>加入社区，获取帮助和交流</p>
              <a href="https://qm.qq.com/q/bd9fISNoME" class="link-button" @click="handleExternalLink">加入群聊</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>应用信息</h3>
      </div>
      <div class="app-info-container">
        <div class="app-info-left">
          <div class="info-item">
            <span class="info-label">软件名：</span>
            <span class="info-value">AUTO-MAS</span>
          </div>
          <div class="info-item">
            <span class="info-label">开发者：</span>
            <span class="info-value">AUTO-MAS Team</span>
          </div>
          <div class="info-item">
            <span class="info-label">许可证：</span>
            <span class="info-value">AGPL-3.0 license</span>
          </div>
        </div>
        <div class="app-info-right">
          <div class="info-item">
            <span class="info-label">软件版本：</span>
            <a-tag color="blue" class="info-badge" @click="copyAllInfo">
              {{ version }}
            </a-tag>
          </div>
          <div class="info-item">
            <span class="info-label">后端日期：</span>
            <a-tag color="orange" class="info-badge" @click="copyAllInfo">
              {{ backendUpdateInfo?.current_time || '未知' }}
            </a-tag>
          </div>
          <div class="info-item">
            <span class="info-label">后端哈希：</span>
            <a-tag color="purple" class="info-badge" @click="copyAllInfo">
              {{
                backendUpdateInfo?.current_hash
                  ? backendUpdateInfo.current_hash.substring(0, 8)
                  : '未知'
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
