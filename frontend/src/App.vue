<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ConfigProvider } from 'ant-design-vue'
import { useTheme } from './composables/useTheme.ts'
import { useUpdateChecker, useUpdateModal } from './composables/useUpdateChecker.ts'
import { useAppClosing } from './composables/useAppClosing.ts'
import { useAudioPlayer } from './composables/useAudioPlayer.ts'
import {
  beginBootstrap,
  finishBootstrap,
  markAsInitialized,
  resetInitializationStatus,
  useAppInitialization,
} from './composables/useAppInitialization.ts'
import { useAppStartup } from './composables/useAppStartup.ts'
import { closeApp, connectWithRetry } from './composables/useAppLifecycle.ts'
import { stopReconnect } from './services/websocket/connection.ts'
import AppLayout from './components/AppLayout.vue'
import TitleBar from './components/TitleBar.vue'
import UpdateModal from './components/UpdateModal.vue'
import DevDebugPanel from './components/DevDebugPanel.vue'
import GlobalPowerCountdown from './components/GlobalPowerCountdown.vue'
import WebSocketMessageListener from './components/WebSocketMessageListener.vue'
import AppClosingOverlay from './components/AppClosingOverlay.vue'
import BackendStartupOverlay from './components/BackendStartupOverlay.vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'

const logger = window.electronAPI.getLogger('App组件')

const route = useRoute()
const router = useRouter()
const { antdTheme, initTheme } = useTheme()
const { updateVisible, updateData, latestVersion, onUpdateConfirmed } = useUpdateModal()
const { stopPolling: stopUpdatePolling } = useUpdateChecker()
const { isClosing } = useAppClosing()
const { playSound } = useAudioPlayer()
const { isInitialized, isBootstrapping, isAppReady } = useAppInitialization()
const { state: startupState, setStatus, beginRetry, isFailure, currentGeneration } = useAppStartup()

const STARTUP_TIMEOUT_MS = 30000
let startupTimeoutId: number | undefined

/**
 * 手动重试进行中标志。
 * 当用户触发重试时置为 true，阻止 isBootstrapping watch 对旧 Promise/timer 的迟到回调
 * 覆盖 performStartupRetry 自管的状态流转。仅在当前 generation 仍有效时清除。
 */
let isManualRetryInProgress = false

const stopStartupTimeout = () => {
  if (startupTimeoutId !== undefined) {
    window.clearTimeout(startupTimeoutId)
    startupTimeoutId = undefined
  }
}

const startStartupTimeout = () => {
  stopStartupTimeout()
  startupTimeoutId = window.setTimeout(() => {
    if (isBootstrapping.value || startupState.value.status === 'reconnecting') {
      setStatus('timeout', {
        detail: `后端启动超过 ${STARTUP_TIMEOUT_MS / 1000} 秒仍未就绪，请检查后端日志或重试。`,
      })
    }
  }, STARTUP_TIMEOUT_MS)
}

/**
 * 启动遮罩只在启动彻底失败（offline/timeout/failed）或安全退出（closing）时全屏展示。
 * 真机反馈：五阶段全屏遮罩与主界面自身的分阶段加载重复——
 * 界面就绪即进入主界面，运行环境/后端/连接等阶段在后台继续
 * （主页「运行状态」卡与各卡片的加载态会体现进度），不再全屏阻塞。
 */
const isStartupOverlayVisible = computed(
  () => isFailure.value || startupState.value.status === 'closing'
)

watch(isBootstrapping, bootstrapping => {
  // 手动重试期间由 performStartupRetry 自管状态流转；
  // 旧 bootstrap Promise 的迟到回调（finishBootstrap/markAsInitialized）
  // 不应覆盖当前重试状态（例如把 'reconnecting'/'backend-starting' 覆盖为 'connected'）
  if (isManualRetryInProgress) {
    return
  }
  if (bootstrapping) {
    if (startupState.value.status !== 'backend-starting') {
      setStatus('backend-starting', { stage: 'backend' })
    }
    startStartupTimeout()
  } else {
    stopStartupTimeout()
    if (isInitialized.value) {
      setStatus('connected')
    } else if (!isFailure.value && startupState.value.status !== 'closing') {
      setStatus('failed', { detail: '应用未能完成初始化，请重试或查看日志。' })
    }
  }
})

watch(isInitialized, initialized => {
  if (initialized && !isBootstrapping.value) {
    setStatus('connected')
  }
})

const buildDiagnosticsText = () => {
  const lines = [
    `AUTO-MAS 启动诊断`,
    `状态: ${startupState.value.status}`,
    `信息: ${startupState.value.message}`,
  ]
  if (startupState.value.detail) lines.push(`详情: ${startupState.value.detail}`)
  lines.push(`时间: ${new Date().toISOString()}`)
  return lines.join('\n')
}

const isCurrentGeneration = (gen: number) => gen === currentGeneration.value

/**
 * 结束本轮启动尝试。
 * 通过 generation 检查隔离旧 Promise/timer 的迟到回调，避免覆盖当前状态。
 */
const finishStartupAttempt = (gen: number, success: boolean, detail?: string) => {
  if (!isCurrentGeneration(gen)) {
    logger.info(`generation ${gen} 已过期，忽略本轮启动结果`)
    return
  }
  stopStartupTimeout()
  finishBootstrap()
  if (success) {
    markAsInitialized()
    setStatus('connected', { stage: 'ready' })
    if (route.path !== '/home') {
      router.push('/home').catch(() => {})
    }
  } else {
    setStatus('failed', {
      stage: 'connection',
      detail: detail || '应用启动失败，请重试或查看日志。',
    })
  }
}

/**
 * 真正的启动重试：递增 generation 隔离旧 Promise/timer，
 * 停止现有 WebSocket 重连，重启后端进程，等待就绪后重连 WebSocket。
 * 任何异常都会退出永久 spinner 并显示结构化失败原因。
 */
const performStartupRetry = async () => {
  const gen = currentGeneration.value + 1
  // 标记手动重试进行中，阻止 isBootstrapping watch 对旧 Promise 的迟到回调
  // 覆盖本轮状态流转
  isManualRetryInProgress = true
  beginRetry()
  logger.info(`启动重试开始，generation=${gen}`)

  stopStartupTimeout()
  stopReconnect()
  resetInitializationStatus()
  beginBootstrap()
  setStatus('backend-starting', {
    stage: 'backend',
    message: '正在重启后端服务...',
  })
  startStartupTimeout()

  try {
    const restartResult = await window.electronAPI.backendRestart()
    if (!isCurrentGeneration(gen)) return
    if (!restartResult.success) {
      throw new Error(restartResult.error || '后端重启失败')
    }

    setStatus('reconnecting', {
      stage: 'connection',
      message: '正在重新连接后端...',
    })
    const ready = await window.electronAPI.backendWaitReady()
    if (!isCurrentGeneration(gen)) return
    if (!ready.ready) {
      throw new Error(ready.reason || '后端未就绪')
    }

    const connected = await connectWithRetry(5, 1000)
    if (!isCurrentGeneration(gen)) return
    if (!connected) {
      throw new Error('WebSocket 重连失败，请检查后端服务')
    }

    finishStartupAttempt(gen, true)
  } catch (error) {
    if (!isCurrentGeneration(gen)) return
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动重试失败: ${errorMsg}`)
    finishStartupAttempt(gen, false, errorMsg)
  } finally {
    // 仅当本轮仍是当前 generation 时清除标志，
    // 避免旧重试的 finally 清除新重试已设置的标志
    if (isCurrentGeneration(gen)) {
      isManualRetryInProgress = false
    }
  }
}

const handleStartupRetry = () => {
  logger.info('用户触发启动重试')
  // resetInitializationStatus 已由 performStartupRetry 内部执行，
  // 此处不再提前调用以避免触发未受保护的 watch
  void performStartupRetry()
}

const handleCopyDiagnostics = async () => {
  const text = buildDiagnosticsText()
  try {
    await navigator.clipboard.writeText(text)
    logger.info('诊断信息已复制到剪贴板')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`复制诊断信息失败: ${errorMsg}`)
  }
}

const handleOpenLogs = async () => {
  try {
    const logsPath = await window.electronAPI.getAppPath('logs')
    await window.electronAPI.showItemInFolder(logsPath)
    logger.info(`已打开日志目录: ${logsPath}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`打开日志目录失败，尝试导出日志: ${errorMsg}`)
    try {
      const result = await window.electronAPI.exportLogs()
      if (result.success && result.zipPath) {
        await window.electronAPI.showItemInFolder(result.zipPath)
      }
    } catch (fallbackError) {
      logger.error(`导出日志也失败: ${fallbackError}`)
    }
  }
}

const handleStartupExit = async () => {
  logger.info('用户从启动遮罩触发退出')
  setStatus('closing', { message: '正在安全退出应用...' })
  try {
    await closeApp()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`通过启动遮罩退出应用失败: ${errorMsg}`)
  }
}

// 判断是否为初始化页面
const isInitializationPage = computed(() => route.name === 'Initialization')

// 判断是否为独立页面（不需要 AppLayout 的页面）
const isStandalonePage = computed(() => route.name === 'Logs')

onMounted(async () => {
  logger.info('App组件已挂载')
  initTheme()
  logger.info('主题初始化完成')
  logger.info(`初始化状态:
    isInitializationPage: ${isInitializationPage.value},
    isInitialized: ${isInitialized.value}
  `)

  window.electronAPI.onStartupError?.(payload => {
    stopStartupTimeout()
    finishBootstrap()
    setStatus('failed', {
      stage: 'backend',
      message: '启动失败',
      detail: `[${payload.errorCode}] ${payload.errorDescription}`,
    })
  })

  // 如果挂载时 bootstrap 已经在进行（例如其他组件/页面已提前触发），
  // watch(isBootstrapping) 不会为初始值派发回调，需手动补齐状态与超时，
  // 否则会永久停在 'initializing' 而无超时保护
  if (isBootstrapping.value) {
    if (startupState.value.status !== 'backend-starting') {
      setStatus('backend-starting', { stage: 'backend' })
    }
    startStartupTimeout()
  }

  // 独立日志窗口只读取本地日志，不能进入主应用初始化流程。
  // 否则第二个 renderer 会再建立一条“唯一主 WebSocket”，把主窗口连接替换掉。
  if (!isInitializationPage.value && !isStandalonePage.value && !isInitialized.value) {
    router.push('/initialization').catch(() => {})
  }

  // 播放欢迎音频（非初始化页面且已初始化时）
  if (!isInitializationPage.value && !isStandalonePage.value && isInitialized.value) {
    logger.info('准备播放欢迎音频')
    await playSound('welcome_back')
  } else {
    logger.info(
      `跳过欢迎音频播放, 原因: ${isInitializationPage.value ? '当前是初始化页面' : '应用未初始化'}`
    )
  }
})

onUnmounted(() => {
  stopStartupTimeout()
  stopUpdatePolling()
  window.electronAPI.removeStartupErrorListener?.()
})
</script>

<template>
  <ConfigProvider :theme="antdTheme" :locale="zhCN">
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
    <div v-else-if="isAppReady" class="app-container">
      <TitleBar />
      <AppLayout />
    </div>

    <!-- 开发环境调试面板 - 开发工具始终可用 -->
    <DevDebugPanel />

    <!-- 以下组件仅在初始化完成后挂载 -->
    <template v-if="isInitialized && !isStandalonePage">
      <!-- 全局更新模态框 -->
      <UpdateModal
        v-model:visible="updateVisible"
        :update-data="updateData"
        :latest-version="latestVersion"
        @confirmed="onUpdateConfirmed"
      />

      <!-- 全局电源倒计时弹窗 -->
      <GlobalPowerCountdown />

      <!-- WebSocket 消息监听组件 -->
      <WebSocketMessageListener />
    </template>

    <!-- 后端启动遮罩 -->
    <BackendStartupOverlay
      :visible="isStartupOverlayVisible"
      :state="startupState"
      @retry="handleStartupRetry"
      @copy-diagnostics="handleCopyDiagnostics"
      @open-logs="handleOpenLogs"
      @exit="handleStartupExit"
    />

    <!-- 应用关闭遮罩 - 始终可用 -->
    <AppClosingOverlay :visible="isClosing" />
  </ConfigProvider>
</template>

<style>
@import './styles/v6-tokens.css';

* {
  box-sizing: border-box;
}

/* Ant switch 是紧凑二态控件；即使位于纵向 flex/grid 中也不得被拉伸成整行轨道。 */
.ant-switch {
  width: max-content;
  flex: 0 0 auto;
}

.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.initialization-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.initialization-content {
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
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

/* 隐藏 Webkit 浏览器的滚动条 */
.initialization-content::-webkit-scrollbar {
  display: none;
}
</style>
