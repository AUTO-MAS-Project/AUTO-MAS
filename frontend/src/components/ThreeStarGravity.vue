<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import {
  getTaskRuntimeStates,
  onTaskRuntimeEvent,
  useTaskRuntimeState,
} from '@/composables/useTaskRuntimeState'
import { connectionState } from '@/services/websocket/connection'
import { usePerformanceStore } from '@/stores/performance'
import { useThreeStarStore } from '@/stores/threeStar'
import { SCRIPT_LABELS, SCRIPT_LOGOS } from '@/utils/scriptLogos'
import type { ScriptType } from '@/types/script'
import { ThreeStarScene, type ProjectedStar } from './three-star/scene'
import { TaskFeedback, runningSpecializations } from './three-star/taskFeedback'
import { DisplayClock } from './three-star/visualState'
import { createAnimationFrameScheduler } from './satellite/frameScheduler'

const { t } = useI18n()
const { isDark } = useTheme()
const performanceStore = usePerformanceStore()
const session = useThreeStarStore()
const { scriptStatusesByType } = useTaskRuntimeState()
const connection = connectionState()
const canvas = ref<HTMLCanvasElement | null>(null)
const root = ref<HTMLDivElement | null>(null)
const fallback = ref(false)
const reducedMotion = ref(false)
const documentHidden = ref(document.hidden)
const inViewport = ref(true)
const reason = ref(session.solver.fault ?? '')
const budgetLimited = ref(false)
const simulationTime = ref(session.solver.time)
const energyError = ref(0)
const labels = shallowRef<ProjectedStar[]>([])
const roles = ['schedule', 'execute', 'feedback'] as const
const activeTypes = computed(() =>
  connection.value === 'open'
    ? runningSpecializations(scriptStatusesByType.value).filter(
        (type): type is ScriptType => type in SCRIPT_LOGOS
      )
    : []
)
const badge = computed(() => activeTypes.value[0])
const effectsPaused = computed(
  () => performanceStore.homeEffectsPaused && !performanceStore.homeEffectsManuallyResumed
)
const staticMode = computed(() => performanceStore.lowPerformanceMode || reducedMotion.value)
const blocked = computed(
  () =>
    staticMode.value ||
    fallback.value ||
    documentHidden.value ||
    !inViewport.value ||
    performanceStore.isBackgrounded ||
    effectsPaused.value ||
    session.userPaused ||
    !!reason.value
)
let scene: ThreeStarScene | null = null
let disposed = false
let initializing = false
let resizeObserver: ResizeObserver | null = null
let intersectionObserver: IntersectionObserver | null = null
let removeTaskListener: (() => void) | null = null
let motionQuery: MediaQueryList | null = null
let lastRenderedAt = 0
let lastUiAt = 0
const frame = createAnimationFrameScheduler(requestAnimationFrame, cancelAnimationFrame)
const clock = new DisplayClock()
const feedback = new TaskFeedback(getTaskRuntimeStates())

watch(isDark, dark => {
  scene?.setDark(dark)
  drawStill()
})
watch(staticMode, value => {
  if (value) {
    stop()
    releaseScene()
  } else void initializeScene()
})
watch(blocked, value => {
  stop()
  if (value) drawStill()
  else {
    session.solver.resume()
    requestFrame()
  }
})
watch(
  [documentHidden, inViewport, () => performanceStore.isBackgrounded],
  ([hidden, visible, background]) => {
    if (hidden || !visible || background) {
      session.userPaused = true
      stop()
    }
  }
)

onMounted(() => {
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion.value = motionQuery.matches
  motionQuery.addEventListener('change', onMotionChange)
  document.addEventListener('visibilitychange', onVisibility)
  canvas.value?.addEventListener('webglcontextlost', onContextLost)
  canvas.value?.addEventListener('webglcontextrestored', onContextRestored)
  resizeObserver = new ResizeObserver(() => {
    try {
      scene?.resize()
      drawStill()
    } catch {
      degrade()
    }
  })
  if (root.value) resizeObserver.observe(root.value)
  intersectionObserver = new IntersectionObserver(entries => {
    inViewport.value = entries.some(entry => entry.isIntersecting)
  })
  if (root.value) intersectionObserver.observe(root.value)
  removeTaskListener = onTaskRuntimeEvent(event => {
    const flash = feedback.consume(event)
    // 暂停期间消耗事件但不排队，恢复时不补播；不从 HTTP 受理推断完成。
    if (flash && !blocked.value && connection.value === 'open') scene?.trigger(flash)
  })
  void initializeScene()
})

onBeforeUnmount(() => {
  disposed = true
  session.userPaused = true
  stop()
  removeTaskListener?.()
  document.removeEventListener('visibilitychange', onVisibility)
  motionQuery?.removeEventListener('change', onMotionChange)
  canvas.value?.removeEventListener('webglcontextlost', onContextLost)
  canvas.value?.removeEventListener('webglcontextrestored', onContextRestored)
  resizeObserver?.disconnect()
  intersectionObserver?.disconnect()
  releaseScene()
})

function stop(): void {
  frame.cancel()
  clock.reset()
  lastRenderedAt = 0
  session.solver.pause()
  try {
    scene?.clearTransient()
  } catch {
    releaseScene()
    fallback.value = true
  }
}
function releaseScene(): void {
  scene?.dispose()
  scene = null
}
function degrade(): void {
  fallback.value = true
  stop()
  releaseScene()
}
async function initializeScene(): Promise<void> {
  if (disposed || staticMode.value || initializing || scene || !canvas.value) return
  initializing = true
  try {
    // 旧 preload / 浏览器没有该能力时，再以 renderer 字符串保守判断。
    const hardware =
      (await window.electronAPI?.getGraphicsAcceleration?.().catch(() => false)) ?? null
    if (disposed || staticMode.value || !canvas.value) return
    scene = new ThreeStarScene(canvas.value, hardware, isDark.value)
    fallback.value = false
    // 降级会隐藏 canvas；等它重新显示后再测量，不能沿用隐藏时的 1×1 尺寸。
    await nextTick()
    if (disposed || staticMode.value || !scene) return
    scene.resize()
    drawStill()
    if (!blocked.value) {
      session.solver.resume()
      requestFrame()
    }
  } catch {
    degrade()
  } finally {
    initializing = false
  }
}
function requestFrame(): void {
  if (!disposed && !blocked.value && scene) frame.request(renderFrame)
}
function renderFrame(now: number): void {
  if (blocked.value || !scene) return
  if (lastRenderedAt && now - lastRenderedAt < 1000 / 30) {
    requestFrame()
    return
  }
  lastRenderedAt = now
  const dt = clock.tick(now)
  try {
    const started = performance.now()
    const result = session.solver.advance(dt * 0.35, 64, () => performance.now() - started > 3)
    budgetLimited.value = result.budgetLimited
    if (session.solver.fault) reason.value = session.solver.fault
    // 只用已接受状态。求解器停下时不再注入或推进流体。
    const projected = scene.render(
      session.solver.snapshot(),
      session.solver.fault ? 0 : dt,
      result.accepted > 0 && !session.solver.fault
    )
    if (now - lastUiAt > 200) {
      labels.value = projected
      simulationTime.value = session.solver.time
      energyError.value = session.solver.diagnostics().energyError
      lastUiAt = now
    }
    requestFrame()
  } catch {
    degrade()
  }
}
function drawStill(): void {
  if (!scene || disposed || documentHidden.value || performanceStore.isBackgrounded) return
  try {
    labels.value = scene.render(session.solver.snapshot())
  } catch {
    degrade()
  }
}
function togglePause(): void {
  if (reason.value || staticMode.value || fallback.value) return
  const resume = blocked.value
  if (effectsPaused.value) performanceStore.homeEffectsManuallyResumed = true
  session.userPaused = !resume
}
function reset(): void {
  stop()
  session.solver.reset()
  session.userPaused = true
  reason.value = ''
  budgetLimited.value = false
  simulationTime.value = 0
  energyError.value = 0
  drawStill()
}
function onVisibility(): void {
  documentHidden.value = document.hidden
}
function onMotionChange(event: MediaQueryListEvent): void {
  reducedMotion.value = event.matches
}
function onContextLost(event: Event): void {
  event.preventDefault()
  session.userPaused = true
  degrade()
}
function onContextRestored(): void {
  if (!disposed) void initializeScene()
}
function pointerMove(event: PointerEvent): void {
  if (!scene || blocked.value || !root.value) return
  const rect = root.value.getBoundingClientRect()
  scene.setPointer(
    (event.clientX - rect.left) / rect.width - 0.5,
    (event.clientY - rect.top) / rect.height - 0.5
  )
}
</script>

<template>
  <div
    ref="root"
    class="three-star"
    @pointermove="pointerMove"
    @pointerleave="scene?.setPointer(0, 0)"
  >
    <div class="three-star-toolbar">
      <span>{{ t('home.threeStar.title') }}</span>
      <a-space size="small">
        <a-button size="small" :disabled="!!reason || staticMode || fallback" @click="togglePause">
          {{ t(blocked ? 'home.threeStar.resume' : 'home.threeStar.pause') }}
        </a-button>
        <a-button size="small" @click="reset">{{ t('home.threeStar.reset') }}</a-button>
      </a-space>
    </div>
    <div class="three-star-stage">
      <canvas
        ref="canvas"
        v-show="!staticMode && !fallback"
        class="three-star-canvas"
        aria-hidden="true"
      />
      <div v-if="staticMode || fallback" class="three-star-static" aria-hidden="true">
        <span v-for="role in roles" :key="role" :class="['static-star', role]" />
      </div>
      <template v-if="!staticMode && !fallback">
        <div
          v-for="(label, i) in labels"
          :key="i"
          class="three-star-label"
          :style="{ left: `${label.x * 100}%`, top: `${label.y * 100}%` }"
        >
          <span
            v-if="label.outside"
            class="three-star-direction"
            :style="{ transform: `rotate(${label.direction}deg)` }"
            >→</span
          >
          <span>{{ t(`home.threeStar.${roles[i]}`) }}</span>
          <span v-if="i === 1 && badge" class="three-star-badge">
            <img :src="SCRIPT_LOGOS[badge]" :alt="SCRIPT_LABELS[badge]" />
            <span v-if="activeTypes.length > 1">＋{{ activeTypes.length - 1 }}</span>
          </span>
        </div>
      </template>
    </div>
    <div class="three-star-caption" role="status" aria-live="polite">
      <span v-if="reason">{{ t(`home.threeStar.${reason}`) }}</span>
      <span v-else-if="staticMode || fallback">{{ t('home.threeStar.static') }}</span>
      <span v-else-if="effectsPaused">{{ t('home.threeStar.taskPaused') }}</span>
      <span v-else-if="session.userPaused">{{ t('home.threeStar.paused') }}</span>
      <span v-else-if="budgetLimited">{{ t('home.threeStar.budget') }}</span>
      <span v-else>{{ t('home.threeStar.fluid') }}</span>
      <span v-if="!staticMode && !fallback" class="three-star-diagnostics" aria-live="off">
        t={{ simulationTime.toFixed(2) }} · ΔE/(K₀+|U₀|)={{ energyError.toExponential(1) }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.three-star {
  position: relative;
  width: 100%;
  overflow: hidden;
  color: var(--ant-color-text);
}
.three-star-toolbar,
.three-star-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 16px;
}
.three-star-toolbar {
  font-size: 14px;
}
.three-star-stage {
  height: 340px;
  position: relative;
  overflow: hidden;
}
.three-star-canvas,
.three-star-static {
  width: 100%;
  height: 100%;
  display: block;
}
.three-star-label {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 4px;
  transform: translate(12px, 12px);
  pointer-events: none;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}
.three-star-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.three-star-direction {
  display: inline-block;
}
.three-star-badge img {
  width: 20px;
  height: 20px;
  object-fit: contain;
}
.three-star-caption {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}
.three-star-diagnostics {
  font-variant-numeric: tabular-nums;
}
.static-star {
  position: absolute;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  box-shadow: 0 0 16px currentColor;
}
.static-star.schedule {
  left: 31%;
  top: 35%;
  color: #c29b49;
  background: radial-gradient(circle at 35% 30%, #fff9e8, #c29b49);
}
.static-star.execute {
  left: 60%;
  top: 40%;
  color: #4b9bbd;
  background: radial-gradient(circle at 35% 30%, #e0f6ff, #4b9bbd);
}
.static-star.feedback {
  left: 46%;
  top: 61%;
  color: #ae5c9c;
  background: radial-gradient(circle at 35% 30%, #ffe3f6, #ae5c9c);
}
</style>
