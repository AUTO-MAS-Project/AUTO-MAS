<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ConfigProvider } from 'ant-design-vue'
import { renderEmpty } from '@/components/renderEmpty'
import { t } from './i18n'
import { useTheme } from './composables/useTheme.ts'
import { useUpdateModal } from './composables/useUpdateChecker.ts'
import { useAppClosing } from './composables/useAppClosing.ts'
import { useAudioPlayer } from './composables/useAudioPlayer.ts'
import { useAppInitialization } from './composables/useAppInitialization.ts'
import AppLayout from './components/AppLayout.vue'
import TitleBar from './components/TitleBar.vue'
import UpdateModal from './components/UpdateModal.vue'
import GlobalPowerCountdown from './components/GlobalPowerCountdown.vue'
import AppClosingOverlay from './components/AppClosingOverlay.vue'
import BackendStartupOverlay from './components/BackendStartupOverlay.vue'
import CursorEffectLayer from './components/CursorEffectLayer.vue'
import AppearanceDecoration from './components/AppearanceDecoration.vue'
import ThemeTokenBridge from './components/ThemeTokenBridge'
import { useCursorEffectStore } from './stores/cursorEffect'
import { usePerformanceStore } from './stores/performance'
import { useLocale } from './composables/useLocale.ts'
import { useDesktopMascotHost } from './composables/useDesktopMascotHost'
import { useTrayTaskActions } from './composables/useTrayTaskActions'
import { isBackendRuntimeUpdating } from './composables/useBackendRuntimeUpdate'
import { useSchedulerLogic } from './views/scheduler/useSchedulerLogic'
import { TaskCreateIn } from './api'
import { isDevelopmentEnvironment as isDev } from '@/utils/environment'
import { useBackendI18nStore } from '@/stores/backendI18n'
import I18nResourceGate from '@/components/I18nResourceGate.vue'
import { navigateTo } from '@/router'
import { cancelAppEntry, resumePendingEntry, retryAppEntry } from '@/utils/appEntry'

const logger = window.electronAPI.getLogger('App组件')

// 开发工作台及其依赖只进开发构建，生产包不包含存储编辑与调试工具。
const DebugPanel =
  import.meta.env.DEV &&
  isDev &&
  (window as Window & { __AUTO_MAS_E2E__?: boolean }).__AUTO_MAS_E2E__ !== true
    ? defineAsyncComponent(() => import('./components/devtools/index.vue'))
    : null

const route = useRoute()
const { antdTheme } = useTheme()
const { antdLocale } = useLocale()
const { updateVisible, updateData, latestVersion, onUpdateConfirmed } = useUpdateModal()
const { isClosing } = useAppClosing()
const { playSound } = useAudioPlayer()
const { isInitialized, isBootstrapping, isAppReady } = useAppInitialization()
const cursorEffectStore = useCursorEffectStore()
const performanceStore = usePerformanceStore()
const languageResources = useBackendI18nStore()

// 判断是否为初始化页面
const isInitializationPage = computed(() => route.name === 'Initialization')

// 判断是否为独立页面（不需要 AppLayout 的页面：日志窗口、虚拟显示器询问弹窗）
const isStandalonePage = computed(
  () => route.name === 'Logs' || route.name === 'VirtualDisplayPrompt'
)

const { trackStartedTask } = useSchedulerLogic()
useDesktopMascotHost({
  isStandalonePage,
  isInitializationPage: computed(() => isInitializationPage.value || !languageResources.ready),
  playSound,
  trackStartedTask,
})
useTrayTaskActions({
  active: computed(
    () =>
      !isStandalonePage.value &&
      (isInitializationPage.value || (isAppReady.value && performanceStore.initialized))
  ),
  canStart: () => languageResources.ready && !isBackendRuntimeUpdating(),
  onStarted: task =>
    trackStartedTask({
      ...task,
      selectedMode: TaskCreateIn.mode.AUTO_PROXY,
      modeLabel: t('core.scheduler.mode.autoProxy'),
    }),
})

// 日志窗口属于初始化恢复；其他独立页面自行获取资源，不依赖主窗口的内存。
watch(
  () => languageResources.ready,
  ready => {
    if (!ready || isStandalonePage.value) return
    resumePendingEntry()
    if (isDev && !isInitializationPage.value && !isInitialized.value) {
      useAppInitialization().markAsInitialized()
    }
  }
)
watch(
  () => route.name,
  name => {
    if (name === 'VirtualDisplayPrompt') void languageResources.ensure()
  },
  { immediate: true }
)

async function retryLanguageResources() {
  if (isStandalonePage.value) await languageResources.refresh()
  else await retryAppEntry()
}

async function closeStandaloneWindow() {
  try {
    await window.electronAPI.closeVirtualDisplayPrompt?.()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`关闭虚拟显示器询问弹窗失败: ${errorMsg}`)
  }
}

async function recoverInitialization() {
  cancelAppEntry()
  languageResources.cancelEntry()
  sessionStorage.setItem('disableInitializationSkip', 'true')
  useAppInitialization().resetInitializationStatus()
  await navigateTo('/initialization', { replace: true })
}

onMounted(async () => {
  logger.info('App组件已挂载')
  logger.info('主题初始化完成')
  await performanceStore.initialize()
  logger.info(`性能模式初始化完成: ${performanceStore.lowPerformanceMode ? '低性能' : '标准'}`)
  await cursorEffectStore.load()
  logger.info(`光标效果初始化完成: ${cursorEffectStore.effect}`)
  logger.info(`初始化状态:
    isInitializationPage: ${isInitializationPage.value},
    isInitialized: ${isInitialized.value}
  `)

  // 注意：版本检查服务已在 appEntry.ts 中统一启动，此处不再重复启动

  // 播放欢迎音频（非初始化页面且已初始化时）
  if (!isInitializationPage.value && isInitialized.value) {
    logger.info('准备播放欢迎音频')
    await playSound('welcome_back')
  } else {
    logger.info(
      `跳过欢迎音频播放, 原因: ${isInitializationPage.value ? '当前是初始化页面' : '应用未初始化'}`
    )
  }
})
</script>

<template>
  <ConfigProvider :theme="antdTheme" :locale="antdLocale" :render-empty="renderEmpty">
    <ThemeTokenBridge />
    <AppearanceDecoration />
    <!-- 初始化页面使用带标题栏的全屏布局 -->
    <div v-if="isInitializationPage" class="initialization-container">
      <TitleBar />
      <div class="initialization-content">
        <router-view />
      </div>
    </div>
    <!-- 独立页面（如日志窗口）使用全屏布局，不包含 AppLayout -->
    <div v-else-if="isStandalonePage" class="standalone-container">
      <router-view v-if="route.name === 'Logs' || languageResources.ready" />
      <!-- 辅助窗口不能进入主应用初始化，否则会建立第二条主 WebSocket。 -->
      <I18nResourceGate
        v-else
        standalone
        @retry="retryLanguageResources"
        @close="closeStandaloneWindow"
      />
    </div>
    <!-- 其他页面使用带标题栏的应用布局 - 仅在初始化完成后挂载 -->
    <div v-else-if="isAppReady || languageResources.requested" class="app-container">
      <TitleBar />
      <AppLayout v-if="languageResources.ready && performanceStore.initialized" />
      <I18nResourceGate v-else @retry="retryLanguageResources" @recover="recoverInitialization" />
    </div>

    <!-- 开发构建才带调试面板；独立小窗口（日志、虚拟显示器询问）里它会盖住内容，不挂 -->
    <DebugPanel v-if="DebugPanel && !isStandalonePage && languageResources.ready" />

    <!-- 以下组件仅在初始化完成后挂载 -->
    <template v-if="isInitialized && languageResources.ready">
      <!-- 全局更新模态框 -->
      <UpdateModal
        v-model:visible="updateVisible"
        :update-data="updateData"
        :latest-version="latestVersion"
        @confirmed="onUpdateConfirmed"
      />

      <!-- 全局电源倒计时弹窗 -->
      <GlobalPowerCountdown />
    </template>

    <!-- 应用关闭遮罩 - 始终可用 -->
    <AppClosingOverlay :visible="isClosing" />
    <BackendStartupOverlay :visible="isBootstrapping && !languageResources.requested" />
    <CursorEffectLayer v-if="isAppReady && performanceStore.initialized" />
  </ConfigProvider>
</template>

<style>
* {
  box-sizing: border-box;
}

#app {
  background: transparent;
}

.app-container {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.initialization-container {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.initialization-content {
  position: relative;
  z-index: 1;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  width: 100%;
  /* 隐藏滚动条但保留滚动功能 */
  scrollbar-width: none;
  /* Firefox */
  -ms-overflow-style: none;
  /* IE/Edge */
}

.standalone-container {
  position: relative;
  z-index: 1;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

/* 隐藏 Webkit 浏览器的滚动条 */
.initialization-content::-webkit-scrollbar {
  display: none;
}
</style>
