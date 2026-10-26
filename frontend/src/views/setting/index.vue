<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import type { GlobalConfig } from '@/api'
import type { CursorEffect } from '@/types/cursorEffect'
import { normalizeCursorEffect } from '@/types/cursorEffect'
import type { PressSoundPhase, PressSoundPreset } from '@/types/pressSound'
import { MAX_PRESS_SOUND_BYTES } from '@/types/pressSound'
import {
  clearCustomSoundCache,
  playPressSound,
  previewPressSound,
} from '@/components/satellite/pressSound'
import { useUpdateChecker } from '@/composables/useUpdateChecker.ts'
import { useCursorEffectStore } from '@/stores/cursorEffect'
import { usePerformanceStore } from '@/stores/performance'
import { useHomeSatelliteStore } from '@/stores/homeSatellite'
import { usePressSoundStore } from '@/stores/pressSound'
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
const pressSoundStore = usePressSoundStore()
void pressSoundStore.load()
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
const version = computed(() => import.meta.env.VITE_APP_VERSION || t('setting.versionFailed'))
const backendUpdateInfo = ref<VersionOut | null>(null)

// 设置数据 - 从API获取，不再使用硬编码初值
const settings = reactive<GlobalConfig>({})

// 下拉选项
const historyRetentionOptions = computed(() => [
  { label: t('setting.retention.d7'), value: 7 },
  { label: t('setting.retention.d15'), value: 15 },
  { label: t('setting.retention.d30'), value: 30 },
  { label: t('setting.retention.d60'), value: 60 },
  { label: t('setting.retention.d90'), value: 90 },
  { label: t('setting.retention.d180'), value: 180 },
  { label: t('setting.retention.d365'), value: 365 },
  { label: t('setting.retention.forever'), value: 0 },
])

const updateSourceOptions = computed(() => [
  { label: 'GitHub', value: 'GitHub' },
  { label: t('setting.source.MirrorChyan'), value: 'MirrorChyan' },
  { label: t('setting.source.AutoSite'), value: 'AutoSite' },
  { label: t('setting.source.CNB'), value: 'CNB' },
])

const updateChannelOptions = computed(() => [
  { label: t('setting.channel.stable'), value: 'stable' },
  { label: t('setting.channel.beta'), value: 'beta' },
])

const voiceTypeOptions = computed(() => [
  { label: t('setting.voice.simple'), value: 'simple' },
  { label: t('setting.voice.noisy'), value: 'noisy' },
])

const cursorEffectOptions = computed<{ label: string; value: CursorEffect }[]>(() => [
  { label: t('setting.cursor.none'), value: 'none' },
  { label: t('setting.cursor.sleekLine'), value: 'sleek-line' },
  { label: t('setting.cursor.fluid'), value: 'fluid' },
])

// 这几类配置 Electron 主进程也要用（托盘、自启、更新源等），保存后同步过去；
// 保存链路已抽到 useSettingPersistence，这里只留页面装配
const { loading, handleSettingChange, refreshSettings } = useSettingPersistence(
  settings,
  restartPolling
)

const confirmFluidCursor = () =>
  new Promise<boolean>(resolve => {
    Modal.confirm({
      title: t('setting.toast.fluidTitle'),
      content: t('setting.toast.fluidContent'),
      okText: t('setting.toast.fluidOk'),
      cancelText: t('common.cancel'),
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
    message.error(t('setting.toast.cursorSaveFailed'))
  }
}

const handleLowPerformanceModeChange = async (enabled: boolean) => {
  try {
    await performanceStore.setLowPerformanceMode(enabled)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存低性能模式失败: ${errorMsg}`)
    message.error(t('setting.toast.lowPerfSaveFailed'))
  }
}

const handlePauseHomeEffectsWhenRunningChange = async (enabled: boolean) => {
  try {
    await performanceStore.setPauseHomeEffectsWhenRunning(enabled)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存脚本运行暂停主页动效失败: ${errorMsg}`)
    message.error(t('setting.toast.pauseHomeEffectsSaveFailed'))
  }
}

const handleHomeSatelliteStyleChange = async (style: HomeSatelliteStyle) => {
  try {
    await homeSatelliteStore.setStyle(style)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存主页卫星样式失败: ${errorMsg}`)
    message.error(t('setting.toast.homeSatelliteSaveFailed'))
  }
}

const reportPressSoundError = (action: string, error: unknown): void => {
  const errorMsg = error instanceof Error ? error.message : String(error)
  logger.error(`${action}失败: ${errorMsg}`)
  message.error(t('setting.toast.pressSoundSaveFailed'))
}

const handlePressSoundEnabledChange = async (enabled: boolean) => {
  try {
    await pressSoundStore.persist({ enabled })
  } catch (error) {
    reportPressSoundError('保存按压音效开关', error)
  }
}

const handlePressSoundPresetChange = async (value: SelectValue) => {
  if (typeof value !== 'string') {
    return
  }

  try {
    await pressSoundStore.persist({ preset: value as PressSoundPreset })
  } catch (error) {
    reportPressSoundError('保存按压音效种类', error)
  }
}

const handlePressSoundVolumeChange = async (volume: number) => {
  try {
    await pressSoundStore.persist({ volume })
  } catch (error) {
    reportPressSoundError('保存按压音效音量', error)
  }
}

/** 导入自定义音频：单文件模式导一个，双文件模式分别导按下与松开 */
const handlePressSoundImport = async (kind: 'single' | 'press' | 'release' = 'single') => {
  try {
    const files = await window.electronAPI.selectFile([
      { name: '音频文件', extensions: ['wav', 'mp3', 'ogg', 'm4a', 'aac', 'flac'] },
    ])
    if (files.length === 0) {
      return
    }

    const filePath = files[0]
    // 上限交给主进程把关：超了它只回大小、不读内容，不会为了拒绝而先把整个文件读进内存。
    // 大小用它 stat 出来的真实字节数，不拿 base64 长度反推——那样会把 padding 当成文件内容
    const { base64, size } = await window.electronAPI.readFileBase64(
      filePath,
      MAX_PRESS_SOUND_BYTES
    )
    if (size > MAX_PRESS_SOUND_BYTES) {
      message.error(t('setting.toast.pressSoundTooLarge'))
      return
    }
    if (!base64) {
      message.error(t('setting.toast.pressSoundReadFailed'))
      return
    }
    // 同一个路径的文件可能被换过内容，缓存里的旧音频要作废
    clearCustomSoundCache(filePath)

    const name = filePath.split(/[\\/]/).pop() ?? filePath
    if (kind === 'single') {
      await pressSoundStore.persist({
        preset: 'custom',
        customPath: filePath,
        customName: name,
        enabled: true,
      })
    } else {
      // 双文件模式：导完第二个才切过去，只有一个文件时先只记路径
      const pressPath = kind === 'press' ? filePath : pressSoundStore.customPath
      const releasePath = kind === 'release' ? filePath : pressSoundStore.customReleasePath
      const ready = Boolean(pressPath && releasePath)
      await pressSoundStore.persist({
        ...(kind === 'press'
          ? { customPath: filePath, customName: name }
          : { customReleasePath: filePath, customReleaseName: name }),
        ...(ready ? { preset: 'customPair' as const, enabled: true } : {}),
      })
    }
    message.success(t('setting.toast.pressSoundImported'))
  } catch (error) {
    reportPressSoundError('导入按压音效', error)
  }
}

const handlePressSoundPreview = (phase?: PressSoundPhase) => {
  if (phase) {
    const filePath =
      phase === 'release' ? pressSoundStore.customReleasePath : pressSoundStore.customPath
    if (filePath) {
      void playPressSound({
        preset: 'custom',
        volume: pressSoundStore.volume,
        customPath: filePath,
      })
    }
    return
  }

  const options = {
    preset: pressSoundStore.preset,
    volume: pressSoundStore.volume,
    customPath: pressSoundStore.customPath,
    customReleasePath: pressSoundStore.customReleasePath,
  }
  void previewPressSound(options)
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
    <div class="settings-header">
      <h1 class="page-title">{{ t('setting.title') }}</h1>
    </div>
    <div class="settings-content">
      <a-tabs v-model:active-key="activeKey" type="card" :loading="loading" class="settings-tabs">
        <a-tab-pane key="basic" :tab="t('setting.tab.basic')">
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
            :press-sound-enabled="pressSoundStore.enabled"
            :press-sound-preset="pressSoundStore.preset"
            :press-sound-custom-path="pressSoundStore.customPath"
            :press-sound-custom-name="pressSoundStore.customName"
            :press-sound-custom-release-path="pressSoundStore.customReleasePath"
            :press-sound-custom-release-name="pressSoundStore.customReleaseName"
            :press-sound-volume="pressSoundStore.volume"
            :press-sound-saving="pressSoundStore.saving"
            :handle-press-sound-enabled-change="handlePressSoundEnabledChange"
            :handle-press-sound-preset-change="handlePressSoundPresetChange"
            :handle-press-sound-volume-change="handlePressSoundVolumeChange"
            :handle-press-sound-import="handlePressSoundImport"
            :handle-press-sound-preview="handlePressSoundPreview"
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
        </a-tab-pane>
        <a-tab-pane key="function" :tab="t('setting.tab.function')">
          <TabFunction
            :settings="settings"
            :history-retention-options="historyRetentionOptions"
            :voice-type-options="voiceTypeOptions"
            :handle-setting-change="handleSettingChange"
          />
        </a-tab-pane>
        <a-tab-pane key="notify" :tab="t('setting.tab.notify')">
          <TabNotify
            :settings="settings"
            :handle-setting-change="handleSettingChange"
            :test-notify="testNotify"
            :testing-notify="testingNotify"
          />
        </a-tab-pane>
        <a-tab-pane key="advanced" :tab="t('setting.tab.advanced')">
          <TabAdvanced :open-dev-tools="openDevTools" />
        </a-tab-pane>
        <a-tab-pane key="others" :tab="t('setting.tab.others')">
          <TabOthers
            :version="version"
            :backend-update-info="backendUpdateInfo"
            :settings="settings"
            :update-source-options="updateSourceOptions"
            :update-channel-options="updateChannelOptions"
            :handle-setting-change="handleSettingChange"
            :check-update="checkUpdate"
          />
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
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  /* Use full viewport min-height so the page can grow and scroll */
  display: flex;
  flex-direction: column;
}

.settings-header {
  margin-bottom: 16px;
  padding: 0 4px;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: var(
    --app-page-title-color,
    linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover))
  );
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.settings-content {
  background: var(--ant-color-bg-container);
  /* Rounded on all corners for a consistent card look */
  border-radius: 12px;
  width: 100%;
  flex: 1;
  /* allow inner scrolling and cooperate with flexbox
     min-height:0 prevents flex children from overflowing the container */
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.settings-tabs {
  margin: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px;
  /* ensure children with overflow:auto can scroll inside this flex item */
  min-height: 0;
}

.settings-tabs :deep(.ant-tabs-nav) {
  padding: 0;
  margin: 0;
}

.settings-tabs :deep(.ant-tabs-content-holder) {
  flex: 1;
  overflow: auto;
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
