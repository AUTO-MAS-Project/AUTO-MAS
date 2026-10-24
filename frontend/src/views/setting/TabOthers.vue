<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { HomeOutlined, GithubOutlined, QqOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { ref } from 'vue'
import type { GlobalConfig, VersionOut } from '@/api'
import ChangelogView from '@/components/ChangelogView.vue'
import UpdateSettingsSection from '@/views/setting/UpdateSettingsSection.vue'
import type { ChangelogData } from '@/utils/changelog'
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
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
  checkUpdate: () => Promise<void>
}>()

// 当前版本的更新日志在编译期从 res/version.json 注入（res/ 不进 Electron 产物）
const changelogVisible = ref(false)
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
    <!-- 更新配置：独立子组件，避免本组件随业务扩展超限 -->
    <UpdateSettingsSection
      :settings="settings"
      :update-source-options="updateSourceOptions"
      :update-channel-options="updateChannelOptions"
      :handle-setting-change="handleSettingChange"
      :check-update="checkUpdate"
    />

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
