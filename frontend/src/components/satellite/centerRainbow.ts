/**
 * 图标彩虹的色相站：每 10° 一个。段数给少了，相邻色相之间的插值偏色会连成肉眼可见的分界。
 * 每站存偏移比例和色相角，整体加 phase 偏移就成了流动效果。
 */
const ICON_RAINBOW_SEGMENTS = 36
const RAINBOW_HUE_STOPS: ReadonlyArray<readonly [number, number]> = Array.from(
  { length: ICON_RAINBOW_SEGMENTS + 1 },
  (_, index) => {
    const ratio = index / ICON_RAINBOW_SEGMENTS
    return [ratio, ratio * 360] as const
  }
)

/** 彩虹的铺设方向：左上 → 右下 */
const RAINBOW_AXIS_X = Math.SQRT1_2
const RAINBOW_AXIS_Y = Math.SQRT1_2

/** 色相走完一整圈要多久 */
const CENTER_RAINBOW_CYCLE_MS = 1200

/**
 * 重画彩虹的最小间隔。这一步是全画布合成加 36 个色相站再上传纹理，是整套里最贵的，
 * 而色相一圈要 1.2 秒，60fps 下每步才 0.5°，限到约 15fps（每步 2°）视觉上没有区别。
 */
const CENTER_RAINBOW_PAINT_INTERVAL_MS = 66

/** 图标不透明像素在某个方向上的投影范围，用来把彩虹铺在图标真正覆盖的那一段上 */
interface OpaqueExtent {
  min: number
  max: number
}

function getOpaqueExtentAlong(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  axisX: number,
  axisY: number
): OpaqueExtent {
  const fallback: OpaqueExtent = { min: 0, max: width * axisX + height * axisY }
  const { data } = context.getImageData(0, 0, width, height)
  let min = Infinity
  let max = -Infinity
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (data[(y * width + x) * 4 + 3] <= 8) {
        continue
      }
      const projection = x * axisX + y * axisY
      if (projection < min) min = projection
      if (projection > max) max = projection
    }
  }
  return min > max ? fallback : { min, max }
}

/**
 * 把炫彩版画进给定画布：色相换成整条彩虹，原图的明暗关系留着，所以还能认出是哪个图标。
 *
 * 合成分两步，缺一不可——先用 `color` 混合铺彩虹，再拿原图的 alpha 裁回来。
 * 少了第二步，图标外面那圈透明区域会被彩虹矩形整块糊满。
 */
function paintRainbowIcon(
  context: CanvasRenderingContext2D,
  source: HTMLCanvasElement,
  extent: OpaqueExtent,
  phase: number
): void {
  const width = context.canvas.width
  const height = context.canvas.height
  context.globalCompositeOperation = 'source-over'
  context.clearRect(0, 0, width, height)
  context.drawImage(source, 0, 0)

  // 斜着铺，左上到右下。起止点取图标自己的投影范围而不是画布对角线：
  // 这个菱形图标只占对角线中间一段，照着画布铺的话红紫两端会落在空白里看不见。
  const gradient = context.createLinearGradient(
    extent.min * RAINBOW_AXIS_X,
    extent.min * RAINBOW_AXIS_Y,
    extent.max * RAINBOW_AXIS_X,
    extent.max * RAINBOW_AXIS_Y
  )
  // 色相随时间递减，颜色才是沿着左上 → 右下淌；递增的话看过去是从右下往左上跑
  RAINBOW_HUE_STOPS.forEach(([offset, hue]) => {
    const hueAngle = (((hue - phase) % 360) + 360) % 360
    gradient.addColorStop(offset, `hsl(${hueAngle} 95% 64%)`)
  })

  context.globalCompositeOperation = 'color'
  context.fillStyle = gradient
  context.fillRect(0, 0, width, height)
  context.globalCompositeOperation = 'destination-in'
  context.drawImage(source, 0, 0)
  context.globalCompositeOperation = 'source-over'
}

export interface RainbowIcon {
  /** 炫彩版画在这块画布上，复用同一块，每次只重画内容 */
  readonly canvas: HTMLCanvasElement
  /** 到了重画间隔就把色相往前推一点，返回这次是否重画了 */
  paint(now: number): boolean
}

/** 以 source 为底图建炫彩图标；画布拿不到 2D 上下文时返回 null */
export function createRainbowIcon(
  source: HTMLCanvasElement,
  startedAt: number
): RainbowIcon | null {
  const canvas = document.createElement('canvas')
  canvas.width = source.width
  canvas.height = source.height
  const context = canvas.getContext('2d')
  if (!context) {
    return null
  }

  context.drawImage(source, 0, 0)
  const extent = getOpaqueExtentAlong(
    context,
    canvas.width,
    canvas.height,
    RAINBOW_AXIS_X,
    RAINBOW_AXIS_Y
  )
  let lastPaintedAt = 0

  return {
    canvas,
    paint(now) {
      if (now - lastPaintedAt < CENTER_RAINBOW_PAINT_INTERVAL_MS) {
        return false
      }
      lastPaintedAt = now

      const phase = (((now - startedAt) / CENTER_RAINBOW_CYCLE_MS) * 360) % 360
      paintRainbowIcon(context, source, extent, phase)
      return true
    },
  }
}
