<template>
  <div
    ref="container"
    class="satellite-container"
    :class="{ 'is-pointing': pointingSatellite }"
    @click="handleClick"
    @pointermove="handlePointerMove"
    @pointerleave="handlePointerLeave"
    @pointerdown="handlePointerDown"
    @pointerup="releaseCenter"
    @pointercancel="releaseCenter"
  >
    <div v-if="loading" class="loading-spinner"></div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import { useScriptApi } from '@/composables/useScriptApi'
import { satelliteModules, centerIconUrl } from '@/composables/satellite-config'
import { useSatelliteStatus } from '@/composables/useSatelliteStatus'
import { requestUpdateCheck } from '@/composables/useUpdateChecker'
import { usePerformanceStore } from '@/stores/performance'
import { connectionState, onConnected } from '@/services/websocket/connection'
import type { ScriptType } from '@/types/script'
import { createCenterPokeCounter } from './satellite/centerPoke'
import { createAnimationFrameScheduler } from './satellite/frameScheduler'
import { SatelliteScene, type SatellitePick } from './satellite-classic/satelliteScene'

/** 主 WS 没开着时，按这个间隔拉运行快照兜底 */
const STATUS_POLL_INTERVAL = 10000
/** 同时在飞的浮字上限；快速连点时先到的先让位，免得 DOM 和合成层无限堆 */
const MAX_STAR_BURSTS = 12

const { t } = useI18n()
const logger = window.electronAPI.getLogger('卫星动画')
const { isDark } = useTheme()
const { getScripts } = useScriptApi()
const performanceStore = usePerformanceStore()
// 卫星状态来自任务运行时常驻订阅（WS 增量 + HTTP 快照兜底）
const {
  statuses: satelliteStatuses,
  setScriptKeys: setSatelliteScriptKeys,
  refresh: refreshSatelliteStatuses,
} = useSatelliteStatus()

const container = ref<HTMLDivElement | null>(null)
const loading = ref(true)
/** 指针停在卫星上时显示手型；中心图标的连点是彩蛋，不提示可点 */
const pointingSatellite = ref(false)

let scene: SatelliteScene | null = null
let isUnmounted = false
let statusPollTimer: ReturnType<typeof setInterval> | null = null
let disposeBackendReadyListener: (() => void) | null = null
const frameScheduler = createAnimationFrameScheduler(requestAnimationFrame, cancelAnimationFrame)
const centerPoke = createCenterPokeCounter()
const activeStarBursts: HTMLSpanElement[] = []

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

  void refreshSatelliteStatuses()
  startStatusPolling()

  // 有新版本时中心光晕换成彩虹
  try {
    const updateRes = await requestUpdateCheck(false)
    if (updateRes.code === 200 && updateRes.if_need_update && !isUnmounted) {
      scene?.setCenterGlowMode('rainbow')
    }
  } catch {
    // 静默失败，保持绿色
  }
})

onUnmounted(() => {
  isUnmounted = true
  disposeBackendReadyListener?.()
  window.removeEventListener('resize', handleResize)
  frameScheduler.cancel()
  stopStatusPolling()
  disposeStarBursts()
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
  // 经典样式一种脚本类型一颗卫星，状态也按类型汇总
  setSatelliteScriptKeys(new Map(userScripts.map(s => [s.uid, s.type])))
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

/** 画一帧。平时逐帧连续画；低性能模式只在有变化时补一帧，碎裂特效放完之前例外 */
function drawFrame(): void {
  if (isUnmounted || !scene || performanceStore.isBackgrounded) return

  const exploding = scene.renderFrame(Date.now())
  if (!performanceStore.isLowPower || exploding) {
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

// ==================== 交互 ====================

function pickAt(event: MouseEvent): SatellitePick {
  if (!scene || performanceStore.isBackgrounded) return null
  return scene.pick(event.clientX, event.clientY)
}

function handlePointerMove(event: PointerEvent): void {
  pointingSatellite.value = typeof pickAt(event) === 'number'
}

function handlePointerLeave(): void {
  pointingSatellite.value = false
  releaseCenter()
}

/** 按在中心图标上时给它一个压扁的形变，松开还原 */
function handlePointerDown(event: PointerEvent): void {
  // 低性能模式下动画循环是停的，按压形变和浮字都不会动，这俩干脆别做；
  // 只认主键，右键 / 中键不会产生 click，冒了字也不算连点
  if (event.button !== 0 || performanceStore.isLowPower || pickAt(event) !== 'center') return
  scene?.setCenterPressed(true)
  spawnStarBurst(event.clientX, event.clientY)
}

function releaseCenter(): void {
  scene?.setCenterPressed(false)
}

function handleClick(event: MouseEvent): void {
  const target = pickAt(event)
  if (target === 'center') {
    registerCenterPoke()
    return
  }
  if (target !== null && scene) {
    scene.explode(target, Date.now())
    requestRender()
  }
}

function registerCenterPoke(): void {
  // 低性能模式下彩虹不会流动，触发了也只是一张静止的图，不给机会
  if (!scene || performanceStore.isLowPower) return

  const hit = centerPoke.poke(performance.now(), scene.isCenterRainbow)
  if (!hit) return
  scene.setCenterRainbow(true)
  logger.info(hit === 'guarantee' ? '中心图标彩蛋触发：连点保底' : '中心图标彩蛋触发：炫彩图标')
}

// ==================== 浮字 ====================

function removeStarBurst(element: HTMLSpanElement): void {
  element.getAnimations().forEach(animation => animation.cancel())
  element.remove()
}

/** 组件销毁时把还在飞的浮字连同动画一起收掉 */
function disposeStarBursts(): void {
  activeStarBursts.forEach(removeStarBurst)
  activeStarBursts.length = 0
}

/** 在点击处冒一句 star！，加速往上方飘走；彩蛋亮起来之后这句字是彩虹色的 */
function spawnStarBurst(clientX: number, clientY: number): void {
  if (!container.value || isUnmounted) return

  const bounds = container.value.getBoundingClientRect()
  const element = document.createElement('span')
  element.className = scene?.isCenterRainbow ? 'star-burst star-burst-rainbow' : 'star-burst'
  element.textContent = t('home.satelliteEgg.star')
  element.style.left = `${clientX - bounds.left}px`
  element.style.top = `${clientY - bounds.top}px`
  container.value.appendChild(element)
  activeStarBursts.push(element)

  while (activeStarBursts.length > MAX_STAR_BURSTS) {
    const oldest = activeStarBursts.shift()
    if (oldest) {
      removeStarBurst(oldest)
    }
  }

  // 左右随机偏一点，整体向上；缓动是强 ease-in，越飞越快
  const driftX = (Math.random() - 0.5) * 90
  const riseY = 220 + Math.random() * 140
  const spin = (Math.random() - 0.5) * 50
  const animation = element.animate(
    [
      { transform: 'translate(-50%, -50%) scale(0.6)', opacity: 0 },
      {
        offset: 0.22,
        transform: `translate(calc(-50% + ${driftX * 0.3}px), calc(-50% - ${riseY * 0.3}px)) scale(1.08) rotate(${spin * 0.35}deg)`,
        opacity: 1,
      },
      {
        transform: `translate(calc(-50% + ${driftX}px), calc(-50% - ${riseY}px)) scale(0.92) rotate(${spin}deg)`,
        opacity: 0,
      },
    ],
    { duration: 1150, easing: 'cubic-bezier(0.5, 0, 1, 1)', fill: 'forwards' }
  )
  animation.onfinish = () => {
    const index = activeStarBursts.indexOf(element)
    if (index >= 0) {
      activeStarBursts.splice(index, 1)
    }
    element.remove()
  }
}
</script>

<style scoped>
.satellite-container {
  width: 100%;
  height: 400px;
  position: relative;
  overflow: hidden;
}

.satellite-container.is-pointing {
  cursor: pointer;
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
