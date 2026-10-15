<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ConfigProvider, message } from 'ant-design-vue'
import { t } from '@/i18n'
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
import { useHomeGreetingStore } from './stores/homeGreeting'
import { useLocale } from './composables/useLocale.ts'
import { onTaskRuntimeEvent } from './composables/useTaskRuntimeState'
import { resolveTaskCompletionFeedback, scriptHasStatus } from './utils/taskFailures'

const logger = window.electronAPI.getLogger('App组件')

// 调试面板及其子页只进开发构建：编译期常量让生产包直接摇掉这近两千行
const DebugPanel = import.meta.env.DEV
  ? defineAsyncComponent(() => import('./components/devtools/index.vue'))
  : null

const route = useRoute()
const { antdTheme, activeAppearance, antTokens } = useTheme()
const { antdLocale } = useLocale()
const { updateVisible, updateData, latestVersion, onUpdateConfirmed } = useUpdateModal()
const { isClosing } = useAppClosing()
const { playSound } = useAudioPlayer()
const { isInitialized, isBootstrapping, isAppReady } = useAppInitialization()
const cursorEffectStore = useCursorEffectStore()
const performanceStore = usePerformanceStore()
const homeGreetingStore = useHomeGreetingStore()

// 判断是否为初始化页面
const isInitializationPage = computed(() => route.name === 'Initialization')

// 判断是否为独立页面（不需要 AppLayout 的页面：日志窗口、虚拟显示器询问弹窗）
const isStandalonePage = computed(
  () => route.name === 'Logs' || route.name === 'VirtualDisplayPrompt'
)

const showDesktopMascotError = () => message.error(t('setting.basic.desktopMascotFailed'))
const disposeDesktopMascotError = window.electronAPI.onDesktopMascotError?.(showDesktopMascotError)
onUnmounted(() => disposeDesktopMascotError?.())
const announcedMascotTasks = new Set<string>()
const mascotRunningStatuses = new Set(['运行', '运行中'])
// 沿用任务总览的状态和收尾判定，不把部分失败误报为成功。
const disposeMascotTaskEvents = onTaskRuntimeEvent(event => {
  if (isStandalonePage.value || !isAppReady.value) return
  if (event.type === 'snapshot') {
    announcedMascotTasks.clear()
    for (const id of event.activeTaskIds) announcedMascotTasks.add(id)
    return
  }
  if (event.type === 'removed') {
    announcedMascotTasks.delete(event.taskId)
    return
  }
  const { state } = event
  if (state.mode === 'ScriptConfig') return
  const name = state.taskName || t('setting.basic.mascotTask')
  let text: string
  let reaction: 'success' | 'failure' | 'stopped' | undefined
  if (event.type === 'info') {
    if (
      announcedMascotTasks.has(state.taskId) ||
      !state.taskInfo.some(info => scriptHasStatus(info, mascotRunningStatuses))
    )
      return
    announcedMascotTasks.add(state.taskId)
    text = t('setting.basic.mascotTaskStarted', { name })
  } else if (event.type === 'completed' && state.outcome) {
    announcedMascotTasks.delete(state.taskId)
    const feedback = resolveTaskCompletionFeedback({
      outcome: state.outcome,
      task_info: state.taskInfo,
    })
    const key = {
      success: 'mascotTaskCompleted',
      error: 'mascotTaskFailed',
      cancelled: 'mascotTaskStopped',
      partialFailure: 'mascotTaskPartialFailure',
    }[feedback.kind]
    text = t(`setting.basic.${key}`, { name })
    reaction =
      feedback.kind === 'success'
        ? 'success'
        : feedback.kind === 'cancelled'
          ? 'stopped'
          : 'failure'
  } else return
  void window.electronAPI.showDesktopMascotNotice?.(text, reaction).catch(error => {
    logger.error('显示桌宠提醒失败:', error)
  })
})
onUnmounted(disposeMascotTaskEvents)
watch(
  () => homeGreetingStore.greeting,
  greeting => {
    if (isStandalonePage.value) return
    void window.electronAPI
      .setDesktopMascotIdleMessage?.({ text: greeting.text, author: greeting.author })
      .catch(error => {
        logger.error('同步桌宠待机留言失败:', error)
      })
  },
  { immediate: true }
)
watch(
  () => [performanceStore.anyScriptRunning, performanceStore.lowPerformanceMode] as const,
  ([working, lowPerformance]) => {
    if (isStandalonePage.value) return
    void window.electronAPI.setDesktopMascotActivity?.(working, !lowPerformance).catch(error => {
      logger.error('同步桌宠工作状态失败:', error)
    })
  },
  { immediate: true }
)
watch(
  () =>
    [
      isAppReady.value && performanceStore.initialized && !isInitializationPage.value,
      activeAppearance.value,
      antdLocale.value,
      antTokens.value,
    ] as const,
  ([ready, , , tokens]) => {
    if (isStandalonePage.value) return
    void window.electronAPI
      .setDesktopMascotReady?.(
        ready && Boolean(tokens),
        {
          pauseAnimation: t('setting.basic.mascotPauseAnimation'),
          resumeAnimation: t('setting.basic.mascotResumeAnimation'),
          pauseIdleMessage: t('setting.basic.mascotPauseIdleMessage'),
          resumeIdleMessage: t('setting.basic.mascotResumeIdleMessage'),
        },
        tokens
          ? {
              background: tokens.colorBgElevated,
              text: tokens.colorText,
              border: tokens.colorBorder,
              radius: tokens.borderRadius,
            }
          : undefined
      )
      .catch(error => {
        logger.error('同步桌面桌宠失败:', error)
        showDesktopMascotError()
      })
  },
  { immediate: true, flush: 'post' }
)

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
  <ConfigProvider :theme="antdTheme" :locale="antdLocale">
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
      <router-view />
    </div>
    <!-- 其他页面使用带标题栏的应用布局 - 仅在初始化完成后挂载 -->
    <div v-else-if="isAppReady && performanceStore.initialized" class="app-container">
      <TitleBar />
      <AppLayout />
    </div>

    <!-- 开发构建才带调试面板；独立小窗口（日志、虚拟显示器询问）里它会盖住内容，不挂 -->
    <DebugPanel v-if="DebugPanel && !isStandalonePage" />

    <!-- 以下组件仅在初始化完成后挂载 -->
    <template v-if="isInitialized">
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
    <BackendStartupOverlay :visible="isBootstrapping" />
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
