<script setup lang="ts">
import { HomeOutlined, GithubOutlined, QqOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { VersionOut } from '@/api'
import { handleExternalLink } from '@/utils/openExternal'

const logger = window.electronAPI.getLogger('设置-其他')

const { version, backendUpdateInfo } = defineProps<{
  version: string
  backendUpdateInfo: VersionOut | null
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
  } catch (err) {
    logger.error('复制失败:', err)
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
    } catch (fallbackErr) {
      logger.error('降级复制也失败:', fallbackErr)
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
            <span class="info-value">GPL-3.0 license</span>
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
