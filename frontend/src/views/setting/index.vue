<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import type { GlobalConfig } from '@/api'
import type { CursorEffect } from '@/types/cursorEffect'
import { normalizeCursorEffect } from '@/types/cursorEffect'
import { useUpdateChecker } from '@/composables/useUpdateChecker.ts'
import { useCursorEffectStore } from '@/stores/cursorEffect'
import { usePerformanceStore } from '@/stores/performance'
import { useHomeSatelliteStore } from '@/stores/homeSatellite'
import type { HomeSatelliteStyle } from '@/types/homeSatellite'
import { Service, type VersionOut } from '@/api'
import { useAppearanceSettings } from './useAppearanceSettings'
import { useSettingPersistence } from './useSettingPersistence'
import { useNotificationTest } from './useNotificationTest'

defineOptions({ name: 'SettingsPage' })

const logger = window.electronAPI.getLogger('设置')

// 引入拆分后的 Tab 组件
import TabBasic from './TabBasic.vue'
import TabFunction from './TabFunction.vue'
import TabNotify from './TabNotify.vue'
import TabAdvanced from './TabAdvanced.vue'
import TabOthers from './TabOthers.vue'
import SettingsSectionLayout from './components/SettingsSectionLayout.vue'

const { t } = useI18n()
const {
  themeMode,
  themeColor,
  appearances,
  appearanceId,
  activeAppearance,
  modalContextHolder,
  appearanceBusy,
  themeResetting,
  themeModeOptions,
  appearanceValue,
  appearanceOptions,
  themeColorOptions,
  handleThemeModeChange,
  handleThemeColorChange,
  handleAppearanceChange,
  handleAppearanceImport,
  handleAppearanceRemove,
  handleThemeReset,
} = useAppearanceSettings()
const cursorEffectStore = useCursorEffectStore()
const performanceStore = usePerformanceStore()
const homeSatelliteStore = useHomeSatelliteStore()
void homeSatelliteStore.load()
const {
  restartPolling,
  updateVisible,
  updateData,
  latestVersion,
  checkUpdate: globalCheckUpdate,
} = useUpdateChecker()

// 活动标签
const route = useRoute()
const activeKey = ref(route.query.tab === 'function' ? 'function' : 'basic')
const version = computed(() => import.meta.env.VITE_APP_VERSION || t('core.setting.versionFailed'))
const backendUpdateInfo = ref<VersionOut | null>(null)

// 设置数据 - 从API获取，不再使用硬编码初值
const settings = reactive<GlobalConfig>({})

const cursorEffectOptions = computed<{ label: string; value: CursorEffect }[]>(() => [
  { label: t('core.setting.cursor.none'), value: 'none' },
  { label: t('core.setting.cursor.sleekLine'), value: 'sleek-line' },
  { label: t('core.setting.cursor.fluid'), value: 'fluid' },
])

// 这几类配置 Electron 主进程也要用（托盘、自启、更新源等），保存后同步过去；
// 保存链路已抽到 useSettingPersistence，这里只留页面装配
const { loading, handleSettingChange, handleDynamicSettingChange, refreshSettings } =
  useSettingPersistence(settings, restartPolling)

const confirmFluidCursor = () =>
  new Promise<boolean>(resolve => {
    Modal.confirm({
      title: t('core.setting.toast.fluidTitle'),
      content: t('core.setting.toast.fluidContent'),
      okText: t('core.setting.toast.fluidOk'),
      cancelText: t('core.common.cancel'),
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })

const handleCursorEffectChange = async (value: SelectValue) => {
  if (typeof value !== 'string') {
    return
  }

  const nextEffect = normalizeCursorEffect(value)
  if (nextEffect === cursorEffectStore.effect) {
    return
  }

  if (nextEffect === 'fluid' && !(await confirmFluidCursor())) {
    return
  }

  try {
    await cursorEffectStore.setEffect(nextEffect)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存光标效果失败: ${errorMsg}`)
    message.error(t('core.setting.toast.cursorSaveFailed'))
  }
}

const handleLowPerformanceModeChange = async (enabled: boolean) => {
  try {
    await performanceStore.setLowPerformanceMode(enabled)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存低性能模式失败: ${errorMsg}`)
    message.error(t('core.setting.toast.lowPerfSaveFailed'))
  }
}

const handlePauseHomeEffectsWhenRunningChange = async (enabled: boolean) => {
  try {
    await performanceStore.setPauseHomeEffectsWhenRunning(enabled)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存脚本运行暂停主页动效失败: ${errorMsg}`)
    message.error(t('core.setting.toast.pauseHomeEffectsSaveFailed'))
  }
}

const handleHomeSatelliteStyleChange = async (style: HomeSatelliteStyle) => {
  try {
    await homeSatelliteStore.setStyle(style)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存主页卫星样式失败: ${errorMsg}`)
    message.error(t('core.setting.toast.homeSatelliteSaveFailed'))
  }
}

// 其他操作
const openDevTools = () => window.electronAPI?.openDevTools?.()

// 更新检查 - 使用全局更新检查器
const checkUpdate = async () => {
  logger.info('使用全局更新检查器进行手动检查')

  // 手动检查立即恢复：先终止暂停、清空截止日期，再做完整检查
  if (settings.Update?.PauseUntil) {
    await handleSettingChange('Update', 'PauseUntil', null)
  }

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
  try {
    backendUpdateInfo.value = await Service.getGitVersionApiInfoVersionPost()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`获取后端版本失败: ${errorMsg}`)
  }
}

const { testingNotify, testNotify } = useNotificationTest(logger)

onMounted(() => {
  void cursorEffectStore.load()
  void performanceStore.initialize()
  refreshSettings()
  getBackendVersion()
})
</script>

<template>
  <div class="settings-container">
    <component :is="modalContextHolder" />
    <SettingsSectionLayout v-model:active-key="activeKey" :loading="loading">
      <template #header>
        <div class="settings-header">
          <h1 class="page-title app-page-title">{{ t('core.setting.title') }}</h1>
          <p class="settings-subtitle">{{ t('core.setting.subtitle') }}</p>
        </div>
      </template>
      <template #basic>
        <TabBasic
          :settings="settings"
          :theme-mode="themeMode"
          :appearance-value="appearanceValue"
          :appearance-options="appearanceOptions"
          :theme-color="themeColor"
          :theme-color-disabled="Boolean(activeAppearance)"
          :appearance-busy="appearanceBusy || themeResetting"
          :theme-resetting="themeResetting"
          :theme-mode-options="themeModeOptions"
          :theme-color-options="themeColorOptions"
          :cursor-effect="cursorEffectStore.effect"
          :cursor-effect-options="cursorEffectOptions"
          :low-performance-mode="performanceStore.lowPerformanceMode"
          :low-performance-mode-saving="performanceStore.saving"
          :pause-home-effects-when-running="performanceStore.pauseHomeEffectsWhenRunning"
          :pause-home-effects-when-running-saving="performanceStore.saving"
          :home-satellite-style="homeSatelliteStore.style"
          :home-satellite-style-saving="homeSatelliteStore.saving"
          :handle-home-satellite-style-change="handleHomeSatelliteStyleChange"
          :handle-theme-mode-change="handleThemeModeChange"
          :handle-appearance-change="handleAppearanceChange"
          :handle-appearance-import="handleAppearanceImport"
          :handle-appearance-remove="handleAppearanceRemove"
          :handle-theme-color-change="handleThemeColorChange"
          :handle-theme-reset="handleThemeReset"
          :handle-cursor-effect-change="handleCursorEffectChange"
          :handle-low-performance-mode-change="handleLowPerformanceModeChange"
          :handle-pause-home-effects-when-running-change="handlePauseHomeEffectsWhenRunningChange"
          :handle-setting-change="handleSettingChange"
        />
      </template>
      <template #function>
        <TabFunction :settings="settings" :handle-setting-change="handleSettingChange" />
      </template>
      <template #notify>
        <TabNotify
          :settings="settings"
          :handle-setting-change="handleDynamicSettingChange"
          :test-notify="testNotify"
          :testing-notify="testingNotify"
        />
      </template>
      <template #advanced>
        <TabAdvanced :open-dev-tools="openDevTools" />
      </template>
      <template #others>
        <TabOthers
          :version="version"
          :backend-update-info="backendUpdateInfo"
          :settings="settings"
          :handle-setting-change="handleSettingChange"
          :check-update="checkUpdate"
          @fluxdown-installed="refreshSettings"
        />
      </template>
    </SettingsSectionLayout>
    <!-- 更新弹窗由 App.vue 统一管理 -->
  </div>
</template>

<style scoped>
/* 统一样式，使用 :deep 作用到子组件内部 */
.settings-container {
  position: relative;
  isolation: isolate;
  width: 100%;
  height: 100%;
  min-height: 0;
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.settings-header {
  padding: 0;
}

.page-title {
  margin: 0;
  color: var(--app-page-title-color, var(--ant-color-text));
  background: none;
  font-size: 28px;
  line-height: 36px;
  -webkit-text-fill-color: currentcolor;
}

.settings-subtitle {
  margin: 4px 0 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

:deep(.form-section:last-child) {
  margin-bottom: 0;
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

/* 项目链接与应用信息的样式已随布局迁入各卡片组件（TabOthers.vue scoped），
   这里不再保留同名 :deep 规则，避免与子组件的同选择器互相覆盖 */
</style>
