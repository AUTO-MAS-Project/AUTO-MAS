import { easeOutCubic } from './motion'

/** 乱飞赛的时间线（毫秒，从拉到榜单开始算） */
export const RACE_TIMELINE = {
  /** 倒数 3、2、1、发射 */
  liftoff: 1800,
  /** 从底下窜进来要多久 */
  entry: 900,
  /** 什么时候开始各自冲出画面 */
  exit: 8600,
  /** 冲出去要多久 */
  exitDuration: 1500,
  /** 整场结束、自己关掉 */
  end: 11000,
} as const

export interface FlightBox {
  left: number
  right: number
  top: number
  bottom: number
}

/** 一枚火箭的乱飞轨迹：两组不同频率的正弦叠出来的绕圈曲线，每枚随机 */
export interface RocketPath {
  /** 飞多快：commit 越多越快 */
  speed: number
  /** 从底下哪里窜出来（0~1，占飞行区宽度的比例） */
  launchAt: number
  x: readonly [number, number, number, number]
  y: readonly [number, number, number, number]
}

export function createRocketPath(
  index: number,
  count: number,
  ratio: number,
  random = Math.random
): RocketPath {
  const between = (min: number, max: number) => min + random() * (max - min)
  return {
    speed: 0.7 + ratio * 0.8,
    launchAt: (index + 0.5) / Math.max(1, count),
    // [主频, 主相位, 副频, 副相位]
    x: [between(0.45, 1), between(0, Math.PI * 2), between(1.3, 2.2), between(0, Math.PI * 2)],
    y: [between(0.55, 1.2), between(0, Math.PI * 2), between(1.4, 2.6), between(0, Math.PI * 2)],
  }
}

function wave(params: readonly [number, number, number, number], t: number): number {
  return 0.68 * Math.sin(params[0] * t + params[1]) + 0.32 * Math.sin(params[2] * t + params[3])
}

/** 乱飞阶段 t 秒（已乘速度）时在飞行区里的位置 */
function cruise(path: RocketPath, box: FlightBox, t: number): { x: number; y: number } {
  const cx = (box.left + box.right) / 2
  const cy = (box.top + box.bottom) / 2
  return {
    x: cx + ((box.right - box.left) / 2) * wave(path.x, t),
    y: cy + ((box.bottom - box.top) / 2) * wave(path.y, t),
  }
}

export interface RocketPose {
  x: number
  y: number
  /** 机头朝向（度）：0 朝上，顺时针为正 */
  angle: number
  /** 还在画面里 */
  visible: boolean
}

/**
 * elapsed 毫秒（从拉到榜单开始算）时火箭的位姿：倒数期间藏在底下，点火后从底下窜进来，
 * 满场乱飞，最后顺着当时的方向加速冲出去。
 */
export function getRocketPose(path: RocketPath, box: FlightBox, elapsed: number): RocketPose {
  const flight = elapsed - RACE_TIMELINE.liftoff
  if (flight < 0) {
    return {
      x: box.left + (box.right - box.left) * path.launchAt,
      y: box.bottom + 140,
      angle: 0,
      visible: false,
    }
  }

  const position = (ms: number) => {
    const point = cruise(path, box, (ms / 1000) * path.speed)
    if (ms < RACE_TIMELINE.entry) {
      // 从底下的发射点渐渐并入乱飞轨迹
      const k = easeOutCubic(Math.max(0, ms) / RACE_TIMELINE.entry)
      const startX = box.left + (box.right - box.left) * path.launchAt
      point.x = startX + (point.x - startX) * k
      point.y = box.bottom + 140 + (point.y - box.bottom - 140) * k
    }
    return point
  }

  // 冲出阶段停在乱飞结束那一刻的位置上，再沿着那一刻的方向飞走
  const cruiseEnd = RACE_TIMELINE.exit - RACE_TIMELINE.liftoff
  const t = Math.min(flight, cruiseEnd)
  const here = position(t)
  const before = position(t - 30)
  const dx = here.x - before.x
  const dy = here.y - before.y
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI + 90

  const exiting = elapsed - RACE_TIMELINE.exit
  if (exiting > 0) {
    const k = exiting / RACE_TIMELINE.exitDuration
    const length = Math.hypot(dx, dy) || 1
    const distance = k * k * 1600
    return {
      x: here.x + (dx / length) * distance,
      y: here.y + (dy / length) * distance,
      angle,
      visible: k < 1,
    }
  }
  return { x: here.x, y: here.y, angle, visible: true }
}
