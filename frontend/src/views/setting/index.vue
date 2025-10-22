<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import type { ThemeColor, ThemeMode } from '@/composables/useTheme'
import { useTheme } from '@/composables/useTheme'
import type { SelectValue } from 'ant-design-vue/es/select'
import type { SettingsData } from '@/types/settings'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { useUpdateChecker } from '@/composables/useUpdateChecker.ts'
import { Service, type VersionOut } from '@/api'
import { mirrorManager } from '@/utils/mirrorManager'

// 引入拆分后的 Tab 组件
import TabBasic from './TabBasic.vue'
import TabFunction from './TabFunction.vue'
import TabNotify from './TabNotify.vue'
import TabAdvanced from './TabAdvanced.vue'
import TabOthers from './TabOthers.vue'

const router = useRouter()
const { themeMode, themeColor, themeColors, setThemeMode, setThemeColor } = useTheme()
const { loading, getSettings, updateSettings } = useSettingsApi()
const {
  restartPolling,
  updateVisible,
  updateData,
  latestVersion,
  checkUpdate: globalCheckUpdate,
} = useUpdateChecker()

// 活动标签
const activeKey = ref('basic')
const version = (import.meta as any).env?.VITE_APP_VERSION || '获取版本失败！'
const backendUpdateInfo = ref<VersionOut | null>(null)

// 镜像配置状态
type MirrorConfigStatus = {
  isUsingCloudConfig: boolean
  version?: string
  lastUpdated?: string
  source: 'cloud' | 'fallback'
}
const mirrorConfigStatus = ref<MirrorConfigStatus>({
  isUsingCloudConfig: false,
  version: undefined,
  lastUpdated: undefined,
  source: 'fallback',
})
const refreshingConfig = ref(false)

const settings = reactive<SettingsData>({
  UI: { IfShowTray: false, IfToTray: false },
  Function: {
    BossKey: '',
    HistoryRetentionTime: 0,
    IfAgreeBilibili: false,
    IfAllowSleep: false,
    IfSilence: false,
    IfSkipMumuSplashAds: false,
  },
  Notify: {
    SendTaskResultTime: '不推送',
    IfSendStatistic: false,
    IfSendSixStar: false,
    IfPushPlyer: false,
    IfSendMail: false,
    SMTPServerAddress: '',
    AuthorizationCode: '',
    FromAddress: '',
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
    ServerChanChannel: '',
    ServerChanTag: '',
    CustomWebhooks: [],
  },
  Voice: { Enabled: false, Type: 'simple' },
  Start: { IfSelfStart: false, IfMinimizeDirectly: false },
  Update: {
    IfAutoUpdate: false,
    Source: 'GitHub',
    ProxyAddress: '',
    MirrorChyanCDK: '',
  },
})

// 下拉选项
const historyRetentionOptions = [
  { label: '7天', value: 7 },
  { label: '15天', value: 15 },
  { label: '30天', value: 30 },
  { label: '60天', value: 60 },
  { label: '90天', value: 90 },
  { label: '180天', value: 180 },
  { label: '365天', value: 365 },
  { label: '永久保留', value: 0 },
]

const sendTaskResultTimeOptions = [
  { label: '不推送', value: '不推送' },
  { label: '任何时刻', value: '任何时刻' },
  { label: '仅失败时', value: '仅失败时' },
]

const updateSourceOptions = [
  { label: 'GitHub', value: 'GitHub' },
  { label: 'Mirror酱', value: 'MirrorChyan' },
  { label: '自建下载站', value: 'AutoSite' },
]

const voiceTypeOptions = [
  { label: '简洁', value: 'simple' },
  { label: '聒噪', value: 'noisy' },
]

const themeModeOptions = [
  { label: '跟随系统', value: 'system' },
  { label: '浅色模式', value: 'light' },
  { label: '深色模式', value: 'dark' },
]

const themeColorLabels: Record<ThemeColor, string> = {
  blue: '蓝色',
  purple: '紫色',
  cyan: '青色',
  green: '绿色',
  magenta: '洋红',
  pink: '粉色',
  red: '红色',
  orange: '橙色',
  yellow: '黄色',
  volcano: '火山红',
  geekblue: '极客蓝',
  lime: '青柠',
  gold: '金色',
}

const themeColorOptions = Object.entries(themeColors).map(([key, color]) => ({
  label: themeColorLabels[key as ThemeColor],
  value: key,
  color,
}))

// 加载和保存
const loadSettings = async () => {
  const data = await getSettings()
  if (data) {
    Object.assign(settings, data)

    // 同步配置到 Electron 主进程
    try {
      if ((window as any).electronAPI?.syncBackendConfig) {
        await (window as any).electronAPI.syncBackendConfig({
          UI: data.UI,
          Start: data.Start,
        })
        console.log('后端配置已同步到 Electron')
      }
    } catch (e) {
      console.error('同步配置到 Electron 失败', e)
    }
  }
}

const saveSettings = async (category: keyof SettingsData, changes: any) => {
  try {
    const updateData = { [category]: changes }
    const result = await updateSettings(updateData)
    if (!result) message.error('设置保存失败')
  } catch (e) {
    console.error(e)
    message.error('设置保存失败')
  }
}

const handleSettingChange = async (category: keyof SettingsData, key: string, value: any) => {
  const changes = { [key]: value }
  await saveSettings(category, changes)

  // 处理托盘相关配置
  if (category === 'UI' && (key === 'IfShowTray' || key === 'IfToTray')) {
    try {
      if ((window as any).electronAPI?.updateTraySettings) {
        await (window as any).electronAPI.updateTraySettings({ [key]: value })
      }
    } catch (e) {
      console.error('更新托盘失败', e)
      message.error('托盘设置更新失败')
    }
  }

  // 处理启动配置
  if (category === 'Start' && key === 'IfMinimizeDirectly') {
    try {
      if ((window as any).electronAPI?.syncBackendConfig) {
        await (window as any).electronAPI.syncBackendConfig({
          Start: { [key]: value },
        })
      }
    } catch (e) {
      console.error('同步启动配置失败', e)
      message.error('启动配置同步失败')
    }
  }

  if (category === 'Update' && key === 'IfAutoUpdate') {
    try {
      await restartPolling()
      message.success(value ? '已启用自动检查更新' : '已禁用自动检查更新')
    } catch (e) {
      console.error('重启更新检查失败', e)
      message.error('更新检查设置变更失败')
    }
  }
}

// 主题
const handleThemeModeChange = (e: any) => setThemeMode(e.target.value as ThemeMode)
const handleThemeColorChange = (value: SelectValue) => {
  if (typeof value === 'string') setThemeColor(value as ThemeColor)
}

// 其他操作
const goToLogs = () => router.push('/logs')
const openDevTools = () => (window as any).electronAPI?.openDevTools?.()

// 更新检查 - 使用全局更新检查器
const checkUpdate = async () => {
  console.log('[Setting] 使用全局更新检查器进行手动检查')
  console.log('[Setting] 检查前状态:', {
    updateVisible: updateVisible.value,
    updateData: updateData.value,
    latestVersion: latestVersion.value,
  })

  try {
    await globalCheckUpdate(false, true) // silent=false, forceCheck=true
    console.log('[Setting] 全局更新检查完成，状态:', {
      updateVisible: updateVisible.value,
      updateData: updateData.value,
      latestVersion: latestVersion.value,
    })
  } catch (error) {
    console.error('[Setting] 全局更新检查失败:', error)
  }
}

// onUpdateConfirmed 不再需要，由全局UpdateModal管理

// 后端版本
const getBackendVersion = async () => {
  try {
    backendUpdateInfo.value = await Service.getGitVersionApiInfoVersionPost()
  } catch (e) {
    console.error('获取后端版本失败', e)
  }
}

// 镜像配置
const updateMirrorConfigStatus = () => {
  mirrorConfigStatus.value = mirrorManager.getConfigStatus()
}
const refreshMirrorConfig = async () => {
  refreshingConfig.value = true
  try {
    const result = await mirrorManager.refreshCloudConfig()
    if (result.success) {
      message.success('镜像配置刷新成功')
      updateMirrorConfigStatus()
    } else message.warning(result.error || '刷新失败，继续使用当前配置')
  } catch (e) {
    console.error('刷新镜像配置失败', e)
    message.error('刷新镜像配置失败')
  } finally {
    refreshingConfig.value = false
  }
}
const goToMirrorTest = () => router.push('/mirror-test')

// 通知测试
const testingNotify = ref(false)
const testNotify = async () => {
  testingNotify.value = true
  try {
    const res = await Service.testNotifyApiSettingTestNotifyPost()
    if (res?.code && res.code !== 200) message.warning(res?.message || '测试通知发送结果未知')
    else message.success('测试通知已发送')
  } catch (e) {
    console.error('测试通知发送失败', e)
    message.error('测试通知发送失败')
  } finally {
    testingNotify.value = false
  }
}

onMounted(() => {
  loadSettings()
  getBackendVersion()
  updateMirrorConfigStatus()
})
</script>

<template>
  <div class="settings-container">
    <div class="settings-header"><h1 class="page-title">设置</h1></div>
    <div class="settings-content">
      <a-tabs v-model:active-key="activeKey" type="card" :loading="loading" class="settings-tabs">
        <a-tab-pane key="basic" tab="界面设置">
          <TabBasic
            :settings="settings"
            :theme-mode="themeMode"
            :theme-color="themeColor"
            :theme-mode-options="themeModeOptions"
            :theme-color-options="themeColorOptions"
            :handle-theme-mode-change="handleThemeModeChange"
            :handle-theme-color-change="handleThemeColorChange"
            :handle-setting-change="handleSettingChange"
          />
        </a-tab-pane>
        <a-tab-pane key="function" tab="功能设置">
          <TabFunction
            :settings="settings"
            :history-retention-options="historyRetentionOptions"
            :update-source-options="updateSourceOptions"
            :voice-type-options="voiceTypeOptions"
            :handle-setting-change="handleSettingChange"
            :check-update="checkUpdate"
          />
        </a-tab-pane>
        <a-tab-pane key="notify" tab="通知设置">
          <TabNotify
            :settings="settings"
            :send-task-result-time-options="sendTaskResultTimeOptions"
            :handle-setting-change="handleSettingChange"
            :test-notify="testNotify"
            :testing-notify="testingNotify"
          />
        </a-tab-pane>
        <a-tab-pane key="advanced" tab="高级设置">
          <TabAdvanced
            :go-to-logs="goToLogs"
            :open-dev-tools="openDevTools"
            :mirror-config-status="mirrorConfigStatus"
            :refreshing-config="refreshingConfig"
            :refresh-mirror-config="refreshMirrorConfig"
            :go-to-mirror-test="goToMirrorTest"
          />
        </a-tab-pane>
        <a-tab-pane key="others" tab="其他设置">
          <TabOthers :version="version" :backend-update-info="backendUpdateInfo" />
        </a-tab-pane>
      </a-tabs>
    </div>
    <!-- 不再在设置页面直接显示UpdateModal，使用全局的UpdateModal -->
    <!-- UpdateModal现在由App.vue统一管理 -->
  </div>
</template>

<style scoped>
/* 统一样式，使用 :deep 作用到子组件内部 */
.settings-container {
  /* Allow the settings page to expand with the window width */
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 20px;
  box-sizing: border-box;
}

.settings-header {
  margin-bottom: 24px;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.settings-content {
  background: var(--ant-color-bg-container);
  border-radius: 12px;
  width: 100%;
}

.settings-tabs {
  margin: 0;
}

.settings-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab) {
  background: transparent;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px 8px 0 0;
  margin-right: 8px;
}

.settings-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab-active) {
  background: var(--ant-color-bg-container);
  border-bottom-color: var(--ant-color-bg-container);
}

:deep(.tab-content) {
  padding: 24px;
  width: 100%;
}

:deep(.form-section) {
  margin-bottom: 32px;
}

:deep(.form-section:last-child) {
  margin-bottom: 0;
}

:deep(.section-header) {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

:deep(.section-header h3) {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

:deep(.section-header h3::before) {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

:deep(.section-description) {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

:deep(.section-doc-link) {
  color: var(--ant-color-primary) !important;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--ant-color-primary);
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 4px;
}

:deep(.section-doc-link:hover) {
  color: var(--ant-color-primary-hover) !important;
  background-color: var(--ant-color-primary-bg);
  border-color: var(--ant-color-primary-hover);
  text-decoration: none;
}

:deep(.section-update-button) {
  height: 32px;
  padding: 0 12px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 6px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 6px;
}

:deep(.section-update-button:hover) {
  transform: translateY(-1px);
}

:deep(.section-update-button:active) {
  transform: translateY(0);
}

:deep(.section-update-button svg) {
  transition: transform 0.3s ease;
}

:deep(.section-update-button:hover svg) {
  transform: rotate(180deg);
}

:deep(.form-item-vertical) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

:deep(.form-label-wrapper) {
  display: flex;
  align-items: center;
  gap: 8px;
}

:deep(.form-label) {
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

:deep(.help-icon) {
  color: #8c8c8c;
  font-size: 14px;
}

:deep(.tooltip-link) {
  color: var(--ant-color-primary) !important;
  text-decoration: underline;
  transition: color 0.2s ease;
}

:deep(.tooltip-link:hover) {
  color: var(--ant-color-primary-hover) !important;
  text-decoration: underline;
}

:deep(.link-card) {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  transition: all 0.3s ease;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

:deep(.link-card:hover) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

:deep(.link-icon) {
  font-size: 48px;
  margin-bottom: 16px;
  line-height: 1;
  color: var(--ant-color-primary);
  display: flex;
  justify-content: center;
  align-items: center;
}

:deep(.link-content) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

:deep(.link-content h4) {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

:deep(.link-content p) {
  margin: 0 0 16px;
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  line-height: 1.5;
  flex: 1;
}

:deep(.link-button) {
  display: inline-block;
  padding: 8px 16px;
  background: var(--ant-color-primary);
  color: #fff !important;
  text-decoration: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.2s ease;
  margin-top: auto;
}

:deep(.link-button:hover) {
  background: var(--ant-color-primary-hover);
  color: #fff !important;
  text-decoration: none;
}

/* link-grid styles moved into TabOthers.vue (scoped) */
:deep(.info-item) {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  line-height: 1.5;
}

:deep(.info-label) {
  font-weight: 600;
  color: var(--ant-color-text);
  min-width: 100px;
  flex-shrink: 0;
}

:deep(.info-value) {
  color: var(--ant-color-text-secondary);
  margin-left: 8px;
}
</style>
