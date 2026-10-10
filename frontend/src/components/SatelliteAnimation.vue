<template>
  <div
    ref="container"
    class="satellite-container"
    :class="{ 'is-pointing': pointingSatellite, 'is-dragging': dragging, 'is-storm': stormTint }"
    @pointerdown="handlePointerDown"
    @pointermove="handlePointerMove"
    @pointerup="handlePointerUp"
    @pointercancel="cancelPress"
    @pointerleave="handlePointerLeave"
  >
    <div v-if="loading" class="loading-spinner"></div>
    <img v-if="staticImage" class="satellite-static" :src="staticImage" alt="" />
    <SatelliteHoverLabel
      ref="hoverLabel"
      :name="hoveredModule?.label ?? null"
      :status="hoveredStatus"
    />
    <SatelliteFloatLayer ref="floatLayer" />
    <SatelliteEggStage
      ref="eggStage"
      :launcher="!loading && !performanceStore.lowPerformanceMode"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useTheme } from '@/composables/useTheme'
import { useScriptApi } from '@/composables/useScriptApi'
import {
  buildOrbitModules,
  centerIconUrl,
  orbitKeysByScriptId,
  type OrbitModule,
} from '@/composables/satellite-config'
import { useSatelliteStatus } from '@/composables/useSatelliteStatus'
import { requestUpdateCheck } from '@/composables/useUpdateChecker'
import { usePerformanceStore } from '@/stores/performance'
import { connectionState, onConnected } from '@/services/websocket/connection'
import { consumeFirstVisit } from './satellite/eggs'
import type { FloatTextVariant } from './satellite/floatText'
import { createAnimationFrameScheduler } from './satellite/frameScheduler'
import type { CenterGlowMode } from './satellite/motion'
import SatelliteEggStage from './satellite/SatelliteEggStage.vue'
import SatelliteFloatLayer from './satellite/SatelliteFloatLayer.vue'
import SatelliteHoverLabel from './satellite/SatelliteHoverLabel.vue'
import { INTRO_IGNITE_MS, SatelliteScene, type ScreenPoint } from './satellite/satelliteScene'
import { useSatelliteEggs } from './satellite/useSatelliteEggs'
import { useSatellitePointer } from './satellite/useSatellitePointer'
import { useSatelliteStill } from './satellite/useSatelliteStill'
import { playPressSound } from './satellite/pressSound'
import { usePressSoundStore } from '@/stores/pressSound'
import type { PressSoundPhase } from '@/types/pressSound'

/** 主 WS 没开着时，按这个间隔拉运行快照兜底 */
const STATUS_POLL_INTERVAL = 10000

const logger = window.electronAPI.getLogger('卫星动画')
const { isDark } = useTheme()
const { getScripts } = useScriptApi()
const performanceStore = usePerformanceStore()
const pressSoundStore = usePressSoundStore()
void pressSoundStore.load()
// 卫星状态来自任务运行时常驻订阅（WS 增量 + HTTP 快照兜底）
const {
  statuses: satelliteStatuses,
  setScriptKeys: setSatelliteScriptKeys,
  refresh: refreshSatelliteStatuses,
} = useSatelliteStatus()

const container = ref<HTMLDivElement | null>(null)
const hoverLabel = ref<InstanceType<typeof SatelliteHoverLabel> | null>(null)
const eggStage = ref<InstanceType<typeof SatelliteEggStage> | null>(null)
const floatLayer = ref<InstanceType<typeof SatelliteFloatLayer> | null>(null)
const loading = ref(true)
/** 1999 暴雨期间画面泛黄，像老照片 */
const stormTint = ref(false)
/** 指针停在卫星上时显示手型；中心图标的连点是彩蛋，不提示可点 */
const pointingSatellite = ref(false)
const hoveredSatellite = ref<number | null>(null)
const hoveredModule = shallowRef<OrbitModule | null>(null)

/** 实时场景；低性能模式下为 null，所有动画、交互、彩蛋都跟着它一起没有 */
let scene: SatelliteScene | null = null
let liveLoading = false
/** 上轨道的卫星：挂载时按用户建过的脚本算一次 */
let visibleModules: OrbitModule[] | null = null
let centerGlowMode: CenterGlowMode = 'green'
let isUnmounted = false
let statusPollTimer: ReturnType<typeof setInterval> | null = null
let disposeBackendReadyListener: (() => void) | null = null
let lastFrameAt: number | null = null
const frameScheduler = createAnimationFrameScheduler(requestAnimationFrame, cancelAnimationFrame)
/** 低性能模式下只放这张静态图，没有实时场景 */
const {
  image: staticImage,
  render: renderStill,
  schedule: scheduleStill,
  clear: clearStill,
} = useSatelliteStill({
  getContainer: () => container.value,
  getModules: () => visibleModules,
  getStatuses: () => satelliteStatuses.value,
  getCenterGlowMode: () => centerGlowMode,
  isDark: () => isDark.value,
  isWanted: () => !isUnmounted && performanceStore.lowPerformanceMode,
})
const eggs = useSatelliteEggs({
  getScene: () => scene,
  getStage: () => eggStage.value,
  spawnText,
  getContainerSize: () =>
    container.value
      ? { width: container.value.clientWidth, height: container.value.clientHeight }
      : null,
  setStormTint: on => {
    stormTint.value = on
  },
  requestRender,
})
/** 按中心图标时响一下；低性能模式（含窗口切到后台）下装饰性音效一并停掉 */
function playCenterPressSound(): void {
  playSoundAtPhase('press')
}

/** 在中心图标上松手时响一下：内置音效组的按下与松开是两个文件 */
function playCenterReleaseSound(): void {
  playSoundAtPhase('release')
}

function playSoundAtPhase(phase: PressSoundPhase): void {
  if (!pressSoundStore.enabled || performanceStore.isLowPower) {
    return
  }

  void playPressSound(
    pressSoundStore.preset,
    pressSoundStore.volume,
    pressSoundStore.customPath,
    phase
  )
}

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
  isBackgrounded: () => performanceStore.isBackgrounded,
  setHovered,
  spawnText,
  requestRender,
  onCenterTap: eggs.pokeCenter,
  onCenterPress: playCenterPressSound,
  onCenterRelease: playCenterReleaseSound,
  onSatelliteTap: handleSatelliteTap,
  onEmptyPress: eggs.tryCatchMeteor,
})

const hoveredStatus = computed(() =>
  hoveredModule.value ? satelliteStatuses.value.get(hoveredModule.value.key) : undefined
)

// ==================== 监听 ====================

watch(isDark, dark => {
  scene?.setDark(dark)
  requestRender()
  scheduleStill()
})

// 常驻订阅推送新状态时同步刷新展示
watch(satelliteStatuses, statuses => {
  scene?.setStatuses(statuses)
  eggs.onStatusesChange(statuses)
  requestRender()
  scheduleStill()
})

// 低性能模式只留一张静态图：切进去就拆掉实时场景拍一张，切回来再搭实时场景
watch(
  () => performanceStore.lowPerformanceMode,
  () => void applyMode()
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
      scene?.clearEffects()
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
    visibleModules = await loadVisibleModules()
    await applyMode()
  } catch (err) {
    logger.error(`初始化场景失败: ${String(err)}`)
  } finally {
    loading.value = false
  }
  if (isUnmounted) return

  window.addEventListener('resize', handleResize)
  window.addEventListener('keydown', eggs.handleKeydown)

  void refreshSatelliteStatuses()
  startStatusPolling()

  // 有新版本时中心光晕换成彩虹
  try {
    const updateRes = await requestUpdateCheck(false)
    if (updateRes.code === 200 && updateRes.if_need_update && !isUnmounted) {
      centerGlowMode = 'rainbow'
      scene?.setCenterGlowMode('rainbow')
      requestRender()
      scheduleStill()
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
  stopStatusPolling()
  clearStill()
  teardownLive()
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

/** 只有用户建过的脚本才上轨道：每种脚本类型一颗，通用 MFW 每个项目一颗 */
async function loadVisibleModules(): Promise<OrbitModule[]> {
  let userScripts: Awaited<ReturnType<typeof getScripts>> = []
  try {
    userScripts = await getScripts()
  } catch (err) {
    logger.warn(`获取脚本列表失败，按空集合处理: ${String(err)}`)
  }

  const modules = buildOrbitModules(userScripts)
  setSatelliteScriptKeys(orbitKeysByScriptId(modules))
  if (modules.length === 0) {
    logger.info('没有可显示的卫星模块，仅渲染中心图标和轨道')
  }
  return modules
}

/** 按当前性能模式摆出实时场景或静态图 */
async function applyMode(): Promise<void> {
  if (isUnmounted || !visibleModules) return

  if (performanceStore.lowPerformanceMode) {
    teardownLive()
    await renderStill()
    return
  }

  clearStill()
  if (!scene && !liveLoading) {
    await startLive()
  }
}

async function startLive(): Promise<void> {
  if (!container.value || !visibleModules) return

  liveLoading = true
  const created = new SatelliteScene(container.value, { isDark: isDark.value })
  try {
    const loaded = await created.load(
      centerIconUrl,
      visibleModules,
      () => isUnmounted || performanceStore.lowPerformanceMode
    )
    if (!loaded) {
      created.dispose()
      return
    }
  } catch (err) {
    created.dispose()
    throw err
  } finally {
    liveLoading = false
  }

  scene = created
  // 加载图片期间主题、状态可能已经变了，watcher 那时还够不着场景
  scene.setDark(isDark.value)
  scene.setStatuses(satelliteStatuses.value)
  scene.setCenterGlowMode(centerGlowMode)
  // 记下此刻已经在跑的脚本：之后看着它开跑才喊「启动」
  eggs.onStatusesChange(satelliteStatuses.value)

  const now = Date.now()
  if (performanceStore.isBackgrounded) {
    scene.skipAppear()
  } else if (consumeFirstVisit()) {
    // 本次启动应用后第一次进主页：曲速跃迁进场，星核点燃时卫星再甩出来
    scene.startIntro(now)
    scene.startAppear(now + INTRO_IGNITE_MS)
  } else {
    scene.startAppear(now)
  }
  lastFrameAt = null
  requestRender()
}

/** 拆掉实时场景连同它的帧循环、手势、彩蛋和浮字 */
function teardownLive(): void {
  frameScheduler.cancel()
  cancelPress()
  setHovered(null)
  eggs.dispose()
  floatLayer.value?.clear()
  scene?.dispose()
  scene = null
}

/** 实时场景逐帧连续画 */
function drawFrame(): void {
  if (isUnmounted || !scene || performanceStore.isBackgrounded) return

  const now = Date.now()
  // 系统时间被往回调时帧间隔会是负的，按 0 算
  const dt = lastFrameAt === null ? 16 : Math.min(100, Math.max(0, now - lastFrameAt))
  lastFrameAt = now
  updateCoreCharge()
  eggs.checkDizzy(dt, now)

  scene.renderFrame(now)
  updateLabelPosition()
  frameScheduler.request(drawFrame)
}

function requestRender(): void {
  if (isUnmounted || !scene || performanceStore.isBackgrounded) return
  frameScheduler.request(drawFrame)
}

function handleResize(): void {
  scene?.resize()
  requestRender()
  scheduleStill()
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

function setHovered(index: number | null): void {
  if (hoveredSatellite.value === index) return
  hoveredSatellite.value = index
  hoveredModule.value = index === null ? null : (visibleModules?.[index] ?? null)
  pointingSatellite.value = index !== null
  scene?.setHovered(index)
  eggs.onHoverChange(index)
  requestRender()
}

function updateLabelPosition(): void {
  const index = hoveredSatellite.value
  if (index === null || !scene) return
  const point = scene.projectSatellite(index)
  if (point) hoverLabel.value?.moveTo(point)
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
  if (isUnmounted) return
  floatLayer.value?.spawn(point, text, variant)
}
</script>

<style scoped>
.satellite-container {
  width: 100%;
  /* 窗口越宽卫星区域越高：450 起步，宽屏上给星系多一点纵深 */
  height: clamp(450px, 36vw, 580px);
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

/* 1999 暴雨：画面褪成老照片的颜色 */
.satellite-container :deep(canvas) {
  transition: filter 900ms ease;
}

.satellite-container.is-storm :deep(canvas) {
  filter: sepia(0.75) saturate(0.8) contrast(1.05);
}

/* 低性能模式的静态图，和实时画布一样铺满 */
.satellite-static {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
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
</style>
