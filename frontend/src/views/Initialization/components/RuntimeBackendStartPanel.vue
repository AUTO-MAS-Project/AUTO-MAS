<template>
  <LaunchFailure
    v-if="status === 'failed'"
    :title="t('init.steps.backend')"
    :message="errorMessage"
    :failure-actions="BACKEND_FAILURE_ACTIONS"
    :failure-logs="backendLogs"
    :show-skip-button="showSkipButton"
    :docs-url="BACKEND_START_FAILURE_DOC_URL"
    @action="handleFailureAction"
    @open-docs="handleOpenDocumentation"
    @skip="emit('skip')"
  />
  <LaunchStatus
    v-else
    :title="retrying ? t('launch.retrying') : t('launch.starting')"
    :hint="hintText"
    :action-label="slow ? t('launch.viewLog') : ''"
    @action="openLaunchLogWindow('后端启动步骤')"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import LaunchStatus from '@/components/LaunchStatus.vue'
import { bootstrapRealtimeResidents } from '@/bootstrap/realtimeResidents'
import { connectWithRetry, initializeAppLifecycle } from '@/composables/useAppLifecycle'
import { useUpdateChecker } from '@/composables/useUpdateChecker'
import { SLOW_LAUNCH_THRESHOLD_MS, openLaunchLogWindow } from '@/utils/launch'
import LaunchFailure from './LaunchFailure.vue'
import type { RuntimeFailureFields } from '@/types/electron'
import type { FailureAction, FailureActionKind } from '@/utils/initializationDecision'

defineOptions({ name: 'RuntimeBackendStartPanel' })

interface Props {
  showSkipButton?: boolean
  /** 静默启动失败后回落到本页时为真，文案要说明是在重试而不是首次启动。 */
  retrying?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showSkipButton: false,
  retrying: false,
})

const emit = defineEmits<{
  'update:status': [status: 'waiting' | 'starting' | 'running' | 'success' | 'failed']
  complete: []
  error: [error: string, failure: RuntimeFailureFields]
  skip: []
}>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('后端启动步骤')
const { startPolling } = useUpdateChecker()

// 后端起不来时能做的只有重试，换源和重建环境都轮不到这一段。
// 加一个查看日志：这一段的失败结果不带 logPath，spawn 之前就失败时连日志正文都没有，
// 「详细信息」折叠整块不出现，不给入口的话这一屏一个日志出口都没有。
const BACKEND_FAILURE_ACTIONS: FailureAction[] = [
  { kind: 'retry', labelKey: 'init.step.retry' },
  { kind: 'open-log', labelKey: 'launch.viewLog' },
]

const BACKEND_START_FAILURE_DOC_URL =
  'https://doc.auto-mas.top/docs/FAQ.html#%E5%90%8E%E7%AB%AF%E5%90%AF%E5%8A%A8%E5%A4%B1%E8%B4%A5-%E8%B7%B3%E8%BF%87%E5%90%8E%E5%BA%94%E7%94%A8%E5%86%85%E4%B8%8D%E5%81%9C%E6%8A%A5%E9%94%99-network-error'

const status = ref<'waiting' | 'starting' | 'running' | 'success' | 'failed'>('waiting')
const errorMessage = ref('')
const backendLogs = ref('')
const slow = ref(false)
let startTimer: ReturnType<typeof setTimeout> | null = null
let completeTimer: ReturnType<typeof setTimeout> | null = null
let slowTimer: ReturnType<typeof setTimeout> | null = null

const hintText = computed(() => {
  if (slow.value) return t('launch.slowHint')
  return props.retrying ? t('launch.retryingHint') : ''
})

function clearSlowTimer() {
  if (!slowTimer) return
  clearTimeout(slowTimer)
  slowTimer = null
}

function restartSlowTimer() {
  clearSlowTimer()
  slow.value = false
  slowTimer = setTimeout(() => {
    slow.value = true
  }, SLOW_LAUNCH_THRESHOLD_MS)
}

async function handleOpenDocumentation() {
  try {
    const result = await window.electronAPI.openUrl(BACKEND_START_FAILURE_DOC_URL)
    if (!result.success) logger.error(`打开后端启动失败文档失败: ${String(result.error)}`)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    logger.error(`打开后端启动失败文档失败: ${message}`)
  }
}

async function startBackend() {
  status.value = 'starting'
  emit('update:status', 'starting')
  backendLogs.value = ''
  errorMessage.value = ''
  restartSlowTimer()
  let failure: RuntimeFailureFields = {}
  let wsConnected = false
  let pollingStarted = false

  try {
    const result = await window.electronAPI.backendStart()

    if (!result.success) {
      failure = result
      backendLogs.value = result.logs || ''
      throw new Error(result.error || t('init.backend.failedTitle'))
    }

    const backendStatus = await window.electronAPI.backendStatus()
    status.value = 'running'
    emit('update:status', 'running')

    // 以下几步对用户是同一件事「正在启动」，进度只写日志，不往界面上播报。
    bootstrapRealtimeResidents()
    initializeAppLifecycle()

    wsConnected = await connectWithRetry()
    if (!wsConnected) logger.warn('WebSocket连接建立失败，将由应用内重连机制继续尝试')

    await startPolling()
    pollingStarted = true

    try {
      const finalStatus = await window.electronAPI.backendStatus()
      if (!finalStatus.isRunning) throw new Error(t('init.backend.notRunning'))
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      logger.warn(`后端连接验证失败，但继续执行: ${message}`)
    }

    status.value = 'success'
    clearSlowTimer()
    emit('update:status', 'success')
    logger.info(
      `后端服务启动完成 - PID: ${backendStatus.pid}, WebSocket: ${wsConnected ? '已连接' : '未连接'}, 版本检查: ${pollingStarted ? '已启动' : '未启动'}`
    )

    completeTimer = setTimeout(() => emit('complete'), 300)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    logger.error(`后端启动失败: ${message}`)
    clearSlowTimer()
    status.value = 'failed'
    emit('update:status', 'failed')
    errorMessage.value = message
    emit('error', message, failure)
  }
}

async function handleFailureAction(kind: FailureActionKind) {
  if (kind === 'open-log') {
    await openLaunchLogWindow('后端启动步骤')
    return
  }
  await startBackend()
}

onMounted(() => {
  window.electronAPI.onBackendStatus?.(backendStatus => {
    logger.debug(`收到后端状态: ${JSON.stringify(backendStatus)}`)
  })

  startTimer = setTimeout(() => {
    void startBackend()
  }, 400)
})

onUnmounted(() => {
  if (startTimer) clearTimeout(startTimer)
  if (completeTimer) clearTimeout(completeTimer)
  clearSlowTimer()
  window.electronAPI.removeBackendStatusListener?.()
})
</script>
