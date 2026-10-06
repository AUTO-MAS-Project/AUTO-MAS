import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CORE_CHARGE } from './config'
import type { FloatTextVariant } from './floatText'
import type { SatellitePick, SatelliteScene, ScreenPoint } from './satelliteScene'

interface PressState {
  pointerId: number
  target: SatellitePick
  startX: number
  startY: number
  lastX: number
  lastY: number
  lastAt: number
  startedAt: number
  dragging: boolean
}

/** 按下后挪动超过这么多像素就算拖动，不再当点击 */
const DRAG_THRESHOLD = 6

interface SatellitePointerOptions {
  /** 场景还没建好或已经销毁时返回 null */
  getScene: () => SatelliteScene | null
  getContainer: () => HTMLElement | null
  isBackgrounded: () => boolean
  setHovered: (index: number | null) => void
  spawnText: (point: ScreenPoint, text: string, variant: FloatTextVariant) => void
  requestRender: () => void
  /** 在中心图标上短按了一下 */
  onCenterTap: () => void
  /** 点了第 index 颗卫星 */
  onSatelliteTap: (index: number, now: number) => void
  /** 按在空白处：返回 true 表示这一下被用掉了（比如接住了流星），不再当拖动 */
  onEmptyPress: (clientX: number, clientY: number) => boolean
}

/**
 * 卫星区域的指针手势：按住拖动转星系（松手带惯性），点中心图标、点卫星，长按星核蓄力放冲击波。
 * 点击在松手时判定，挪远了就算拖动，不会误触。
 */
export function useSatellitePointer(options: SatellitePointerOptions) {
  const { getScene, getContainer, isBackgrounded, setHovered, requestRender } = options
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('卫星动画')
  const dragging = ref(false)
  let press: PressState | null = null

  function toLocalPoint(event: MouseEvent): ScreenPoint | null {
    const bounds = getContainer()?.getBoundingClientRect()
    if (!bounds) return null
    return { x: event.clientX - bounds.left, y: event.clientY - bounds.top }
  }

  function pickAt(event: MouseEvent): SatellitePick {
    const scene = getScene()
    if (!scene || isBackgrounded()) return null
    return scene.pick(event.clientX, event.clientY)
  }

  function releaseCenter(): void {
    getScene()?.setCenterPressed(false)
    getScene()?.setCoreCharge(0)
  }

  function handlePointerDown(event: PointerEvent): void {
    const scene = getScene()
    if (event.button !== 0 || !scene) return

    // 周哥在场时点哪都是请他回去
    if (scene.isRevealing) {
      scene.dismissZhouge(Date.now())
      return
    }

    const target = pickAt(event)
    if (target === null && options.onEmptyPress(event.clientX, event.clientY)) {
      return
    }
    press = {
      pointerId: event.pointerId,
      target,
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      lastAt: performance.now(),
      startedAt: performance.now(),
      dragging: false,
    }
    getContainer()?.setPointerCapture(event.pointerId)

    // 按在中心图标上时给它一个压扁的形变，再冒一句 star!
    if (target === 'center') {
      scene.setCenterPressed(true)
      const local = toLocalPoint(event)
      if (local) {
        options.spawnText(
          local,
          t('home.satelliteEgg.star'),
          scene.isCenterRainbow ? 'rainbow' : 'star'
        )
      }
    }
    requestRender()
  }

  function handlePointerMove(event: PointerEvent): void {
    const scene = getScene()
    if (!scene) return

    const bounds = getContainer()?.getBoundingClientRect()
    if (bounds && bounds.width > 0) {
      scene.setPointer(
        ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
        1 - ((event.clientY - bounds.top) / bounds.height) * 2
      )
    }

    if (!press || press.pointerId !== event.pointerId) {
      const target = pickAt(event)
      setHovered(typeof target === 'number' ? target : null)
      return
    }

    const now = performance.now()
    if (
      !press.dragging &&
      Math.hypot(event.clientX - press.startX, event.clientY - press.startY) > DRAG_THRESHOLD
    ) {
      // 挪远了就是在拖星系：之前的按压和蓄力都作废
      press.dragging = true
      dragging.value = true
      setHovered(null)
      releaseCenter()
      scene.beginDrag()
    }
    if (press.dragging) {
      scene.dragBy(event.clientX - press.lastX, event.clientY - press.lastY, now - press.lastAt)
      requestRender()
    }
    press.lastX = event.clientX
    press.lastY = event.clientY
    press.lastAt = now
  }

  function handlePointerUp(event: PointerEvent): void {
    const scene = getScene()
    if (!press || press.pointerId !== event.pointerId || !scene) return

    const finished = press
    press = null
    getContainer()?.releasePointerCapture(event.pointerId)
    releaseCenter()

    if (finished.dragging) {
      dragging.value = false
      scene.endDrag()
      requestRender()
      return
    }

    const now = Date.now()
    if (finished.target === 'center') {
      const held = performance.now() - finished.startedAt
      if (held >= CORE_CHARGE.chargeFull) {
        scene.shockwave(now)
        logger.info('卫星彩蛋触发：冲击波')
      } else if (held < CORE_CHARGE.chargeStart) {
        options.onCenterTap()
      }
    } else if (typeof finished.target === 'number') {
      options.onSatelliteTap(finished.target, now)
    }
    requestRender()
  }

  function handlePointerLeave(): void {
    setHovered(null)
    getScene()?.setPointer(0, 0)
  }

  /** 指针被系统收走或页面切到后台：按压、拖动、蓄力全部作废 */
  function cancelPress(): void {
    if (press?.dragging) {
      getScene()?.endDrag()
    }
    press = null
    dragging.value = false
    releaseCenter()
  }

  /** 每帧调用：一直按着星核就蓄力，满了松手放冲击波 */
  function updateCoreCharge(): void {
    const scene = getScene()
    if (!scene || !press || press.dragging || press.target !== 'center') return
    const held = performance.now() - press.startedAt
    scene.setCoreCharge(
      (held - CORE_CHARGE.chargeStart) / (CORE_CHARGE.chargeFull - CORE_CHARGE.chargeStart)
    )
  }

  return {
    dragging,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handlePointerLeave,
    cancelPress,
    updateCoreCharge,
  }
}
