<template>
  <div
    ref="container"
    class="satellite-container"
    :class="{ 'is-pointing': pointingSatellite, 'is-dragging': dragging }"
    @pointerdown="handlePointerDown"
    @pointermove="handlePointerMove"
    @pointerup="handlePointerUp"
    @pointercancel="cancelPress"
    @pointerleave="handlePointerLeave"
  >
    <div v-if="loading" class="loading-spinner"></div>
    <div v-show="hoverLabel" ref="labelElement" class="satellite-label">
      <span class="satellite-label-name">{{ hoverLabel?.name }}</span>
      <span v-if="hoverLabel?.status" class="satellite-label-status">{{ hoverLabel.status }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import { useScriptApi } from '@/composables/useScriptApi'
import { satelliteModules, centerIconUrl } from '@/composables/satellite-config'
import { useSatelliteStatus, type SatelliteModuleStatus } from '@/composables/useSatelliteStatus'
import { requestUpdateCheck } from '@/composables/useUpdateChecker'
import { usePerformanceStore } from '@/stores/performance'
import { connectionState, onConnected } from '@/services/websocket/connection'
import type { ScriptType } from '@/types/script'
import { SCRIPT_LABELS } from '@/utils/scriptLogos'
import { createFloatTextLayer, type FloatTextVariant } from './satellite/floatText'
import { createAnimationFrameScheduler } from './satellite/frameScheduler'
import { SatelliteScene, type ScreenPoint } from './satellite/satelliteScene'
import { useSatelliteEggs } from './satellite/useSatelliteEggs'
import { useSatellitePointer } from './satellite/useSatellitePointer'

/** 主 WS 没开着时，按这个间隔拉运行快照兜底 */
const STATUS_POLL_INTERVAL = 10000

const { t } = useI18n()
const logger = window.electronAPI.getLogger('卫星动画')
const { isDark } = useTheme()
const { getScripts } = useScriptApi()
const performanceStore = usePerformanceStore()
// 卫星状态来自任务运行时常驻订阅（WS 增量 + HTTP 快照兜底）
const { statuses: satelliteStatuses, refresh: refreshSatelliteStatuses } = useSatelliteStatus()

const container = ref<HTMLDivElement | null>(null)
const labelElement = ref<HTMLDivElement | null>(null)
const loading = ref(true)
/** 指针停在卫星上时显示手型；中心图标的连点是彩蛋，不提示可点 */
const pointingSatellite = ref(false)
const hoveredSatellite = ref<number | null>(null)
const hoveredType = ref<ScriptType | null>(null)

let scene: SatelliteScene | null = null
let isUnmounted = false
let statusPollTimer: ReturnType<typeof setInterval> | null = null
let disposeBackendReadyListener: (() => void) | null = null
let lastFrameAt: number | null = null
const frameScheduler = createAnimationFrameScheduler(requestAnimationFrame, cancelAnimationFrame)
const floatTexts = createFloatTextLayer()
const eggs = useSatelliteEggs({
  getScene: () => scene,
  isLowPower: () => performanceStore.isLowPower,
  spawnText,
  getContainerSize: () =>
    container.value
      ? { width: container.value.clientWidth, height: container.value.clientHeight }
      : null,
  requestRender,
})
const {
  dragging,
  handlePointerDown,
  handlePointerMove,
  handlePointerUp,
  handlePointerLeave,
  cancelPress,
  updateCoreCharge,
} = useSatellitePointer({
  getScene: () => scene,
  getContainer: () => container.value,
  isLowPower: () => performanceStore.isLowPower,
  isBackgrounded: () => performanceStore.isBackgrounded,
  setHovered,
  spawnText,
  requestRender,
  onCenterTap: eggs.pokeCenter,
  onSatelliteTap: handleSatelliteTap,
})

/** 悬停标签：脚本名，有运行状态时带上状态 */
const hoverLabel = computed(() => {
  const type = hoveredType.value
  if (!type) return null
  return { name: SCRIPT_LABELS[type], status: describeStatus(satelliteStatuses.value.get(type)) }
})

// ==================== 监听 ====================

watch(isDark, dark => {
  scene?.setDark(dark)
  requestRender()
})

// 常驻订阅推送新状态时同步刷新展示
watch(satelliteStatuses, statuses => {
  scene?.setStatuses(statuses)
  requestRender()
})

watch(
  () => performanceStore.lowPerformanceMode,
  lowPerformanceMode => {
    if (!scene) return

    scene.setLowPerformance(lowPerformanceMode)
    if (lowPerformanceMode) {
      // 彩蛋跟着低性能模式一起收掉：不然会停在一张静止的彩虹图上，补渲一帧还会跳一次色相
      scene.setCenterRainbow(false)
      scene.resetCenterPress()
      scene.skipAppear()
    }
    requestRender()
  }
)

// WS 打开时事件推送足够，停掉 HTTP 轮询（运行态资源在 onConnected 里已重拉一次快照）；
// 掉线期间再靠轮询兜底
watch(connectionState(), state => {
  if (isUnmounted || performanceStore.isBackgrounded) return
  if (state === 'open') {
    stopStatusPolling()
  } else {
    startStatusPolling()
  }
})

watch(
  () => performanceStore.isBackgrounded,
  async isBackgrounded => {
    if (isBackgrounded) {
      frameScheduler.cancel()
      stopStatusPolling()
      cancelPress()
      scene?.clearExplosions()
      return
    }

    await nextTick()
    if (isUnmounted) return

    if (scene) {
      scene.resize()
      scene.skipAppear()
      scene.setStatuses(satelliteStatuses.value)
    }
    lastFrameAt = null
    requestRender()
    void waitBackendReady().then(() => {
      if (isUnmounted || performanceStore.isBackgrounded) return
      void refreshSatelliteStatuses()
      startStatusPolling()
    })
  }
)

// ==================== 生命周期 ====================

onMounted(async () => {
  await waitBackendReady()
  if (isUnmounted) return

  try {
    await initScene()
  } catch (err) {
    logger.error(`初始化场景失败: ${String(err)}`)
  } finally {
    loading.value = false
  }
  if (isUnmounted || !scene || !container.value) return

  requestRender()
  window.addEventListener('resize', handleResize)
  window.addEventListener('keydown', eggs.handleKeydown)

  void refreshSatelliteStatuses()
  startStatusPolling()

  // 有新版本时中心光晕换成彩虹
  try {
    const updateRes = await requestUpdateCheck(false)
    if (updateRes.code === 200 && updateRes.if_need_update && !isUnmounted) {
      scene?.setCenterGlowMode('rainbow')
      requestRender()
    }
  } catch {
    // 静默失败，保持绿色
  }
})

onUnmounted(() => {
  isUnmounted = true
  disposeBackendReadyListener?.()
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('keydown', eggs.handleKeydown)
  frameScheduler.cancel()
  stopStatusPolling()
  floatTexts.dispose()
  scene?.dispose()
  scene = null
})

// ==================== 场景 ====================

// 后端未就绪（主 WS 未 open）时不发请求：启动遮罩期间立即初始化会把脚本列表与
// 运行快照打向尚未监听的端口，请求直接以 "Network Error" 弹错，卫星也会整场不渲染。
function waitBackendReady(): Promise<void> {
  if (connectionState().value === 'open') return Promise.resolve()
  return new Promise(resolve => {
    disposeBackendReadyListener = onConnected(() => {
      disposeBackendReadyListener = null
      resolve()
    })
  })
}

async function initScene(): Promise<void> {
  let userScripts: Awaited<ReturnType<typeof getScripts>> = []
  try {
    userScripts = await getScripts()
  } catch (err) {
    logger.warn(`获取脚本列表失败，按空集合处理: ${String(err)}`)
  }
  if (!container.value || isUnmounted) return

  // 只有用户建过的脚本类型才上轨道
  const userScriptTypes = new Set<ScriptType>(userScripts.map(s => s.type as ScriptType))
  const modules = satelliteModules.filter(m => m.enabled && userScriptTypes.has(m.scriptType))
  if (modules.length === 0) {
    logger.info('没有可显示的卫星模块，仅渲染中心图标和轨道')
  }

  const created = new SatelliteScene(container.value, {
    lowPerformance: performanceStore.lowPerformanceMode,
    isDark: isDark.value,
  })
  try {
    if (!(await created.load(centerIconUrl, modules, () => isUnmounted))) {
      created.dispose()
      return
    }
  } catch (err) {
    created.dispose()
    throw err
  }

  scene = created
  // 加载图片期间主题或低性能模式可能已经变了，watcher 那时还够不着场景
  scene.setDark(isDark.value)
  scene.setLowPerformance(performanceStore.lowPerformanceMode)
  scene.setStatuses(satelliteStatuses.value)
  if (performanceStore.isLowPower) {
    scene.skipAppear()
  } else {
    scene.startAppear(Date.now())
  }
}

/** 画一帧。平时逐帧连续画；低性能模式只在有变化时补帧，动画放完之前例外 */
function drawFrame(): void {
  if (isUnmounted || !scene || performanceStore.isBackgrounded) return

  const now = Date.now()
  const dt = lastFrameAt === null ? 16 : Math.min(100, now - lastFrameAt)
  lastFrameAt = now
  updateCoreCharge()
  eggs.checkDizzy(dt, now)

  const busy = scene.renderFrame(now)
  updateLabelPosition()
  if (!performanceStore.isLowPower || busy) {
    frameScheduler.request(drawFrame)
  }
}

function requestRender(): void {
  if (isUnmounted || !scene || performanceStore.isBackgrounded) return
  frameScheduler.request(drawFrame)
}

function handleResize(): void {
  scene?.resize()
  requestRender()
}

function stopStatusPolling(): void {
  if (statusPollTimer === null) return
  clearInterval(statusPollTimer)
  statusPollTimer = null
}

function startStatusPolling(): void {
  if (
    performanceStore.isBackgrounded ||
    statusPollTimer !== null ||
    connectionState().value === 'open'
  ) {
    return
  }

  // 周期性 HTTP 快照兜底：只在主 WS 没开着时轮询；WS 开着靠 task.* 事件推送
  statusPollTimer = setInterval(() => void refreshSatelliteStatuses(), STATUS_POLL_INTERVAL)
}

// ==================== 悬停标签 ====================

function describeStatus(status: SatelliteModuleStatus | undefined): string {
  if (!status) return ''
  if (status.lastFailed) {
    return t(status.running ? 'home.satelliteStatus.failedRunning' : 'home.satelliteStatus.failed')
  }
  if (status.running) return t('home.satelliteStatus.running')
  if (status.queued) return t('home.satelliteStatus.queued')
  return ''
}

function setHovered(index: number | null): void {
  if (hoveredSatellite.value === index) return
  hoveredSatellite.value = index
  hoveredType.value = index === null ? null : (scene?.satelliteType(index) ?? null)
  pointingSatellite.value = index !== null
  scene?.setHovered(index)
  requestRender()
}

/** 标签跟着卫星走，每帧直接改样式，不经过响应式 */
function updateLabelPosition(): void {
  const index = hoveredSatellite.value
  const element = labelElement.value
  if (index === null || !element || !scene) return
  const point = scene.projectSatellite(index)
  if (point) {
    element.style.transform = `translate(${point.x}px, ${point.y - 52}px) translate(-50%, -100%)`
  }
}

// ==================== 交互 ====================

function handleSatelliteTap(index: number, now: number): void {
  if (!scene) return
  if (!scene.explode(index, now)) {
    scene.ping(index, now)
  }
  eggs.pokeSatellite(index)
}

function spawnText(point: ScreenPoint, text: string, variant: FloatTextVariant): void {
  if (!container.value || isUnmounted) return
  floatTexts.spawn(container.value, point, text, variant)
}
</script>

<style scoped>
.satellite-container {
  width: 100%;
  height: 400px;
  position: relative;
  overflow: hidden;
  user-select: none;
}

.satellite-container.is-pointing {
  cursor: pointer;
}

.satellite-container.is-dragging {
  cursor: grabbing;
}

.loading-spinner {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 32px;
  height: 32px;
  margin: -16px 0 0 -16px;
  border: 2px solid var(--ant-color-border);
  border-top-color: var(--ant-color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.satellite-label {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-elevated);
  box-shadow: var(--ant-box-shadow-secondary);
  color: var(--ant-color-text);
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
  pointer-events: none;
}

.satellite-label-name {
  font-weight: 600;
}

.satellite-label-status {
  color: var(--ant-color-text-secondary);
}

/* 浮字是运行时创建的，不在模板里，scoped 的选择器要用 :deep 才管得到 */
.satellite-container :deep(.star-burst) {
  position: absolute;
  /* 浮字得压在场景画布上面才看得见 */
  z-index: 10;
  transform: translate(-50%, -50%);
  font-size: 17px;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: var(--ant-color-warning);
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
  pointer-events: none;
  white-space: nowrap;
  will-change: transform, opacity;
}

.satellite-container :deep(.star-burst-hint) {
  font-size: 20px;
  color: var(--ant-color-primary);
}

.satellite-container :deep(.star-burst-huge) {
  font-size: 44px;
  font-weight: 900;
  letter-spacing: 0.06em;
  color: var(--ant-color-warning);
  -webkit-text-stroke: 1.5px rgba(0, 0, 0, 0.35);
  text-shadow: 0 4px 18px rgba(0, 0, 0, 0.35);
}

.satellite-container :deep(.star-burst-rainbow) {
  background-image: linear-gradient(90deg, #ff5f6d, #ffc371, #47e5bc, #4facfe, #b06ab3, #ff5f6d);
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  -webkit-text-fill-color: transparent;
  text-shadow: none;
  animation: star-rainbow 1.2s linear infinite;
}

@keyframes star-rainbow {
  to {
    background-position: 200% center;
  }
}
</style>
