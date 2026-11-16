<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ref } from 'vue'
import type { GlobalConfig, VersionOut } from '@/api'
import type { SettingChangeHandler } from './settingTypes'
import ChangelogView from '@/components/ChangelogView.vue'
import UpdateSettingsSection from '@/views/setting/UpdateSettingsSection.vue'
import SectionCard from '@/components/ui/SectionCard.vue'
import appIcon from '@/assets/AUTO-MAS.ico'
import type { ChangelogData } from '@/utils/changelog'
import { MAS_QQ_GROUP_URL, handleExternalLink } from '@/utils/openExternal'
import {
  CopyOutlined,
  ExportOutlined,
  FileTextOutlined,
  GithubOutlined,
  HomeOutlined,
  InfoCircleOutlined,
  LinkOutlined,
  QqOutlined,
} from '@ant-design/icons-vue'

const logger = window.electronAPI.getLogger('设置-其他')

const { t } = useI18n()
const emit = defineEmits<{ fluxdownInstalled: [] }>()

const { version, backendUpdateInfo, settings, handleSettingChange, checkUpdate } = defineProps<{
  version: string
  backendUpdateInfo: VersionOut | null
  settings: GlobalConfig
  handleSettingChange: SettingChangeHandler
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
    t('core.setting.others.copyVersion', { version }),
    t('core.setting.others.copyBackendHash', {
      hash: backendUpdateInfo?.current_hash || t('core.common.unknown'),
    }),
  ].join('\n')

// 复制所有版本信息到剪贴板
const copyAllInfo = async () => {
  try {
    const copyText = buildCopyText()

    await navigator.clipboard.writeText(copyText)
    message.success(t('core.setting.toast.versionCopied'))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`复制失败: ${errorMsg}`)
    // 降级方案：创建临时input元素
    const textArea = document.createElement('textarea')
    textArea.value = buildCopyText()
    document.body.appendChild(textArea)
    textArea.select()
    try {
      if (!document.execCommand('copy')) throw new Error('复制未完成')
      message.success(t('core.setting.toast.versionCopied'))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`降级复制也失败: ${errorMsg}`)
      message.error(t('core.setting.toast.copyFailed'))
    }
    document.body.removeChild(textArea)
  }
}
</script>
<template>
  <div class="tab-content about-settings">
    <section class="version-card" :aria-label="t('core.setting.others.appVersion')">
      <img :src="appIcon" class="app-icon" alt="" />
      <div class="version-details">
        <h2>AUTO-MAS</h2>
        <div class="version-meta">
          <span class="version-number">{{ version }}</span>
          <a-tag v-if="version.includes('-beta.')">{{ t('core.setting.channel.beta') }}</a-tag>
          <span class="backend-hash">
            {{ t('core.setting.others.backendHash') }}
            <code>{{
              backendUpdateInfo?.current_hash?.substring(0, 8) || t('core.common.unknown')
            }}</code>
          </span>
        </div>
      </div>
      <div class="version-actions">
        <a-button @click="changelogVisible = true">
          <template #icon><FileTextOutlined aria-hidden="true" /></template>
          {{ t('core.setting.others.viewChangelog') }}
        </a-button>
        <a-button @click="copyAllInfo">
          <template #icon><CopyOutlined aria-hidden="true" /></template>
          {{ t('core.setting.others.copyInfo') }}
        </a-button>
      </div>
    </section>

    <div class="about-grid">
      <div class="about-main">
        <UpdateSettingsSection
          :settings="settings"
          :handle-setting-change="handleSettingChange"
          :check-update="checkUpdate"
          @fluxdown-installed="emit('fluxdownInstalled')"
        />
      </div>
      <aside class="about-sidebar">
        <SectionCard :title="t('core.setting.others.linkSection')" :icon="LinkOutlined">
          <div class="link-cards">
            <a class="link-card" href="https://auto-mas.top" @click="handleExternalLink">
              <span class="link-card__head">
                <HomeOutlined class="link-card__icon" />
                <span class="link-card__title">{{ t('core.setting.others.site') }}</span>
              </span>
              <span class="link-card__desc">{{ t('core.setting.others.siteDesc') }}</span>
              <ExportOutlined class="link-card__external" aria-hidden="true" />
            </a>
            <a
              class="link-card"
              href="https://github.com/AUTO-MAS-Project/AUTO-MAS"
              @click="handleExternalLink"
            >
              <span class="link-card__head">
                <GithubOutlined class="link-card__icon" />
                <span class="link-card__title">{{ t('core.setting.others.repo') }}</span>
              </span>
              <span class="link-card__desc">{{ t('core.setting.others.repoDesc') }}</span>
              <ExportOutlined class="link-card__external" aria-hidden="true" />
            </a>
            <a class="link-card" :href="MAS_QQ_GROUP_URL" @click="handleExternalLink">
              <span class="link-card__head">
                <QqOutlined class="link-card__icon" />
                <span class="link-card__title">{{ t('core.setting.others.qq') }}</span>
              </span>
              <span class="link-card__desc">{{ t('core.setting.others.qqDesc') }}</span>
              <ExportOutlined class="link-card__external" aria-hidden="true" />
            </a>
          </div>
        </SectionCard>

        <SectionCard :title="t('core.setting.others.appSection')" :icon="InfoCircleOutlined">
          <dl class="info-grid">
            <div class="info-item">
              <dt>{{ t('core.setting.others.appName') }}</dt>
              <dd>AUTO-MAS</dd>
            </div>
            <div class="info-item">
              <dt>{{ t('core.setting.others.developer') }}</dt>
              <dd>AUTO-MAS Team</dd>
            </div>
            <div class="info-item">
              <dt>{{ t('core.setting.others.license') }}</dt>
              <dd>AGPL-3.0</dd>
            </div>
          </dl>
        </SectionCard>
      </aside>
    </div>
  </div>

  <a-modal
    v-model:open="changelogVisible"
    :title="t('core.setting.others.changelogTitle', { version })"
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
.version-card {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 20px;
  padding: 24px;
  margin-bottom: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius-lg);
  background: var(--app-appearance-surface-bg);
}

.app-icon {
  width: 60px;
  height: 60px;
  object-fit: contain;
}

.version-details {
  flex: 1;
  min-width: 200px;
}

.version-details h2 {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 20px;
  font-weight: 600;
}

.version-meta,
.version-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.version-meta {
  margin-top: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.version-number,
.backend-hash code {
  font-family: monospace;
}

.backend-hash {
  padding-left: 12px;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.about-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.95fr) minmax(260px, 1fr);
  gap: 16px;
  align-items: start;
}

.about-main,
.about-sidebar {
  min-width: 0;
}

.link-cards {
  display: flex;
  flex-direction: column;
}

.link-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px 12px;
  padding: 16px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  color: inherit;
  text-decoration: none;
}

.link-card:last-child {
  border-bottom: 0;
}

.link-card:hover .link-card__title {
  color: var(--ant-color-primary);
}

.link-card:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.link-card__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.link-card__icon {
  color: var(--ant-color-text-secondary);
  font-size: 16px;
}

.link-card__title {
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 500;
}

.link-card__desc {
  color: var(--ant-color-text-secondary);
  padding-left: 24px;
  font-size: 12px;
  line-height: 1.5;
}

.link-card__external {
  grid-column: 2;
  grid-row: 1 / 3;
  align-self: center;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.info-grid {
  margin: 0;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 40px;
  gap: 16px;
  padding: 8px 0;
  font-size: 12px;
}

.info-item dt {
  color: var(--ant-color-text-secondary);
}

.info-item dd {
  margin: 0;
  color: var(--ant-color-text);
  text-align: right;
  overflow-wrap: anywhere;
}

.changelog-modal-body {
  padding-right: 8px;
}

@media (max-width: 1080px) {
  .about-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .about-sidebar {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    align-items: start;
  }
}

@media (max-width: 800px) {
  .about-sidebar {
    grid-template-columns: minmax(0, 1fr);
  }

  .version-actions {
    width: 100%;
  }
}
</style>
