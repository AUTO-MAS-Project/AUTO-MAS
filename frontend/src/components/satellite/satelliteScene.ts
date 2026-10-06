import * as THREE from 'three'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import type { SatelliteModuleStatus } from '@/composables/useSatelliteStatus'
import type { ScriptType } from '@/types/script'
import { createRainbowIcon, type RainbowIcon } from './centerRainbow'
import {
  CENTER_PRESS_SCALE_X,
  CENTER_PRESS_SCALE_Y,
  ORBIT_RINGS,
  SATELLITE_COLORS,
  SATELLITE_CONFIG as C,
} from './config'
import { isAprilFools } from './eggs'
import { SatelliteExplosion } from './explosionEffect'
import { FxDirector } from './fxDirector'
import {
  easeOutBack,
  easeOutCubic,
  getActivityGlow,
  getAppearDuration,
  getAppearProgress,
  getCenterFloat,
  getCenterGlow,
  getErrorGlow,
  getKnockback,
  getRingBasis,
  getRingPoint,
  getRingSpeed,
  getSatelliteFloat,
  getSatelliteSlot,
  getStatusKind,
  getTrailStatusColor,
  type CenterGlowMode,
  type SatelliteSlot,
} from './motion'
import {
  applyGlow,
  createCanvasTexture,
  createCoreShell,
  createCoreSwirl,
  createGlowSprite,
  createGyroRing,
  createOrbitLine,
  createPointCloud,
  createSatelliteTile,
  createStarfield,
  disposeObject,
  loadImageToCanvas,
  RENDER_ORDER,
  type PointCloud,
  type SatelliteTile,
} from './sceneParts'
import { createBadgeTextures, SatelliteDecor, type StatusTextures } from './statusDecor'
import {
  createGlowTexture,
  createNebulaTexture,
  createRaysTexture,
  createShockwaveTexture,
} from './textures'
import { createZhougeFaceCanvas } from './zhougeFace'
import { ZhougeReveal } from './zhougeReveal'

// ==================== 类型定义 ====================

type IconMesh = THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>

interface Satellite extends SatelliteTile {
  /** 卫星键，运行状态按它取 */
  key: string
  type: ScriptType
  label: string
  iconCanvas: HTMLCanvasElement
  slot: SatelliteSlot
  activityGlow: THREE.Sprite
  errorGlow: THREE.Sprite
  /** 点一下冒的青色闪光 */
  pingGlow: THREE.Sprite
  /** 光芒、进度弧、警示环、徽标 */
  decor: SatelliteDecor
  status: SatelliteModuleStatus
  explosion: SatelliteExplosion | null
  /** 本帧在轨道上的角度和半径，彗尾沿着它往回画 */
  angle: number
  radius: number
  /** 离镜头的远近换算出的透明度系数，远的暗一些 */
  fade: number
  hover: number
  punchAt: number
  pingAt: number
}

export interface SatelliteSceneModule {
  /** 卫星键：一般就是脚本类型，通用 MFW 每个项目一颗 */
  key: string
  scriptType: ScriptType
  label: string
  iconUrl: string
  /** iconUrl 加载不出来时换用的图标 */
  fallbackIconUrl?: string
}

/** 指针下是什么：中心图标、第几颗卫星，或者什么都没点到 */
export type SatellitePick = 'center' | number | null

export interface ScreenPoint {
  x: number
  y: number
}

const IDLE_STATUS: SatelliteModuleStatus = { queued: false, running: false, lastFailed: false }

const OVERCLOCK_MS = 10000
const DIZZY_MS = 4200
const SHOCKWAVE_MS = 1100
const PUNCH_MS = 650
const PING_MS = 380
/** 松手惯性的转速上限，弧度/毫秒 */
const MAX_SPIN = 0.018
/** 停手多久后镜头开始转回正面 */
const AZIMUTH_RETURN_DELAY = 3500
/** 松手前最后一次挪动在这么久以内，才算甩出去 */
const FLING_WINDOW = 80
/** 入场跃迁：多久后星核点燃、卫星甩出来；镜头从多远推进来 */
export const INTRO_IGNITE_MS = 1300
const INTRO_DOLLY_MS = 1800
const INTRO_DOLLY_FROM = 3.4
const STORM_MS = 6500
const VANISH_MS = 3000
const CORE_FLASH_MS = 1400

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}

/** 渐入、保持、渐出的包络，返回 0~1 */
function envelope(elapsed: number, duration: number, rampIn: number, rampOut: number): number {
  if (elapsed < 0 || elapsed > duration) return 0
  return Math.min(1, elapsed / rampIn, (duration - elapsed) / rampOut)
}

// ==================== 场景 ====================

/**
 * 主页卫星的 three.js 场景：中心是 AUTO-MAS 图标和一颗全息星核，脚本卫星沿三条倾斜的轨道
 * 绕着它转，拖着彗尾。轨道线不写深度、排在卫星之前画，所以永远压在卫星下面。
 */
export class SatelliteScene {
  private readonly host: HTMLElement
  private isDark: boolean
  private renderer: THREE.WebGLRenderer
  private environment: THREE.WebGLRenderTarget | null = null
  private readonly scene = new THREE.Scene()
  private readonly camera: THREE.PerspectiveCamera
  private cameraDistance: number = C.cameraDistance
  /** 本帧镜头到星核的实际距离：入场推镜头时比 cameraDistance 远 */
  private viewDistance: number = C.cameraDistance
  private readonly raycaster = new THREE.Raycaster()
  private readonly pointer = new THREE.Vector2()
  private readonly glowTexture = createGlowTexture()
  private readonly raysTexture = createRaysTexture()
  private readonly statusTextures: StatusTextures = {
    rays: this.raysTexture,
    glow: this.glowTexture,
    badges: createBadgeTextures(),
  }
  private readonly fx: FxDirector

  private readonly stars = createStarfield()
  /** 星核背后一圈慢慢转的光芒 */
  private readonly coreRays: THREE.Sprite
  /** 深色主题下远处的几团星云 */
  private readonly nebula: THREE.Sprite[]
  private readonly swirl = createCoreSwirl()
  private readonly shell = createCoreShell()
  private readonly gyroRings = [createGyroRing(104, 0.9), createGyroRing(122, 0.6)]
  private readonly orbitLines = ORBIT_RINGS.map(createOrbitLine)
  private readonly ringBases = ORBIT_RINGS.map(getRingBasis)
  private readonly ringSpeeds = ORBIT_RINGS.map(getRingSpeed)
  private readonly coreGlow: THREE.Sprite
  private shockwaveRing: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial> | null = null
  private trails: PointCloud | null = null

  private satellites: Satellite[] = []
  private centerCard: IconMesh | null = null
  /** 中心图标原图；炫彩版以它为底，关掉炫彩时也从它还原，不用重新加载 */
  private centerIconCanvas: HTMLCanvasElement | null = null
  private centerRainbow: RainbowIcon | null = null
  private centerGlowMode: CenterGlowMode = 'green'
  private centerPressed = false
  private centerScaleX = 1
  private centerScaleY = 1
  /** 入场动画的起点；null 表示不在入场中 */
  private appearStartedAt: number | null = null

  private lastTime: number | null = null
  /** 轨道相位累加值：超频时转得快，不能直接用时间乘角速度 */
  private orbitPhase = 0
  private azimuth = 0
  private elevation: number = C.cameraElevation
  /** 拖动松手后的方位角速度，弧度/毫秒 */
  private spinVelocity = 0
  private previousAzimuth = 0
  private azimuthRate = 0
  private lastDragAt = -Infinity
  private lastDragMoveAt = 0
  private dragging = false
  private readonly parallax = new THREE.Vector2()
  private readonly parallaxTarget = new THREE.Vector2()
  private hovered: number | null = null

  /** 愚人节：倒着转、图标倒过来 */
  private readonly reversed = isAprilFools(new Date())
  private overclockAt = -Infinity
  private dizzyAt = -Infinity
  private charge = 0
  private shockwaveAt = -Infinity
  private shockwaveColor: number = SATELLITE_COLORS.explosionFlash
  private coreFlashAt = -Infinity
  private readonly coreFlashColor = new THREE.Color()
  private introAt = -Infinity
  private stormAt = -Infinity
  private vanishAt = -Infinity
  private reveal: { effect: ZhougeReveal; satellite: number } | null = null
  private revealPending = false
  private disposed = false

  private readonly tmpVector = new THREE.Vector3()
  private readonly tmpEuler = new THREE.Euler()
  private readonly tmpQuaternion = new THREE.Quaternion()
  private readonly tmpColor = new THREE.Color()

  constructor(host: HTMLElement, options: { isDark: boolean }) {
    this.host = host
    this.isDark = options.isDark

    this.camera = new THREE.PerspectiveCamera(C.cameraFov, 1, 1, 6000)
    this.renderer = this.createRenderer()
    this.applyEnvironment()

    this.coreGlow = createGlowSprite(this.glowTexture, RENDER_ORDER.coreGlow)
    this.coreRays = createGlowSprite(this.raysTexture, RENDER_ORDER.coreGlow)
    this.coreRays.scale.setScalar(560)
    this.nebula = [200, 265, 300, 175, 325].map((hue, index) => {
      const cloud = createGlowSprite(createNebulaTexture(hue), RENDER_ORDER.stars)
      const angle = (index / 5) * Math.PI * 2 + 0.4
      cloud.position.set(
        Math.cos(angle) * 1500,
        (Math.random() - 0.5) * 900,
        -1700 - Math.random() * 600
      )
      cloud.scale.setScalar(1300 + Math.random() * 800)
      cloud.material.rotation = Math.random() * Math.PI * 2
      // 只当远景的一点颜色，浓了会抢卫星的戏
      cloud.material.opacity = 0.3
      return cloud
    })
    this.gyroRings[0].rotation.set(1.2, 0.3, 0)
    this.gyroRings[1].rotation.set(0.4, -0.9, 0.5)
    // 镜头也挂进场景：曲速线、雨幕、流星是镜头空间里的东西，要跟着镜头走
    this.scene.add(
      this.camera,
      this.stars.points,
      ...this.nebula,
      this.swirl.points,
      this.shell,
      this.coreRays,
      this.coreGlow,
      ...this.gyroRings,
      ...this.orbitLines
    )
    this.fx = new FxDirector(this.scene, this.camera, {
      glow: this.glowTexture,
      rays: this.raysTexture,
    })

    this.setDark(options.isDark)
    this.resize()
  }

  /** 加载中心图标和各卫星的图片；加载期间 isCancelled 变真就返回 false，场景交给调用方销毁 */
  async load(
    centerIconUrl: string,
    modules: readonly SatelliteSceneModule[],
    isCancelled: () => boolean
  ): Promise<boolean> {
    const [centerCanvas, ...iconCanvases] = await Promise.all([
      loadImageToCanvas(centerIconUrl),
      ...modules.map(module => loadImageToCanvas(module.iconUrl, module.fallbackIconUrl)),
    ])
    if (isCancelled()) {
      return false
    }

    const center = new THREE.Mesh(
      new THREE.PlaneGeometry(C.centerCardSize, C.centerCardSize),
      new THREE.MeshBasicMaterial({
        map: createCanvasTexture(centerCanvas),
        transparent: true,
        opacity: 0,
        // 图标外围全透明的地方不写深度，绕到背后的卫星和轨道按图标轮廓被挡住；
        // 阈值压得很低，半透明的抗锯齿边照样画出来，边缘不发硬
        alphaTest: 0.05,
      })
    )
    center.renderOrder = RENDER_ORDER.coreIcon
    center.scale.setScalar(0.001)
    this.centerCard = center
    this.centerIconCanvas = centerCanvas
    this.scene.add(center)

    this.satellites = iconCanvases.map((iconCanvas, index) => {
      const tile = createSatelliteTile(iconCanvas)
      tile.body.material.color.setHex(this.tileColor)
      const satellite: Satellite = {
        ...tile,
        key: modules[index].key,
        type: modules[index].scriptType,
        label: modules[index].label,
        iconCanvas,
        slot: getSatelliteSlot(index, modules.length),
        activityGlow: createGlowSprite(this.glowTexture, RENDER_ORDER.satelliteGlow),
        errorGlow: createGlowSprite(this.glowTexture, RENDER_ORDER.satelliteGlow),
        pingGlow: createGlowSprite(this.glowTexture, RENDER_ORDER.effect),
        decor: new SatelliteDecor(this.scene, this.statusTextures),
        status: IDLE_STATUS,
        explosion: null,
        angle: 0,
        radius: 0,
        fade: 0,
        hover: 0,
        punchAt: -Infinity,
        pingAt: -Infinity,
      }
      satellite.pingGlow.material.color.setHex(SATELLITE_COLORS.explosionFlash)
      this.scene.add(tile.root, satellite.activityGlow, satellite.errorGlow, satellite.pingGlow)
      return satellite
    })

    if (this.satellites.length > 0) {
      this.trails = createPointCloud(this.satellites.length * C.trailLength, RENDER_ORDER.trail)
      this.scene.add(this.trails.points)
    }
    this.syncPixelRatio()
    return true
  }

  // ==================== 状态 ====================

  setDark(isDark: boolean): void {
    this.isDark = isDark
    // 星空、星云只在深色主题下有意义，浅色背景上就是一片灰点
    this.stars.points.visible = isDark
    for (const cloud of this.nebula) {
      cloud.visible = isDark
    }
    const orbitColor = isDark ? SATELLITE_COLORS.orbitDark : SATELLITE_COLORS.orbitLight
    for (const line of this.orbitLines) {
      line.material.uniforms.uColor.value.setHex(orbitColor)
      line.material.uniforms.uOpacity.value = isDark ? 1 : 0.85
    }
    for (const ring of this.gyroRings) {
      ring.material.color.setHex(isDark ? SATELLITE_COLORS.gyroDark : SATELLITE_COLORS.gyroLight)
    }
    for (const satellite of this.satellites) {
      satellite.body.material.color.setHex(this.tileColor)
    }
  }

  setStatuses(statuses: ReadonlyMap<string, SatelliteModuleStatus>): void {
    for (const satellite of this.satellites) {
      satellite.status = statuses.get(satellite.key) ?? IDLE_STATUS
    }
  }

  setCenterGlowMode(mode: CenterGlowMode): void {
    this.centerGlowMode = mode
  }

  setCenterPressed(pressed: boolean): void {
    this.centerPressed = pressed
  }

  /** 松开并立即复原形变，不走平滑逼近 */
  resetCenterPress(): void {
    this.centerPressed = false
    this.centerScaleX = 1
    this.centerScaleY = 1
    this.charge = 0
  }

  get isCenterRainbow(): boolean {
    return this.centerRainbow !== null
  }

  /** 中心图标的正面贴图在炫彩版和原图之间切换 */
  setCenterRainbow(rainbow: boolean): void {
    const material = this.centerCard?.material
    if (!material?.map || !this.centerIconCanvas || this.isCenterRainbow === rainbow) {
      return
    }

    let texture: THREE.CanvasTexture
    if (rainbow) {
      const icon = createRainbowIcon(this.centerIconCanvas, performance.now())
      if (!icon) {
        return
      }
      this.centerRainbow = icon
      texture = createCanvasTexture(icon.canvas)
    } else {
      // 炫彩用的画布随贴图一起丢掉，下次触发再建
      this.centerRainbow = null
      texture = createCanvasTexture(this.centerIconCanvas)
    }

    material.map.dispose()
    material.map = texture
    material.needsUpdate = true
  }

  startAppear(time: number): void {
    this.appearStartedAt = time
  }

  /** 入场到此为止，所有卡片直接显示完整 */
  skipAppear(): void {
    this.appearStartedAt = null
    if (this.centerCard) {
      this.centerCard.material.opacity = 1
      this.centerCard.scale.set(this.centerScaleX, this.centerScaleY, 1)
    }
  }

  // ==================== 交互 ====================

  pick(clientX: number, clientY: number): SatellitePick {
    if (!this.setRayFromClient(clientX, clientY)) {
      return null
    }

    const bodies = this.satellites.map(satellite => satellite.body)
    const targets: THREE.Object3D[] = this.centerCard ? [this.centerCard, ...bodies] : bodies
    // 取最近的命中：卫星从星核前面经过时点的是卫星
    const hit = this.raycaster.intersectObjects(targets, false)[0]
    if (!hit) {
      return null
    }
    if (hit.object === this.centerCard) {
      return 'center'
    }

    const index = bodies.indexOf(hit.object as SatelliteTile['body'])
    // 入场还没长出来的卫星不算点中；炸开期间照样能点，方便连点计数
    return this.satellites[index].root.scale.x > 0.05 ? index : null
  }

  setHovered(index: number | null): void {
    this.hovered = index
  }

  /** 指针在容器里的归一化坐标（-1~1），镜头跟着轻轻偏转；拖出容器外的按边缘算 */
  setPointer(x: number, y: number): void {
    this.parallaxTarget.set(THREE.MathUtils.clamp(x, -1, 1), THREE.MathUtils.clamp(y, -1, 1))
  }

  beginDrag(): void {
    this.dragging = true
    this.spinVelocity = 0
  }

  /** 拖动转镜头：横向转方位角，纵向调俯仰角；dt 用来估松手后的惯性 */
  dragBy(dx: number, dy: number, dt: number): void {
    const delta = (-dx / Math.max(1, this.host.clientWidth)) * Math.PI * 1.6
    this.azimuth += delta
    this.elevation = THREE.MathUtils.clamp(
      this.elevation + (dy / this.height) * 0.9,
      C.cameraElevationMin,
      C.cameraElevationMax
    )
    if (dt > 0) {
      // 甩得再猛，松手后也就转个两三圈
      const velocity = THREE.MathUtils.clamp(delta / dt, -MAX_SPIN, MAX_SPIN)
      this.spinVelocity += (velocity - this.spinVelocity) * 0.5
    }
    this.lastDragMoveAt = performance.now()
  }

  endDrag(): void {
    this.dragging = false
    this.lastDragAt = this.lastTime ?? 0
    // 拖到一半停住再松手不该甩出去：离最后一次挪动隔久了就当没有惯性
    if (performance.now() - this.lastDragMoveAt > FLING_WINDOW) {
      this.spinVelocity = 0
    }
  }

  /** 镜头上一帧实际转过的速度（弧度/秒，不分方向），给转晕检测用；来回猛搓也算 */
  get spinSpeed(): number {
    return this.azimuthRate
  }

  /** 炸开一颗卫星；正在炸的不重复炸，返回这次有没有炸 */
  explode(index: number, time: number): boolean {
    const satellite = this.satellites[index]
    if (!satellite || satellite.explosion) {
      return false
    }

    satellite.explosion = new SatelliteExplosion({
      card: satellite.root,
      source: satellite.iconCanvas,
      seed: index + 17,
      glowTexture: this.glowTexture,
      scene: this.scene,
      startTime: time,
    })
    this.setSatelliteVisible(satellite, false)
    return true
  }

  /** 点一下的小闪光；卫星没炸开时再顺带弹一下、翻个面 */
  ping(index: number, time: number): void {
    const satellite = this.satellites[index]
    if (!satellite) return
    satellite.pingAt = time
    if (!satellite.explosion) {
      satellite.punchAt = time
    }
  }

  clearExplosions(): void {
    this.satellites.forEach(satellite => this.finishExplosion(satellite))
  }

  /** 长按星核的蓄力程度（0~1） */
  setCoreCharge(level: number): void {
    this.charge = clamp01(level)
  }

  /** 星核放冲击波：卫星被震开再弹回轨道，顺便都翻个面；color 是光环颜色 */
  shockwave(time: number, color: number = SATELLITE_COLORS.explosionFlash): void {
    this.shockwaveAt = time
    this.shockwaveColor = color
    this.charge = 0
    for (const satellite of this.satellites) {
      satellite.punchAt = time + satellite.slot.ring * 60
    }
  }

  /** 收掉所有在放的特效和流星（切后台时） */
  clearEffects(): void {
    this.fx.clear()
    this.stormAt = -Infinity
    this.vanishAt = -Infinity
  }

  /**
   * 入场曲速跃迁：星光拉成线迎面冲过来、镜头从远处推近，INTRO_IGNITE_MS 时星核点燃。
   * 卫星的入场由调用方按点燃时间安排。
   */
  startIntro(time: number): void {
    this.introAt = time
    this.fx.warp(time)
    this.shockwave(time + INTRO_IGNITE_MS)
    this.flashCore(time + INTRO_IGNITE_MS, SATELLITE_COLORS.explosionFlash)
  }

  /** 攒满保底：金色流星砸中第 index 颗卫星，冲击波、金粉、星核一起亮 */
  playGoldPull(index: number, time: number, color: number, rainbow: boolean): void {
    const satellite = this.satellites[index]
    if (!satellite) return
    this.fx.goldPull({
      time,
      color,
      rainbow,
      pixelRatio: this.renderer.getPixelRatio(),
      getTarget: () => satellite.root.position,
      onImpact: impactAt => {
        this.shockwave(impactAt, color)
        this.flashCore(impactAt, color)
        satellite.pingAt = impactAt
      },
    })
  }

  /** 1999：暴雨降临，时间倒流——雨幕落下，卫星倒着转 */
  startStorm(time: number): void {
    this.stormAt = time
    this.fx.rain(time, STORM_MS)
  }

  /** 404：卫星集体闪烁着消失，过一会儿再弹回来 */
  vanish(time: number): void {
    this.vanishAt = time
  }

  playCrystalRain(time: number): void {
    this.fx.crystalRain(time)
    this.flashCore(time, 0xffd36b)
  }

  playHearts(time: number): void {
    this.fx.hearts(time)
  }

  playFireworks(time: number): void {
    this.fx.fireworks(time, this.renderer.getPixelRatio())
  }

  /** 点中背景里的流星就接住它，返回它在容器里的位置；没点中返回 null */
  catchMeteor(clientX: number, clientY: number, time: number): ScreenPoint | null {
    const bounds = this.renderer.domElement.getBoundingClientRect()
    const pointer = { x: clientX - bounds.left, y: clientY - bounds.top }
    const head = this.fx.catchMeteor(
      pointer,
      world => this.project(world),
      time,
      this.renderer.getPixelRatio()
    )
    return head ? this.project(head) : null
  }

  /**
   * 低性能模式用的静态图：按 time 摆好画一帧，导出成透明底的图片。调用方拿到图就把整个
   * 场景销毁，页面上只留这张图——不跑动画、不占着 WebGL。
   */
  renderStill(time: number): string {
    this.renderFrame(time)
    return this.renderer.domElement.toDataURL('image/png')
  }

  /**
   * 给当前画面拍一张照片（三月七的相册）：重画一帧后立刻读画布——画布不保留绘制缓冲，
   * 不在同一个任务里读就是一片空白。底色按主题铺，免得透明背景在相纸上发灰。
   */
  captureSnapshot(): string | null {
    this.renderer.render(this.scene, this.camera)
    const source = this.renderer.domElement
    const canvas = document.createElement('canvas')
    canvas.width = source.width
    canvas.height = source.height
    const context = canvas.getContext('2d')
    if (!context) return null
    context.fillStyle = this.isDark ? '#0b0f17' : '#f4f6fb'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(source, 0, 0)
    return canvas.toDataURL('image/jpeg', 0.86)
  }

  startOverclock(time: number): void {
    this.overclockAt = time
  }

  startDizzy(time: number): void {
    this.dizzyAt = time
  }

  /** 周哥的脸还在画面上；脸缩回去之后彩纸还会落一会儿，那时点击照常响应 */
  get isRevealing(): boolean {
    return this.revealPending || (this.reveal?.effect.faceShowing ?? false)
  }

  /** 周哥从第 index 颗卫星里出场；脸要先画好，所以是异步的 */
  async revealZhouge(index: number): Promise<void> {
    if (this.isRevealing) return
    this.revealPending = true
    const faceCanvas = await createZhougeFaceCanvas()
    this.revealPending = false
    if (this.disposed) return

    // 上一场的彩纸还没落完就直接收掉
    this.reveal?.effect.dispose()
    const now = Date.now()
    const effect = new ZhougeReveal(this.scene, faceCanvas, now, this.renderer.getPixelRatio())
    this.reveal = { effect, satellite: index }
    this.shockwave(now)
  }

  dismissZhouge(time: number): void {
    this.reveal?.effect.dismiss(time)
  }

  satelliteType(index: number): ScriptType | null {
    return this.satellites[index]?.type ?? null
  }

  satelliteLabel(index: number): string | null {
    return this.satellites[index]?.label ?? null
  }

  /** 这个卫星键的卫星是第几颗；没上轨道返回 null */
  findSatellite(key: string): number | null {
    const index = this.satellites.findIndex(satellite => satellite.key === key)
    return index < 0 ? null : index
  }

  projectSatellite(index: number): ScreenPoint | null {
    const satellite = this.satellites[index]
    return satellite ? this.project(satellite.root.position) : null
  }

  projectCenter(): ScreenPoint {
    return this.project(this.centerCard?.position ?? this.tmpVector.set(0, 0, 0))
  }

  // ==================== 渲染 ====================

  /** 推进到 time 时刻并画一帧 */
  renderFrame(time: number): void {
    const dt = this.lastTime === null ? 16 : Math.min(50, Math.max(0, time - this.lastTime))
    this.lastTime = time

    const overclock = envelope(time - this.overclockAt, OVERCLOCK_MS, 500, 1500)
    const dizzy = envelope(time - this.dizzyAt, DIZZY_MS, 300, 1500)
    const knock = getKnockback(time - this.shockwaveAt)
    // 暴雨里时间倒流：轨道慢慢停下、再倒着转
    const storm = envelope(time - this.stormAt, STORM_MS, 900, 1400)
    const direction = (this.reversed ? -1 : 1) * (1 - 2.6 * storm)
    this.orbitPhase += dt * C.orbitSpeed * (1 + 5 * overclock) * direction

    this.updateCamera(time, dt, overclock)
    this.azimuthRate = dt > 0 ? (Math.abs(this.azimuth - this.previousAzimuth) / dt) * 1000 : 0
    this.previousAzimuth = this.azimuth
    const count = this.satellites.length

    let appearElapsed = this.appearStartedAt === null ? null : time - this.appearStartedAt
    if (appearElapsed !== null && appearElapsed > getAppearDuration(count)) {
      this.skipAppear()
      appearElapsed = null
    }

    this.satellites.forEach((satellite, index) =>
      this.updateSatellite(satellite, index, time, dt, appearElapsed, knock, dizzy)
    )
    const centerY = this.updateCore(time, dt, appearElapsed, overclock)
    this.updateTrails(time, overclock, direction)

    for (const cloud of this.nebula) {
      cloud.material.rotation += dt * 0.000012
    }

    for (const line of this.orbitLines) {
      const { uniforms } = line.material
      uniforms.uTime.value = time
      uniforms.uCenterDepth.value = -this.viewDistance
      uniforms.uFlow.value = 1 + 6 * overclock
    }
    this.stars.points.material.uniforms.uTime.value = time
    this.stars.points.rotation.y += dt * 0.000006

    for (const satellite of this.satellites) {
      if (satellite.explosion?.update(time)) {
        this.finishExplosion(satellite)
      }
    }
    this.updateShockwave(time, centerY)
    this.updateReveal(time)
    // 流星只在深色主题、不在入场时出
    this.fx.update(time, this.isDark && time - this.introAt >= INTRO_DOLLY_MS)

    this.renderer.render(this.scene, this.camera)
  }

  resize(): void {
    const width = this.host.clientWidth
    if (width <= 0) {
      return
    }

    const aspect = width / this.height
    const halfFov = Math.tan(THREE.MathUtils.degToRad(C.cameraFov / 2))
    // 主轨道左右两端加一颗卫星的余量都要在画面里，窄容器就把镜头拉远
    this.cameraDistance = Math.max(
      C.cameraDistance,
      (ORBIT_RINGS[0].radius + C.satelliteSize * 1.4) / (halfFov * aspect)
    )
    this.camera.aspect = aspect
    this.camera.updateProjectionMatrix()
    this.renderer.setPixelRatio(this.pixelRatio)
    this.renderer.setSize(width, this.height)
    this.syncPixelRatio()
  }

  dispose(): void {
    this.disposed = true
    this.clearExplosions()
    this.fx.clear()
    this.reveal?.effect.dispose()
    this.reveal = null
    disposeObject(this.scene)
    this.scene.clear()
    this.glowTexture.dispose()
    this.environment?.dispose()
    this.environment = null
    this.disposeRenderer()
    this.satellites = []
    this.centerCard = null
    this.centerIconCanvas = null
    this.centerRainbow = null
    this.trails = null
  }

  // ==================== 每帧更新 ====================

  private updateCamera(time: number, dt: number, overclock: number): void {
    if (!this.dragging) {
      this.azimuth += this.spinVelocity * dt
      this.spinVelocity *= Math.exp(-dt / 700)
      if (Math.abs(this.spinVelocity) < 0.00002) this.spinVelocity = 0

      // 停手一会儿后俯仰角回到默认、慢慢转回正面：默认构图是按正面摆的
      this.elevation += (C.cameraElevation - this.elevation) * (1 - Math.exp(-dt / 1600))
      const front = Math.round(this.azimuth / (Math.PI * 2)) * Math.PI * 2
      if (this.spinVelocity === 0 && time - this.lastDragAt > AZIMUTH_RETURN_DELAY) {
        this.azimuth += (front - this.azimuth) * (1 - Math.exp(-dt / 1400))
      }
    }
    this.parallax.lerp(this.parallaxTarget, 1 - Math.exp(-dt / 220))

    const sway = Math.sin(time * 0.00011) * 0.05
    const yaw = this.azimuth + this.parallax.x * C.parallaxYaw + sway
    const pitch = THREE.MathUtils.clamp(
      this.elevation + this.parallax.y * C.parallaxPitch,
      C.cameraElevationMin,
      C.cameraElevationMax
    )
    // 入场时镜头从远处推进来
    const intro = time - this.introAt
    const dolly =
      intro >= 0 && intro < INTRO_DOLLY_MS
        ? 1 + (INTRO_DOLLY_FROM - 1) * (1 - easeOutCubic(intro / INTRO_DOLLY_MS))
        : 1
    const distance = this.cameraDistance * dolly
    this.viewDistance = distance
    this.camera.position.set(
      distance * Math.sin(yaw) * Math.cos(pitch),
      distance * Math.sin(pitch),
      distance * Math.cos(yaw) * Math.cos(pitch)
    )

    // 冲击波和超频时镜头抖一抖
    const sinceShock = time - this.shockwaveAt
    const shake = (sinceShock < 0 ? 0 : Math.max(0, 1 - sinceShock / 500) * 9) + overclock * 1.6
    if (shake > 0) {
      this.camera.position.x += (Math.random() - 0.5) * shake
      this.camera.position.y += (Math.random() - 0.5) * shake
    }
    this.camera.lookAt(0, C.cameraTargetY, 0)
    this.camera.updateMatrixWorld()
  }

  private updateSatellite(
    satellite: Satellite,
    index: number,
    time: number,
    dt: number,
    appearElapsed: number | null,
    knock: number,
    dizzy: number
  ): void {
    const { root, slot } = satellite
    const appear = appearElapsed === null ? 1 : getAppearProgress(appearElapsed, index + 1)
    // 入场时从星核里甩出来：半径带一点回弹
    satellite.angle = slot.baseAngle + this.orbitPhase * this.ringSpeeds[slot.ring]
    satellite.radius = ORBIT_RINGS[slot.ring].radius * easeOutBack(appear) * (1 + knock)
    const point = getRingPoint(this.ringBases[slot.ring], satellite.radius, satellite.angle)
    root.position.set(
      point.x,
      point.y + getSatelliteFloat(index, this.satellites.length, time),
      point.z
    )
    if (dizzy > 0) {
      root.position.x += Math.sin(time * 0.013 + index * 2.1) * 16 * dizzy
      root.position.y += Math.cos(time * 0.017 + index * 1.3) * 12 * dizzy
    }
    const kind = getStatusKind(satellite.status)
    // 上次失败的卫星隔一阵哆嗦一下
    if (kind === 'failed' && (time + index * 700) % 2600 < 220) {
      root.position.x += Math.sin(time * 0.09) * 3
    }

    // 朝向：先正对镜头，再叠摆动、翻面、转晕和愚人节倒置
    const phase = index * 1.7
    const punch = time - satellite.punchAt
    const flip = punch >= 0 && punch < PUNCH_MS ? Math.PI * 2 * easeOutCubic(punch / PUNCH_MS) : 0
    this.tmpEuler.set(
      Math.sin(time * 0.0009 + phase) * C.satelliteWobble * 0.45 +
        dizzy * Math.sin(time * 0.021 + phase) * 0.9,
      Math.sin(time * 0.0011 + phase) * C.satelliteWobble + flip,
      (this.reversed ? Math.PI : 0) + dizzy * Math.sin(time * 0.015 + phase) * 1.2
    )
    root.quaternion
      .copy(this.camera.quaternion)
      .multiply(this.tmpQuaternion.setFromEuler(this.tmpEuler))

    satellite.hover +=
      ((this.hovered === index ? 1 : 0) - satellite.hover) * (1 - Math.exp(-dt / 90))
    const pulse = punch >= 0 && punch < 300 ? 1 + 0.22 * Math.sin((Math.PI * punch) / 300) : 1
    const vanish = this.getVanishScale(time, index)
    root.scale.setScalar(
      Math.max(0.001, easeOutCubic(appear) * (1 + 0.18 * satellite.hover) * pulse * vanish)
    )

    // 远处的暗一些：按到镜头的深度换算
    this.tmpVector.copy(root.position).applyMatrix4(this.camera.matrixWorldInverse)
    const front = clamp01(
      ((this.tmpVector.z + this.viewDistance) / ORBIT_RINGS[0].radius) * 0.5 + 0.5
    )
    satellite.fade = (0.45 + 0.55 * front) * easeOutCubic(appear) * Math.min(1, vanish)
    satellite.body.material.opacity = 0.94 * satellite.fade
    satellite.iconMaterial.opacity = Math.min(1, satellite.fade * 1.1)

    applyGlow(
      satellite.activityGlow,
      getActivityGlow(satellite.status, time),
      root.position,
      satellite.fade
    )
    applyGlow(
      satellite.errorGlow,
      getErrorGlow(satellite.status, time),
      root.position,
      satellite.fade
    )

    const ping = time - satellite.pingAt
    if (ping >= 0 && ping < PING_MS) {
      const progress = ping / PING_MS
      satellite.pingGlow.position.copy(root.position)
      satellite.pingGlow.material.opacity = 0.9 * (1 - progress)
      satellite.pingGlow.scale.setScalar(C.satelliteSize * (1.4 + progress * 1.6))
    } else {
      satellite.pingGlow.material.opacity = 0
    }

    satellite.decor.update(kind, {
      time,
      dt,
      anchor: root.position,
      camera: this.camera,
      fade: satellite.fade,
      scale: root.scale.x,
      visible: root.visible,
      isDark: this.isDark,
    })
  }

  /** 404 期间卫星的缩放系数：先闪烁，再消失，最后带回弹地冒回来 */
  private getVanishScale(time: number, index: number): number {
    const elapsed = time - this.vanishAt
    if (elapsed < 0 || elapsed >= VANISH_MS) return 1
    if (elapsed < 420) return Math.floor(elapsed / 55 + index) % 2 === 0 ? 1 : 0.001
    // 依次冒回来，错开的时间封顶，保证最后一颗也在 404 结束前弹完
    const back = VANISH_MS - 800 + Math.min(index, 5) * 40
    if (elapsed < back) return 0.001
    return Math.max(0.001, easeOutBack(Math.min(1, (elapsed - back) / 560)))
  }

  /** 星核闪一下 color 色：外壳变色变亮，CORE_FLASH_MS 内慢慢退回去 */
  private flashCore(time: number, color: number): void {
    this.coreFlashAt = time
    this.coreFlashColor.setHex(color)
  }

  /** 更新星核，返回它当前的高度（冲击波从这里出发） */
  private updateCore(
    time: number,
    dt: number,
    appearElapsed: number | null,
    overclock: number
  ): number {
    const centerY = getCenterFloat(time)
    const center = this.centerCard
    if (center) {
      center.quaternion.copy(this.camera.quaternion)
      center.position.set(0, centerY, 0)
      if (this.charge > 0) {
        // 蓄力时图标发抖，越满抖得越厉害
        center.position.x += (Math.random() - 0.5) * 7 * this.charge
        center.position.y += (Math.random() - 0.5) * 7 * this.charge
      }

      if (appearElapsed !== null) {
        const appear = getAppearProgress(appearElapsed, 0)
        center.material.opacity = easeOutCubic(appear)
        center.scale.setScalar(Math.max(0.001, easeOutBack(appear)))
      } else {
        // 按压形变平滑逼近，免得一帧跳到位
        const swell = 1 + 0.16 * this.charge
        const targetX = (this.centerPressed ? CENTER_PRESS_SCALE_X : 1) * swell
        const targetY = (this.centerPressed ? CENTER_PRESS_SCALE_Y : 1) * swell
        this.centerScaleX += (targetX - this.centerScaleX) * 0.35
        this.centerScaleY += (targetY - this.centerScaleY) * 0.35
        center.scale.set(this.centerScaleX, this.centerScaleY, 1)
      }

      if (this.centerRainbow?.paint(performance.now()) && center.material.map) {
        center.material.map.needsUpdate = true
      }
    }

    const coreAppear =
      appearElapsed === null ? 1 : easeOutCubic(getAppearProgress(appearElapsed, 0))
    const glow = getCenterGlow(this.centerGlowMode, time)
    applyGlow(
      this.coreGlow,
      { ...glow, size: glow.size * (1 + 0.7 * this.charge) },
      this.tmpVector.set(0, centerY, 0),
      coreAppear
    )

    // 外壳颜色跟中心光晕走：平时绿色，有新版本时彩虹；出金、点燃时被闪光色盖过去
    const shellUniforms = this.shell.material.uniforms
    const shellColor: THREE.Color = shellUniforms.uColor.value
    if (typeof glow.color === 'number') {
      shellColor.setHex(glow.color)
    } else {
      shellColor.setHSL(glow.color[0], glow.color[1], glow.color[2])
    }
    const sinceFlash = time - this.coreFlashAt
    const coreFlash = sinceFlash < 0 ? 0 : Math.max(0, 1 - sinceFlash / CORE_FLASH_MS)
    shellColor.lerp(this.coreFlashColor, coreFlash)
    const sinceShock = time - this.shockwaveAt
    const flash = sinceShock < 0 ? 0 : Math.max(0, 1 - sinceShock / 400)
    shellUniforms.uIntensity.value =
      (0.85 + 0.7 * overclock + 1.5 * this.charge + 1.6 * flash + 2 * coreFlash) * coreAppear

    // 星核背后的光芒：跟外壳同色，蓄力、超频、闪光时更亮更大、转得更快
    const raysBoost = 1 + 1.4 * this.charge + 0.8 * overclock + 2.2 * coreFlash
    this.coreRays.position.set(0, centerY, 0)
    this.coreRays.material.color.copy(shellColor)
    this.coreRays.material.rotation += dt * 0.00007 * (1 + 3 * overclock + 4 * this.charge)
    this.coreRays.material.opacity =
      Math.min(1, (this.isDark ? 0.3 : 0.18) * raysBoost) * coreAppear
    this.coreRays.scale.setScalar(560 * (0.9 + 0.1 * raysBoost) * Math.max(0.001, coreAppear))
    shellUniforms.uTime.value = time
    this.shell.position.y = centerY
    this.shell.scale.setScalar(Math.max(0.001, coreAppear * (1 + 0.08 * this.charge)))

    const spin = 1 + 5 * overclock + 4 * this.charge
    this.gyroRings[0].rotation.y += dt * 0.00035 * spin
    this.gyroRings[0].rotation.z += dt * 0.00012 * spin
    this.gyroRings[1].rotation.x += dt * 0.00028 * spin
    this.gyroRings[1].rotation.y -= dt * 0.00018 * spin
    for (const ring of this.gyroRings) {
      ring.position.y = centerY
      ring.scale.setScalar(Math.max(0.001, coreAppear))
      ring.material.opacity = (this.isDark ? 0.5 : 0.65) * coreAppear
    }

    this.swirl.points.position.y = centerY
    this.swirl.points.rotation.y += dt * 0.00022 * spin
    this.swirl.points.scale.setScalar(Math.max(0.001, coreAppear))
    this.swirl.points.material.uniforms.uTime.value = time
    return centerY
  }

  /** 彗尾：沿轨道往回取一串点，越往后越淡越小；超频时变彩虹，倒着转时拖在另一侧 */
  private updateTrails(time: number, overclock: number, motion: number): void {
    const trails = this.trails
    if (!trails) return

    const length = C.trailLength
    const direction = motion < 0 ? -1 : 1
    const spacing = C.trailSpacing * (1 + 1.5 * overclock)
    const idleColor = this.isDark ? SATELLITE_COLORS.trailDark : SATELLITE_COLORS.trailLight
    const color = this.tmpColor

    this.satellites.forEach((satellite, index) => {
      const basis = this.ringBases[satellite.slot.ring]
      const head = getRingPoint(basis, satellite.radius, satellite.angle)
      const floatOffset = satellite.root.position.y - head.y
      const statusColor = getTrailStatusColor(satellite.status)
      const strength = satellite.fade * (satellite.root.visible ? 1 : 0.45)

      for (let k = 0; k < length; k++) {
        const i = index * length + k
        const along = (k + 1) / length
        const point = getRingPoint(
          basis,
          satellite.radius,
          satellite.angle - direction * (k + 1) * spacing
        )
        trails.positions[i * 3] = point.x
        trails.positions[i * 3 + 1] = point.y + floatOffset
        trails.positions[i * 3 + 2] = point.z

        if (overclock > 0.15) {
          color.setHSL((time * 0.0006 + along) % 1, 0.9, 0.62)
        } else {
          color.setHex(statusColor ?? idleColor)
        }
        trails.colors[i * 3] = color.r
        trails.colors[i * 3 + 1] = color.g
        trails.colors[i * 3 + 2] = color.b
        trails.alphas[i] = Math.pow(1 - along, 1.4) * 0.85 * strength
        trails.sizes[i] = (22 - 17 * along) * (statusColor === null ? 1 : 1.2)
      }
    })
    trails.commit()
  }

  private updateShockwave(time: number, centerY: number): void {
    const elapsed = time - this.shockwaveAt
    if (elapsed < 0 || elapsed > SHOCKWAVE_MS) {
      if (this.shockwaveRing) this.shockwaveRing.visible = false
      return
    }

    if (!this.shockwaveRing) {
      this.shockwaveRing = new THREE.Mesh(
        new THREE.PlaneGeometry(2, 2),
        new THREE.MeshBasicMaterial({
          map: createShockwaveTexture(),
          transparent: true,
          blending: THREE.AdditiveBlending,
          depthTest: false,
          depthWrite: false,
        })
      )
      this.shockwaveRing.renderOrder = RENDER_ORDER.overlay
      this.scene.add(this.shockwaveRing)
    }

    const progress = elapsed / SHOCKWAVE_MS
    const ring = this.shockwaveRing
    ring.material.color.setHex(this.shockwaveColor)
    ring.visible = true
    ring.position.set(0, centerY, 0)
    ring.quaternion.copy(this.camera.quaternion)
    ring.scale.setScalar(60 + easeOutCubic(progress) * 620)
    ring.material.opacity = 1 - progress
  }

  private updateReveal(time: number): void {
    if (!this.reveal) {
      return
    }

    const from =
      this.satellites[this.reveal.satellite]?.root.position ?? this.tmpVector.set(0, 0, 0)
    // 停靠点在星核和镜头之间、离镜头三分之二处；脸的大小按那里的可视高度算，占掉大半个画面
    const stage = this.camera.position.clone().multiplyScalar(0.34)
    const visibleHeight =
      2 *
      stage.distanceTo(this.camera.position) *
      Math.tan(THREE.MathUtils.degToRad(C.cameraFov / 2))
    if (this.reveal.effect.update(time, from, stage, visibleHeight * 0.72)) {
      this.reveal.effect.dispose()
      this.reveal = null
    }
  }

  // ==================== 内部 ====================

  private get tileColor(): number {
    return this.isDark ? SATELLITE_COLORS.tileDark : SATELLITE_COLORS.tileLight
  }

  /** 卫星区域的高度跟着窗口宽度走（见组件样式），每次都读容器的实际高度 */
  private get height(): number {
    return Math.max(1, this.host.clientHeight)
  }

  private get pixelRatio(): number {
    return Math.min(window.devicePixelRatio || 1, 2)
  }

  /** 粒子的像素大小要乘设备像素比，否则高分屏上一半大 */
  private syncPixelRatio(): void {
    const ratio = this.renderer.getPixelRatio()
    for (const cloud of [this.stars, this.swirl, this.trails]) {
      if (cloud) cloud.points.material.uniforms.uPixelRatio.value = ratio
    }
  }

  private setRayFromClient(clientX: number, clientY: number): boolean {
    const bounds = this.renderer.domElement.getBoundingClientRect()
    if (bounds.width <= 0 || bounds.height <= 0) {
      return false
    }
    this.pointer.set(
      ((clientX - bounds.left) / bounds.width) * 2 - 1,
      -((clientY - bounds.top) / bounds.height) * 2 + 1
    )
    this.raycaster.setFromCamera(this.pointer, this.camera)
    return true
  }

  private project(position: THREE.Vector3): ScreenPoint {
    const projected = position.clone().project(this.camera)
    return {
      x: ((projected.x + 1) / 2) * this.host.clientWidth,
      y: ((1 - projected.y) / 2) * this.height,
    }
  }

  private createRenderer(): THREE.WebGLRenderer {
    // 低性能模式下主页根本不挂卫星，这里不用为它降配
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    })
    renderer.setClearColor(0x000000, 0)
    renderer.setPixelRatio(this.pixelRatio)
    renderer.setSize(Math.max(1, this.host.clientWidth), this.height)

    const canvas = renderer.domElement
    canvas.setAttribute('aria-label', '脚本卫星互动区域')
    canvas.style.position = 'absolute'
    canvas.style.top = '0'
    canvas.style.left = '0'
    canvas.style.zIndex = '1'
    canvas.style.touchAction = 'none'
    this.host.appendChild(canvas)
    return renderer
  }

  /** 金属边的反光要一张环境贴图；它绑在渲染器上，重建渲染器时一起重建 */
  private applyEnvironment(): void {
    this.environment?.dispose()
    const generator = new THREE.PMREMGenerator(this.renderer)
    const room = new RoomEnvironment()
    this.environment = generator.fromScene(room, 0.04)
    this.scene.environment = this.environment.texture
    room.dispose()
    generator.dispose()
  }

  private disposeRenderer(): void {
    this.renderer.domElement.remove()
    this.renderer.dispose()
  }

  private setSatelliteVisible(satellite: Satellite, visible: boolean): void {
    satellite.root.visible = visible
    satellite.activityGlow.visible = visible
    satellite.errorGlow.visible = visible
  }

  private finishExplosion(satellite: Satellite): void {
    if (!satellite.explosion) {
      return
    }

    satellite.explosion.dispose()
    satellite.explosion = null
    this.setSatelliteVisible(satellite, true)
  }
}
