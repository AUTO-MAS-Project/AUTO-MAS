<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { onBeforeRouteLeave } from 'vue-router'
import type { ThemeColor, ThemeMode } from '@/composables/useTheme'
import { useTheme } from '@/composables/useTheme'
import { useLowPerfMode } from '@/composables/useLowPerfMode'
import type { SelectValue } from 'ant-design-vue/es/select'
import type { GlobalConfig } from '@/api'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { useUiPreferences } from '@/composables/useUiPreferences'
import { useUpdateChecker } from '@/composables/useUpdateChecker.ts'
import { useSettingsFormGuard, type SettingsCategory } from '@/composables/useSettingsFormGuard'
import { Service, type VersionOut } from '@/api'
import StatePanel from '@/components/mac/StatePanel.vue'
const logger = window.electronAPI.getLogger('设置')

// 引入拆分后的 Tab 组件
import TabBasic from './TabBasic.vue'
import TabFunction from './TabFunction.vue'
import TabNotify from './TabNotify.vue'
import TabAdvanced from './TabAdvanced.vue'
import TabOthers from './TabOthers.vue'

const { themeMode, themeColor, themeColors, setThemeMode, setThemeColor } = useTheme()
const { perfMode, detectedPerfMode, detectionContext, setPerfMode } = useLowPerfMode()
const { loading: settingsLoading, getSettings, updateSettings } = useSettingsApi()
const { syncUiPreferences } = useUiPreferences()
const {
  restartPolling,
  updateVisible,
  updateData,
  latestVersion,
  checkUpdate: globalCheckUpdate,
} = useUpdateChecker()

// Lane 8：设置页表单保护
const formGuard = useSettingsFormGuard()
const {
  getEffectiveValue,
  stageAndSave: guardStageAndSave,
  retryPending: guardRetryPending,
  retryPendingForCategories: guardRetryPendingForCategories,
  revertField: guardRevertField,
  getDefaultsForCategory,
  isSaving: guardIsSaving,
  getError: guardGetError,
  clearError: guardClearError,
  getAggregateStateForCategories: guardGetAggregateState,
  clearErrorsForCategories: guardClearErrorsForCategories,
  pendingCount: guardPendingCount,
  hasPending: guardHasPending,
} = formGuard

type SettingTabKey = 'basic' | 'function' | 'notify' | 'advanced' | 'others'

// macOS 风格彩色图标侧边栏配置：iOS settings 风格的圆角彩色图标
interface SettingNavMeta {
  key: SettingTabKey
  label: string
  iconKind: 'appearance' | 'features' | 'notifications' | 'logs' | 'about'
  description: string
}

const settingNavItems: SettingNavMeta[] = [
  {
    key: 'basic',
    label: '界面',
    iconKind: 'appearance',
    description: '主题外观、性能模式、托盘与窗口',
  },
  {
    key: 'function',
    label: '功能',
    iconKind: 'features',
    description: '启动行为、运行时功能与语音提示',
  },
  {
    key: 'notify',
    label: '通知',
    iconKind: 'notifications',
    description: '系统通知、邮件、Server酱、Koishi 与 Webhook',
  },
  {
    key: 'advanced',
    label: '日志',
    iconKind: 'logs',
    description: '导出日志压缩包与开发者工具',
  },
  {
    key: 'others',
    label: '关于',
    iconKind: 'about',
    description: '更新配置、项目链接与应用版本',
  },
]

// 活动标签
const activeKey = ref<SettingTabKey>('basic')
const activeMeta = computed(
  () => settingNavItems.find(item => item.key === activeKey.value) ?? settingNavItems[0]
)

const handleSettingTabChange = (key: SettingTabKey) => {
  activeKey.value = key
}

const uiGuardState = computed(() => guardGetAggregateState(['UI']))
const notifyGuardState = computed(() => guardGetAggregateState(['Notify']))
const updateGuardState = computed(() => guardGetAggregateState(['Update']))
const version = import.meta.env.VITE_APP_VERSION || '获取版本失败！'
const backendUpdateInfo = ref<VersionOut | null>(null)

// 设置数据 - 从API获取，不再使用硬编码初值
const settings = reactive<GlobalConfig>({})

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
  { label: 'CNB 镜像源', value: 'CNB' },
]

const updateChannelOptions = [
  { label: '稳定版', value: 'stable' },
  { label: '公测版', value: 'beta' },
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
    syncUiPreferences(data.UI)

    // 同步配置到 Electron 主进程
    try {
      if (window.electronAPI?.syncBackendConfig) {
        await window.electronAPI.syncBackendConfig({
          UI: data.UI,
          Start: data.Start,
          Update: data.Update,
        })
        logger.info('后端配置已同步到 Electron')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`同步配置到 Electron 失败: ${errorMsg}`)
      message.warning('部分配置未能同步到客户端，可能需要重启')
    }
  }
}

// 保存设置 - 只发送修改的字段（遵循最小原则）
const saveSettings = async (category: keyof GlobalConfig, changes: any): Promise<boolean> => {
  try {
    const updateData: GlobalConfig = { [category]: changes }
    const result = await updateSettings(updateData)
    if (!result) {
      message.error('设置保存失败')
      return false
    }
    return true
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`设置保存失败: ${errorMsg}`)
    message.error('设置保存失败')
    return false
  }
}

// 刷新设置数据
const refreshSettings = async () => {
  const data = await getSettings()
  if (data) {
    Object.assign(settings, data)
    syncUiPreferences(data.UI)

    // 同步所有配置到 Electron
    try {
      if (window.electronAPI?.syncBackendConfig) {
        await window.electronAPI.syncBackendConfig({
          UI: data.UI,
          Start: data.Start,
          Update: data.Update,
        })
        logger.info('所有配置已同步到 Electron')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`同步配置到 Electron 失败: ${errorMsg}`)
      message.warning('部分配置未能同步到客户端，可能需要重启')
    }
  }
}

const handleSettingChange = async (
  category: keyof GlobalConfig,
  key: string,
  value: any
): Promise<boolean> => {
  // Lane 8：通过 guard 暂存修改并尝试保存；失败时保留用户输入
  const ok = await guardStageAndSave(category as SettingsCategory, key, value, async () => {
    const changes = { [key]: value }
    return await saveSettings(category, changes)
  })

  if (!ok) {
    // 保存失败：guard 已保留 pendingChanges，错误已写入 errorByCategory
    // 不再 refreshSettings，避免用户输入被覆盖
    return false
  }

  // 更新成功后重新获取最新配置（会自动同步到 Electron）
  await refreshSettings()

  // 处理托盘相关配置（需要额外的实时更新调用）
  if (category === 'UI' && (key === 'IfShowTray' || key === 'IfToTray')) {
    try {
      if (window.electronAPI?.updateTraySettings) {
        await window.electronAPI.updateTraySettings({ [key]: value })
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`更新托盘失败: ${errorMsg}`)
      message.error('托盘设置更新失败')
    }
  }

  // 处理自动更新配置 - 重启更新检查轮询
  if (category === 'Update' && key === 'IfAutoUpdate') {
    try {
      await restartPolling()
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`重启更新检查失败: ${errorMsg}`)
      message.error('更新检查设置变更失败')
    }
  }

  return true
}

// Lane 8：重试某个 category 下所有 pendingChanges
const handleRetryPending = async (category: SettingsCategory) => {
  await guardRetryPending(category, async (key, value) => {
    const changes = { [key]: value }
    const ok = await saveSettings(category as keyof GlobalConfig, changes)
    if (ok) {
      await refreshSettings()
    }
    return ok
  })
  if (!guardGetError(category)) {
    message.success('已重试保存成功')
  }
}

// Lane 8：重试多个 category 下所有 pendingChanges（用于多 category Tab）
const handleRetryPendingForCategories = async (categories: SettingsCategory[]) => {
  await guardRetryPendingForCategories(categories, async (category, key, value) => {
    const changes = { [key]: value }
    const ok = await saveSettings(category as keyof GlobalConfig, changes)
    if (ok) {
      await refreshSettings()
    }
    return ok
  })
  const stillHasError = categories.some(c => guardGetError(c))
  if (!stillHasError) {
    message.success('已重试保存成功')
  }
}

// Lane 8：还原某个字段到 settings 原值
const handleRevertField = (category: SettingsCategory, key: string) => {
  guardRevertField(category, key)
}

// Lane 8：恢复某个 category 的已知默认值
const handleRestoreDefaults = async (category: SettingsCategory) => {
  const defaults = getDefaultsForCategory(category)
  if (!defaults) {
    message.info('该分类暂无已知的默认值配置')
    return
  }
  const entries = Object.entries(defaults)
  let successCount = 0
  for (const [key, value] of entries) {
    const ok = await handleSettingChange(category as keyof GlobalConfig, key, value)
    if (ok) successCount += 1
  }
  if (successCount === entries.length) {
    message.success(`已恢复 ${successCount} 项默认设置`)
  } else if (successCount > 0) {
    message.warning(`已恢复 ${successCount}/${entries.length} 项默认设置，部分字段保存失败`)
  } else {
    message.error('恢复默认设置失败，请重试')
  }
}

// Lane 8：恢复多个 category 的已知默认值（用于多 category Tab）
const handleRestoreDefaultsForCategories = async (categories: SettingsCategory[]) => {
  let totalAttempted = 0
  let totalRestored = 0
  for (const category of categories) {
    const defaults = getDefaultsForCategory(category)
    if (!defaults) continue
    const entries = Object.entries(defaults)
    for (const [key, value] of entries) {
      totalAttempted += 1
      const ok = await handleSettingChange(category as keyof GlobalConfig, key, value)
      if (ok) totalRestored += 1
    }
  }
  if (totalAttempted === 0) {
    message.info('这些分类暂无已知的默认值配置')
  } else if (totalRestored === totalAttempted) {
    message.success(`已恢复 ${totalRestored} 项默认设置`)
  } else if (totalRestored > 0) {
    message.warning(`已恢复 ${totalRestored}/${totalAttempted} 项默认设置，部分字段保存失败`)
  } else {
    message.error('恢复默认设置失败，请重试')
  }
}

// 主题
const handleThemeModeChange = (value: SelectValue) => {
  if (typeof value === 'string') setThemeMode(value as ThemeMode)
}
const handleThemeColorChange = (value: SelectValue) => {
  if (typeof value === 'string') setThemeColor(value as ThemeColor)
}

// 性能模式：'auto' 代表恢复自动检测（setPerfMode(null)），'low'/'normal' 为用户显式覆盖
const handlePerfModeChange = (value: SelectValue) => {
  if (value === 'auto') {
    setPerfMode(null)
  } else if (value === 'low' || value === 'normal') {
    setPerfMode(value)
  }
}

// perfMode 选择器绑定值：用户未显式设置时显示 'auto'
const perfModeSelectValue = computed(() => {
  const stored = localStorage.getItem('perf-mode')
  return stored ? perfMode.value : 'auto'
})

// 其他操作
const openDevTools = () => window.electronAPI?.openDevTools?.()

// 更新检查 - 使用全局更新检查器
const checkUpdate = async () => {
  logger.info('使用全局更新检查器进行手动检查')
  logger.info(`检查前状态:{
    updateVisible: ${updateVisible.value},
    updateData: ${updateData.value},
    latestVersion: ${latestVersion.value},
  }`)

  try {
    await globalCheckUpdate(false, true) // silent=false, forceCheck=true
    logger.info(
      `全局更新检查完成，状态: ${JSON.stringify({
        updateVisible: updateVisible.value,
        updateData: updateData.value,
        latestVersion: latestVersion.value,
      })}`
    )
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`全局更新检查失败: ${errorMsg}`)
  }
}

// onUpdateConfirmed 不再需要，由全局UpdateModal管理

// 后端版本
const getBackendVersion = async () => {
  if (import.meta.env.DEV) {
    logger.info('开发环境：跳过设置页后端版本查询')
    return
  }

  try {
    backendUpdateInfo.value = await Service.getGitVersionApiInfoVersionPost()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`获取后端版本失败: ${errorMsg}`)
  }
}

// 通知测试
const testingNotify = ref(false)
const testNotify = async () => {
  testingNotify.value = true
  try {
    const res = await Service.testNotifyApiSettingTestNotifyPost()
    if (res?.code && res.code !== 200) message.warning(res?.message || '测试通知发送结果未知')
    else message.success('测试通知已发送')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`测试通知发送失败: ${errorMsg}`)
    message.error('测试通知发送失败')
  } finally {
    testingNotify.value = false
  }
}

const handleBeforeUnload = (event: BeforeUnloadEvent) => {
  if (!guardHasPending.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(() => {
  if (!guardHasPending.value) return true

  return new Promise<boolean>(resolve => {
    Modal.confirm({
      title: '仍有未保存的设置',
      content: `有 ${guardPendingCount.value} 项设置保存失败并保留在当前页面。离开后这些输入将丢失。`,
      okText: '仍然离开',
      cancelText: '留在此页',
      okType: 'danger',
      centered: true,
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })
})

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  loadSettings()
  getBackendVersion()
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<template>
  <div class="settings-container">
    <div class="settings-body">
      <!-- ── macOS 风格彩色图标侧边栏 ── -->
      <aside class="settings-sidebar" aria-label="设置分类">
        <nav class="settings-nav" role="tablist">
          <button
            v-for="item in settingNavItems"
            :key="item.key"
            type="button"
            role="tab"
            class="settings-nav-item"
            :class="{ 'nav-selected': activeKey === item.key }"
            :aria-selected="activeKey === item.key"
            @click="handleSettingTabChange(item.key)"
          >
            <span class="nav-icon-wrap" :class="`nav-icon-${item.iconKind}`" aria-hidden="true">
              <svg
                v-if="item.iconKind === 'appearance'"
                class="nav-icon"
                viewBox="0 0 16 16"
                fill="none"
              >
                <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.4" />
                <path d="M8 2a6 6 0 0 0 0 12V2z" fill="currentColor" />
              </svg>
              <svg
                v-else-if="item.iconKind === 'features'"
                class="nav-icon"
                viewBox="0 0 16 16"
                fill="none"
              >
                <rect x="2" y="2" width="5" height="5" rx="1" fill="currentColor" />
                <rect x="9" y="2" width="5" height="5" rx="1" fill="currentColor" opacity="0.7" />
                <rect x="2" y="9" width="5" height="5" rx="1" fill="currentColor" opacity="0.7" />
                <rect x="9" y="9" width="5" height="5" rx="1" fill="currentColor" />
              </svg>
              <svg
                v-else-if="item.iconKind === 'notifications'"
                class="nav-icon"
                viewBox="0 0 16 16"
                fill="none"
              >
                <path
                  d="M8 1.5a4.5 4.5 0 0 0-4.5 4.5v2.5L2 11h12l-1.5-2.5V6A4.5 4.5 0 0 0 8 1.5z"
                  fill="currentColor"
                />
                <path
                  d="M6 13a2 2 0 0 0 4 0"
                  stroke="currentColor"
                  stroke-width="1.4"
                  stroke-linecap="round"
                  fill="none"
                />
              </svg>
              <svg
                v-else-if="item.iconKind === 'logs'"
                class="nav-icon"
                viewBox="0 0 16 16"
                fill="none"
              >
                <path
                  d="M3 2h7l3 3v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"
                  fill="currentColor"
                />
                <path
                  d="M5 7h6M5 9.5h6M5 12h3"
                  stroke="#fff"
                  stroke-width="1"
                  stroke-linecap="round"
                />
              </svg>
              <svg v-else class="nav-icon" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.4" />
                <path
                  d="M8 5.2v3.6M8 11.2v.1"
                  stroke="currentColor"
                  stroke-width="1.4"
                  stroke-linecap="round"
                />
              </svg>
            </span>
            <span class="nav-label">{{ item.label }}</span>
          </button>
        </nav>

        <div class="sidebar-footer">
          <span class="sidebar-hint">修改即时保存</span>
        </div>
      </aside>

      <!-- ── 右侧内容区 ── -->
      <main class="settings-content" data-scroll-region="primary">
        <div class="settings-content-inner">
          <!-- 面板标题（精简，不与 PageHeader 重复） -->
          <header class="settings-panel-header">
            <h1 class="settings-panel-title">{{ activeMeta.label }}</h1>
            <p class="settings-panel-subtitle">{{ activeMeta.description }}</p>
          </header>

          <StatePanel
            v-if="guardHasPending"
            type="warning"
            compact
            :title="`${guardPendingCount} 项设置尚未保存`"
          >
            保存失败的输入已保留在当前页面，可在对应分区重试或恢复。
          </StatePanel>

          <a-spin :spinning="settingsLoading" class="settings-loading">
            <div class="settings-tab-scroll">
              <div v-show="activeKey === 'basic'" class="settings-tab-panel" role="tabpanel">
                <TabBasic
                  :settings="settings"
                  :theme-mode="themeMode"
                  :theme-color="themeColor"
                  :theme-mode-options="themeModeOptions"
                  :theme-color-options="themeColorOptions"
                  :handle-theme-mode-change="handleThemeModeChange"
                  :handle-theme-color-change="handleThemeColorChange"
                  :handle-setting-change="handleSettingChange"
                  :perf-mode-select-value="perfModeSelectValue"
                  :detected-perf-mode="detectedPerfMode"
                  :detection-context="detectionContext"
                  :handle-perf-mode-change="handlePerfModeChange"
                  :get-effective-value="getEffectiveValue"
                  :get-error="guardGetError"
                  :clear-error="guardClearError"
                  :has-pending="uiGuardState.hasPendingForCategories"
                  :pending-count="uiGuardState.pendingCountForCategories"
                  :retry-pending="handleRetryPending"
                  :revert-field="handleRevertField"
                  :restore-defaults="handleRestoreDefaults"
                  :is-saving="guardIsSaving"
                />
              </div>
              <div v-show="activeKey === 'function'" class="settings-tab-panel" role="tabpanel">
                <TabFunction
                  :settings="settings"
                  :history-retention-options="historyRetentionOptions"
                  :voice-type-options="voiceTypeOptions"
                  :handle-setting-change="handleSettingChange"
                  :get-effective-value="getEffectiveValue"
                  :get-aggregate-state="guardGetAggregateState"
                  :clear-errors-for-categories="guardClearErrorsForCategories"
                  :retry-pending-for-categories="handleRetryPendingForCategories"
                  :revert-field="handleRevertField"
                  :restore-defaults-for-categories="handleRestoreDefaultsForCategories"
                  :is-saving="guardIsSaving"
                />
              </div>
              <div v-show="activeKey === 'notify'" class="settings-tab-panel" role="tabpanel">
                <TabNotify
                  :settings="settings"
                  :send-task-result-time-options="sendTaskResultTimeOptions"
                  :handle-setting-change="handleSettingChange"
                  :test-notify="testNotify"
                  :testing-notify="testingNotify"
                  :get-effective-value="getEffectiveValue"
                  :get-error="guardGetError"
                  :clear-error="guardClearError"
                  :has-pending="notifyGuardState.hasPendingForCategories"
                  :pending-count="notifyGuardState.pendingCountForCategories"
                  :retry-pending="handleRetryPending"
                  :revert-field="handleRevertField"
                  :restore-defaults="handleRestoreDefaults"
                  :is-saving="guardIsSaving"
                />
              </div>
              <div v-show="activeKey === 'advanced'" class="settings-tab-panel" role="tabpanel">
                <TabAdvanced :open-dev-tools="openDevTools" />
              </div>
              <div v-show="activeKey === 'others'" class="settings-tab-panel" role="tabpanel">
                <TabOthers
                  :version="version"
                  :backend-update-info="backendUpdateInfo"
                  :settings="settings"
                  :update-source-options="updateSourceOptions"
                  :update-channel-options="updateChannelOptions"
                  :handle-setting-change="handleSettingChange"
                  :check-update="checkUpdate"
                  :get-effective-value="getEffectiveValue"
                  :get-error="guardGetError"
                  :clear-error="guardClearError"
                  :has-pending="updateGuardState.hasPendingForCategories"
                  :pending-count="updateGuardState.pendingCountForCategories"
                  :retry-pending="handleRetryPending"
                  :revert-field="handleRevertField"
                  :restore-defaults="handleRestoreDefaults"
                  :is-saving="guardIsSaving"
                />
              </div>
            </div>
          </a-spin>
        </div>
      </main>
    </div>
    <!-- 不再在设置页面直接显示UpdateModal，使用全局的UpdateModal -->
    <!-- UpdateModal现在由App.vue统一管理 -->
  </div>
</template>

<style scoped>
.settings-container {
  /* settings-root 容器用于驱动 .settings-body 自身的窄屏降级
     (@container 只作用于容器后代,settings-body 自己的容器查不到自己) */
  container: settings-root / inline-size;
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  width: 100%;
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  overflow: hidden;
  background: var(--v6-color-window);
}

/* ── 主体：左侧边栏 + 右侧内容 ── */
.settings-body {
  container: settings-body / inline-size;
  flex: 1;
  min-height: 0;
  display: flex;
  width: 100%;
  overflow: hidden;
}

/* ── macOS Settings 风格彩色图标侧边栏 ── */
.settings-sidebar {
  width: 200px;
  min-width: 200px;
  flex-shrink: 0;
  background: var(--v6-vibrancy-sidebar);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  border-right: 0.5px solid var(--v6-color-border);
  display: flex;
  flex-direction: column;
  padding: var(--v6-space-3) var(--v6-space-2) var(--v6-space-2);
  overflow-y: auto;
}

.settings-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.settings-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 38px;
  padding: 0 var(--v6-space-2);
  border: none;
  background: transparent;
  border-radius: var(--v6-radius-control);
  font-size: var(--v6-font-size-base);
  color: var(--v6-color-text);
  cursor: pointer;
  transition:
    background-color var(--v6-motion-fast) var(--v6-ease-out),
    color var(--v6-motion-fast) var(--v6-ease-out);
  white-space: nowrap;
  text-align: left;
  font-family: inherit;
}

.settings-nav-item:hover {
  background: var(--v6-vibrancy-hover);
}

.settings-nav-item:focus-visible {
  outline: var(--v6-outline-width) solid var(--v6-color-info);
  outline-offset: -2px;
}

/* iOS-style colored rounded-square icon wraps */
.nav-icon-wrap {
  width: 26px;
  height: 26px;
  border-radius: var(--v6-radius-control);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #fff;
}

.nav-icon {
  width: 15px;
  height: 15px;
  color: #fff;
}

/* macOS Settings gradient color tokens - replicated from design HTML */
.nav-icon-appearance {
  background: linear-gradient(135deg, #5ac8fa, #32a7dc);
}

.nav-icon-features {
  background: linear-gradient(135deg, #0a84ff, #0060df);
}

.nav-icon-notifications {
  background: linear-gradient(135deg, #ff3b30, #cc2c23);
}

.nav-icon-logs {
  background: linear-gradient(135deg, #ff9500, #cc6f00);
}

.nav-icon-about {
  background: linear-gradient(135deg, #34c759, #248a3d);
}

.nav-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: var(--v6-font-weight-normal);
}

/* 选中状态：macOS vibrancy active 蓝色背景 */
.nav-selected {
  background: var(--v6-vibrancy-active) !important;
  color: #fff;
}

.nav-selected .nav-label {
  color: #fff;
  font-weight: var(--v6-font-weight-medium);
}

/* 选中状态下图标保持原色（macOS settings 实际行为：选中后图标变白底） */
.nav-selected .nav-icon-wrap {
  background: rgba(255, 255, 255, 0.92) !important;
}

.nav-selected .nav-icon-wrap .nav-icon {
  color: var(--v6-vibrancy-active);
}

.sidebar-footer {
  padding-top: var(--v6-space-2);
  margin-top: var(--v6-space-2);
  border-top: 0.5px solid var(--v6-color-border);
  display: flex;
  justify-content: flex-start;
  padding-left: var(--v6-space-1);
}

.sidebar-hint {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-xs);
  line-height: 1.5;
}

/* ── 右侧内容区 ── */
.settings-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  container: settings-content / inline-size;
  background: var(--v6-color-window);
}

.settings-content-inner {
  padding: var(--v6-space-6) var(--v6-space-8) var(--v6-space-8);
  width: 100%;
  max-width: 1600px;
  margin: 0 auto;
  box-sizing: border-box;
}

/* ── 面板标题（精简，避免与 PageHeader 重复） ── */
.settings-panel-header {
  margin-bottom: var(--v6-space-5);
}

.settings-panel-title {
  margin: 0;
  font-size: var(--v6-font-size-3xl);
  font-weight: var(--v6-font-weight-semibold);
  line-height: var(--v6-line-height-tight);
  color: var(--v6-color-text);
  letter-spacing: -0.01em;
}

.settings-panel-subtitle {
  margin: var(--v6-space-1) 0 0;
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text-secondary);
  line-height: var(--v6-line-height-normal);
}

.settings-loading {
  display: flex;
  min-height: 0;
}

.settings-loading :deep(.ant-spin-container) {
  width: 100%;
}

.settings-tab-scroll {
  min-height: 0;
}

.settings-tab-panel {
  width: 100%;
}

/* ── Tab 内部表单 NSBox 分组：复用 mac/Section token 语言 ──
   iPad 设置式自适应瀑布布局：multi-column 让卡片在各列内独立纵向堆叠，
   矮卡高度互不影响，消除旧 grid 行等高布局中矮卡下方的大片空白。
   三档响应：超宽容器（≥1400px）三列、常规双列、窄容器（≤980px）单列，
   档位由下方容器查询切换，仅改 columns 数。 */
:deep(.tab-content) {
  width: 100%;
  padding: 0;
  columns: 2;
  column-gap: var(--v6-space-4);
}

/* 全跨元素：Tab 状态条与含宽控件/信息列表的卡片横贯两列。
   column-span 仅对 block-level 盒生效，卡片须保持 display: block（勿改 inline-block）。 */
:deep(.tab-content > .settings-tab-header),
:deep(.tab-content > .setting-tab-header),
:deep(.tab-content > .state-panel),
:deep(.form-section:has(.row-control-full)),
:deep(.form-section:has(.link-grid)),
:deep(.form-section:has(.webhook-manager)),
:deep(.form-section:has(.log-highlight-settings)),
:deep(.form-section:has(.info-value)) {
  column-span: all;
}

/* 状态条与首排卡片的间距：补偿原 grid gap（组件自身 margin 仅 space-3） */
:deep(.tab-content > .setting-tab-header) {
  margin-bottom: var(--v6-space-4);
}

/* NSBox 分组容器：12px 圆角、0.5px 边框、毛玻璃
   break-inside: avoid 保证卡片作为整体落入某一列，不跨列断裂；
   列内卡片纵向间距由 margin-bottom 承担（multi-column 中 gap 不作用于列内） */
:deep(.form-section) {
  min-width: 0;
  break-inside: avoid;
  margin-bottom: var(--v6-space-4);
  padding: 0;
  border: 0.5px solid var(--v6-color-border);
  border-radius: var(--v6-radius-card);
  background: var(--v6-color-surface-transparent);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  box-shadow: var(--v6-shadow-card);
  overflow: hidden;
}

:deep(.form-section:last-child) {
  margin-bottom: 0;
}

/* 组标题：13px semibold，灰阶次色 */
:deep(.section-header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-3);
  padding: var(--v6-space-3) var(--v6-space-4);
  margin: 0;
  border: 0;
  border-bottom: 0.5px solid var(--v6-color-border-subtle);
  background: transparent;
}

:deep(.section-header h3) {
  margin: 0;
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-base);
  font-weight: var(--v6-font-weight-semibold);
  line-height: var(--v6-line-height-snug);
}

:deep(.section-description) {
  margin: 0;
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
}

:deep(.section-doc-link) {
  color: var(--v6-color-info) !important;
  text-decoration: none;
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-medium);
  padding: var(--v6-space-1) var(--v6-space-2);
  border-radius: var(--v6-radius-sm);
  border: 1px solid var(--v6-color-info-border);
  transition: all var(--v6-motion-fast) var(--v6-ease-out);
  display: inline-flex;
  align-items: center;
  gap: var(--v6-space-1);
}

:deep(.section-doc-link:hover) {
  color: var(--v6-color-info) !important;
  background-color: var(--v6-color-info-bg);
  border-color: var(--v6-color-info);
  text-decoration: none;
}

:deep(.section-update-button) {
  height: 28px;
  padding: 0 var(--v6-space-3);
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-medium);
  border-radius: var(--v6-radius-control);
  transition:
    transform var(--v6-motion-fast) var(--v6-ease-out),
    box-shadow var(--v6-motion-fast) var(--v6-ease-out);
  display: inline-flex;
  align-items: center;
  gap: var(--v6-space-1);
}

:deep(.section-update-button:hover) {
  transform: translateY(-1px);
}

:deep(.section-update-button:active) {
  transform: translateY(0);
}

:deep(.section-update-button svg) {
  transition: transform var(--v6-motion-base) var(--v6-ease-out);
}

:deep(.section-update-button:hover svg) {
  transform: rotate(180deg);
}

/* macOS 设置行：label 左对齐，控件右对齐 */
:deep(.setting-row) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 36px;
  padding: var(--v6-space-2) var(--v6-space-4);
  gap: var(--v6-space-4);
}

:deep(.setting-row-multiline) {
  align-items: flex-start;
  padding-top: var(--v6-space-3);
  padding-bottom: var(--v6-space-3);
}

:deep(.setting-row-multiline:has(.row-control-full)) {
  flex-direction: column;
}

:deep(.row-label) {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

:deep(.row-title) {
  font-size: var(--v6-font-size-base);
  color: var(--v6-color-text);
  line-height: var(--v6-line-height-snug);
}

:deep(.row-help) {
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-tertiary);
  line-height: 1.4;
}

:deep(.row-warning) {
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-warning);
  line-height: 1.4;
}

:deep(.row-control) {
  min-width: 0;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
}

:deep(.row-control-full) {
  width: 100%;
  min-width: 0;
  flex: 0 0 auto;
}

:deep(.row-control-full > .log-highlight-settings) {
  width: 100%;
  min-width: 0;
}

:deep(.row-separator) {
  height: 0.5px;
  background: var(--v6-color-border-subtle);
  margin: 0 var(--v6-space-4);
}

/* 兼容旧 form-item-vertical 命名（在重构中过渡） */
:deep(.form-item-vertical) {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-2);
  margin-bottom: var(--v6-space-3);
}

:deep(.form-label-wrapper) {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
}

:deep(.form-label) {
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-base);
}

:deep(.help-icon) {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-base);
}

:deep(.tooltip-link) {
  color: var(--v6-color-info) !important;
  text-decoration: underline;
  transition: color var(--v6-motion-fast) var(--v6-ease-out);
}

:deep(.tooltip-link:hover) {
  color: var(--v6-color-text-link-hover) !important;
  text-decoration: underline;
}

:deep(.link-card) {
  background: var(--v6-color-surface);
  border: 1px solid var(--v6-color-border);
  border-radius: var(--v6-radius-card);
  padding: var(--v6-space-5);
  text-align: center;
  transition: all var(--v6-motion-base) var(--v6-ease-out);
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

:deep(.link-card:hover) {
  border-color: var(--v6-color-info);
  box-shadow: var(--v6-shadow-md);
  transform: translateY(-2px);
}

:deep(.link-icon) {
  font-size: 48px;
  margin-bottom: var(--v6-space-4);
  line-height: 1;
  color: var(--v6-color-info);
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
  margin: 0 0 var(--v6-space-2);
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
}

:deep(.link-content p) {
  margin: 0 0 var(--v6-space-4);
  font-size: var(--v6-font-size-base);
  color: var(--v6-color-text-secondary);
  line-height: 1.5;
  flex: 1;
}

:deep(.link-button) {
  display: inline-block;
  padding: var(--v6-space-2) var(--v6-space-4);
  background: var(--v6-color-info);
  color: #fff !important;
  text-decoration: none;
  border-radius: var(--v6-radius-sm);
  font-size: var(--v6-font-size-base);
  font-weight: var(--v6-font-weight-medium);
  transition: background-color var(--v6-motion-fast) var(--v6-ease-out);
  margin-top: auto;
}

:deep(.link-button:hover) {
  background: var(--v6-color-info-hover, var(--v6-color-primary-hover));
  color: #fff !important;
  text-decoration: none;
}

:deep(.info-item) {
  display: flex;
  align-items: center;
  margin-bottom: var(--v6-space-2);
  line-height: 1.5;
}

:deep(.info-label) {
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
  min-width: 100px;
  flex-shrink: 0;
}

:deep(.info-value) {
  color: var(--v6-color-text-secondary);
  margin-left: var(--v6-space-2);
}

/* ── 低性能模式：禁用毛玻璃与阴影 ── */
:root[data-perf-mode='low'] .form-section {
  background: var(--v6-color-surface);
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

:root[data-perf-mode='low'] .settings-sidebar {
  background: var(--v6-color-sidebar);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

/* 内容区会受设置侧栏挤压，必须按真实可用宽度而非仅按窗口宽度切档。 */
@container settings-content (min-width: 1400px) {
  :deep(.tab-content) {
    columns: 3;
  }
}

@container settings-content (max-width: 980px) {
  :deep(.tab-content) {
    columns: 1;
  }
}

/* ── 响应式 ── */
@container settings-body (max-width: 820px) {
  .settings-sidebar {
    width: 168px;
    min-width: 168px;
  }

  .settings-content-inner {
    padding: var(--v6-space-5) var(--v6-space-4) var(--v6-space-6);
  }

  .settings-panel-title {
    font-size: var(--v6-font-size-2xl);
  }

  :deep(.tab-content) {
    columns: 1;
  }
}

/* .settings-body 自身的窄屏降级由外层 settings-root 容器驱动 */
@container settings-root (max-width: 640px) {
  .settings-body {
    flex-direction: column;
  }
}

@container settings-body (max-width: 640px) {
  .settings-sidebar {
    width: 100%;
    min-width: 0;
    flex-direction: row;
    padding: var(--v6-space-2);
    overflow-x: auto;
    overflow-y: hidden;
    border-right: none;
    border-bottom: 0.5px solid var(--v6-color-border);
  }

  .settings-nav {
    flex-direction: row;
    flex-wrap: nowrap;
    gap: var(--v6-space-1);
  }

  .settings-nav-item {
    height: 32px;
    padding: 0 var(--v6-space-2);
  }

  .nav-label {
    font-size: var(--v6-font-size-sm);
  }

  .sidebar-footer {
    display: none;
  }
}
</style>
