import * as THREE from 'three'
import type { SatelliteModuleStatus } from '@/composables/useSatelliteStatus'
import type { ScriptType } from '@/types/script'
import { createRainbowIcon, type RainbowIcon } from '../satellite/centerRainbow'
import { loadImageToCanvas } from '../satellite/sceneParts'
import {
  CENTER_PRESS_SCALE_X,
  CENTER_PRESS_SCALE_Y,
  SATELLITE_COLORS,
  SATELLITE_CONFIG as C,
} from './config'
import { SatelliteExplosion } from './explosionEffect'
import {
  getActivityGlow,
  getAppearDuration,
  getAppearProgress,
  getCenterFloat,
  getCenterGlow,
  getErrorGlow,
  getSatelliteBaseAngle,
  getSatellitePosition,
  type CenterGlowMode,
  type GlowAppearance,
} from './motion'

// ==================== 类型定义 ====================

type CardMesh = THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>

interface Satellite {
  /** 卫星键，运行状态按它取：一般就是脚本类型，通用 MFW 每个项目一颗 */
  key: string
  type: ScriptType
  card: CardMesh
  baseAngle: number
  activityGlow: THREE.Sprite
  errorGlow: THREE.Sprite
  status: SatelliteModuleStatus
  explosion: SatelliteExplosion | null
}

export interface SatelliteSceneModule {
  key: string
  scriptType: ScriptType
  iconUrl: string
  /** iconUrl 加载不出来时换用的图标（通用 MFW 项目图标取不到时用 MFW 图标） */
  fallbackIconUrl?: string
}

/** 指针下是什么：中心图标、第几颗卫星，或者什么都没点到 */
export type SatellitePick = 'center' | number | null

const IDLE_STATUS: SatelliteModuleStatus = { queued: false, running: false, lastFailed: false }

// ==================== 资源 ====================

function createCanvasTexture(canvas: HTMLCanvasElement): THREE.CanvasTexture {
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.needsUpdate = true
  return texture
}

function createGlowTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = 128
  canvas.height = 128
  const ctx = canvas.getContext('2d')!
  const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64)
  gradient.addColorStop(0, 'rgba(255, 255, 255, 0.85)')
  gradient.addColorStop(0.15, 'rgba(255, 255, 255, 0.55)')
  gradient.addColorStop(0.35, 'rgba(255, 255, 255, 0.2)')
  gradient.addColorStop(0.6, 'rgba(255, 255, 255, 0.05)')
  gradient.addColorStop(1, 'rgba(255, 255, 255, 0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, 128, 128)
  return new THREE.CanvasTexture(canvas)
}

/** 一张正对镜头的图标卡片；入场前是透明、缩到几乎看不见的 */
async function createCard(
  size: number,
  faceOffset: number,
  imageUrl: string,
  fallbackUrl?: string
): Promise<CardMesh> {
  const canvas = await loadImageToCanvas(imageUrl, fallbackUrl)
  const geometry = new THREE.PlaneGeometry(size, size)
  geometry.translate(0, 0, faceOffset)
  const card = new THREE.Mesh(
    geometry,
    new THREE.MeshBasicMaterial({ map: createCanvasTexture(canvas), transparent: true, opacity: 0 })
  )
  card.scale.set(0.01, 0.01, 0.01)
  return card
}

function getCardImageCanvas(card: CardMesh): HTMLCanvasElement | null {
  const image = card.material.map?.image
  if (!(image instanceof HTMLCanvasElement) || image.width <= 0 || image.height <= 0) {
    return null
  }
  return image
}

function disposeCard(card: CardMesh): void {
  card.geometry.dispose()
  card.material.map?.dispose()
  card.material.dispose()
}

function disposeSceneResources(scene: THREE.Scene): void {
  const geometries = new Set<THREE.BufferGeometry>()
  const materials = new Set<THREE.Material>()
  const textures = new Set<THREE.Texture>()

  scene.traverse(object => {
    const { geometry, material } = object as THREE.Object3D & {
      geometry?: THREE.BufferGeometry
      material?: THREE.Material | THREE.Material[]
    }
    if (geometry) geometries.add(geometry)
    for (const mat of Array.isArray(material) ? material : material ? [material] : []) {
      materials.add(mat)
      const { map } = mat as THREE.Material & { map?: THREE.Texture | null }
      if (map) textures.add(map)
    }
  })

  geometries.forEach(geometry => geometry.dispose())
  materials.forEach(material => material.dispose())
  textures.forEach(texture => texture.dispose())
  scene.clear()
}

function getPixelRatio(lowPerformance: boolean): number {
  return Math.min(window.devicePixelRatio || 1, lowPerformance ? 1 : 2)
}

function setCardAppear(card: CardMesh, progress: number): void {
  card.material.opacity = progress
  card.scale.set(progress, progress, progress)
}

function applyGlow(
  sprite: THREE.Sprite,
  appearance: GlowAppearance | null,
  anchor: THREE.Vector3,
  zOffset: number
): void {
  sprite.position.set(anchor.x, anchor.y, anchor.z + zOffset)
  if (!appearance) {
    sprite.material.opacity = 0
    return
  }

  const { color } = appearance
  if (typeof color === 'number') {
    sprite.material.color.setHex(color)
  } else {
    sprite.material.color.setHSL(color[0], color[1], color[2])
  }
  sprite.material.opacity = appearance.opacity
  sprite.scale.set(appearance.size, appearance.size, 1)
}

// ==================== 场景 ====================

/**
 * 主页卫星的 three.js 场景：中心图标、绕着它转的脚本卫星、轨道线和状态光晕。
 *
 * 画面分三层，自下而上是光晕、轨道、卡片——轨道永远压在卫星下面是设计。三层画在同一块
 * 画布上，每层之前清一次深度，叠出来的效果等同于三块透明画布摞在一起。
 */
export class SatelliteScene {
  private readonly host: HTMLElement
  private lowPerformance: boolean
  private renderer: THREE.WebGLRenderer
  private readonly camera: THREE.PerspectiveCamera
  private readonly glowScene = new THREE.Scene()
  private readonly orbitScene = new THREE.Scene()
  private readonly cardScene = new THREE.Scene()
  private readonly orbitMaterial: THREE.LineBasicMaterial
  private readonly glowTexture = createGlowTexture()
  private readonly raycaster = new THREE.Raycaster()
  private readonly pointer = new THREE.Vector2()

  private satellites: Satellite[] = []
  private centerCard: CardMesh | null = null
  private centerGlow: THREE.Sprite | null = null
  /** 中心图标原图；炫彩版以它为底，关掉炫彩时也从它还原，不用重新加载 */
  private centerIconCanvas: HTMLCanvasElement | null = null
  private centerRainbow: RainbowIcon | null = null
  private centerGlowMode: CenterGlowMode = 'green'
  private centerPressed = false
  private centerScaleX = 1
  private centerScaleY = 1
  /** 入场动画的起点；null 表示不在入场中 */
  private appearStartedAt: number | null = null

  constructor(host: HTMLElement, options: { lowPerformance: boolean; isDark: boolean }) {
    this.host = host
    this.lowPerformance = options.lowPerformance

    this.camera = new THREE.PerspectiveCamera(
      C.cameraFov,
      Math.max(1, host.clientWidth) / C.containerHeight,
      0.1,
      5000
    )
    this.camera.position.set(0, C.cameraY, C.cameraZ)
    this.camera.lookAt(0, 0, 0)
    this.renderer = this.createRenderer()

    const orbitPoints = new THREE.EllipseCurve(
      0,
      0,
      C.orbitRadiusX,
      C.orbitRadiusY,
      0,
      2 * Math.PI,
      false,
      0
    ).getPoints(128)
    this.orbitMaterial = new THREE.LineBasicMaterial({ transparent: true, opacity: C.orbitOpacity })
    const orbitLine = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(orbitPoints),
      this.orbitMaterial
    )
    orbitLine.rotation.x = C.orbitTilt
    this.orbitScene.add(orbitLine)
    this.setDark(options.isDark)
  }

  /** 加载中心图标和各卫星的图片；加载期间 isCancelled 变真就返回 false，场景交给调用方销毁 */
  async load(
    centerIconUrl: string,
    modules: readonly SatelliteSceneModule[],
    isCancelled: () => boolean
  ): Promise<boolean> {
    const [centerCard, ...satelliteCards] = await Promise.all([
      createCard(C.centerCardSize, C.centerCardFaceOffset, centerIconUrl),
      ...modules.map(module =>
        createCard(
          C.satelliteCardSize,
          C.satelliteCardFaceOffset,
          module.iconUrl,
          module.fallbackIconUrl
        )
      ),
    ])
    if (isCancelled()) {
      for (const card of [centerCard, ...satelliteCards]) {
        disposeCard(card)
      }
      return false
    }

    this.centerCard = centerCard
    this.centerIconCanvas = getCardImageCanvas(centerCard)
    this.cardScene.add(centerCard)
    this.centerGlow = this.createGlowSprite()

    this.satellites = satelliteCards.map((card, index) => {
      this.cardScene.add(card)
      return {
        key: modules[index].key,
        type: modules[index].scriptType,
        card,
        baseAngle: getSatelliteBaseAngle(index, modules.length),
        activityGlow: this.createGlowSprite(),
        errorGlow: this.createGlowSprite(),
        status: IDLE_STATUS,
        explosion: null,
      }
    })
    return true
  }

  // ==================== 状态 ====================

  setDark(isDark: boolean): void {
    this.orbitMaterial.color.setHex(
      isDark ? SATELLITE_COLORS.orbitDark : SATELLITE_COLORS.orbitLight
    )
  }

  /** 抗锯齿和功耗偏好只能在建上下文时定，换模式就重建渲染器 */
  setLowPerformance(lowPerformance: boolean): void {
    if (lowPerformance === this.lowPerformance) {
      return
    }

    this.lowPerformance = lowPerformance
    this.clearExplosions()
    this.disposeRenderer()
    this.renderer = this.createRenderer()
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
    for (const card of [this.centerCard, ...this.satellites.map(satellite => satellite.card)]) {
      if (card) setCardAppear(card, 1)
    }
  }

  // ==================== 交互 ====================

  pick(clientX: number, clientY: number): SatellitePick {
    const bounds = this.renderer.domElement.getBoundingClientRect()
    if (bounds.width <= 0 || bounds.height <= 0) {
      return null
    }

    this.pointer.set(
      ((clientX - bounds.left) / bounds.width) * 2 - 1,
      -((clientY - bounds.top) / bounds.height) * 2 + 1
    )
    this.raycaster.setFromCamera(this.pointer, this.camera)

    if (this.centerCard && this.raycaster.intersectObject(this.centerCard, false).length > 0) {
      return 'center'
    }

    const cards = this.satellites.map(satellite => satellite.card)
    const hit = this.raycaster.intersectObjects(cards, false)[0]
    if (!hit || !hit.object.visible) {
      return null
    }

    // 入场还没长出来的卫星不算点中
    const card = hit.object as CardMesh
    if (card.material.opacity <= 0.05 || card.scale.x <= 0.05) {
      return null
    }
    return cards.indexOf(card)
  }

  explode(index: number, time: number): void {
    const satellite = this.satellites[index]
    const source = satellite && getCardImageCanvas(satellite.card)
    if (!satellite || satellite.explosion || !source) {
      return
    }

    satellite.explosion = new SatelliteExplosion({
      card: satellite.card,
      source,
      seed: index + 17,
      glowTexture: this.glowTexture,
      cardScene: this.cardScene,
      effectScene: this.lowPerformance ? this.cardScene : this.glowScene,
      startTime: time,
    })
    this.setSatelliteVisible(satellite, false)
  }

  clearExplosions(): void {
    this.satellites.forEach(satellite => this.finishExplosion(satellite))
  }

  // ==================== 渲染 ====================

  /** 推进到 time 时刻并画一帧；返回是否还有碎裂特效没放完 */
  renderFrame(time: number): boolean {
    const cameraPosition = this.camera.position
    const count = this.satellites.length

    let appearElapsed = this.appearStartedAt === null ? null : time - this.appearStartedAt
    if (appearElapsed !== null && appearElapsed > getAppearDuration(count)) {
      this.skipAppear()
      appearElapsed = null
    }

    this.satellites.forEach((satellite, index) => {
      const { card } = satellite
      const position = getSatellitePosition(satellite.baseAngle, index, count, time)
      card.position.set(position.x, position.y, position.z)
      card.lookAt(cameraPosition)
      card.rotation.z = 0
      if (appearElapsed !== null) {
        setCardAppear(card, getAppearProgress(appearElapsed, index + 1))
      }
    })

    if (this.centerCard) {
      const center = this.centerCard
      center.lookAt(cameraPosition)
      center.rotation.z = 0
      center.position.y = getCenterFloat(time)
      if (appearElapsed !== null) {
        setCardAppear(center, getAppearProgress(appearElapsed, 0))
      } else {
        // 按压形变平滑逼近，免得一帧跳到位
        const targetX = this.centerPressed ? CENTER_PRESS_SCALE_X : 1
        const targetY = this.centerPressed ? CENTER_PRESS_SCALE_Y : 1
        this.centerScaleX += (targetX - this.centerScaleX) * 0.35
        this.centerScaleY += (targetY - this.centerScaleY) * 0.35
        center.scale.set(this.centerScaleX, this.centerScaleY, 1)
      }

      if (this.centerRainbow?.paint(performance.now()) && center.material.map) {
        center.material.map.needsUpdate = true
      }
    }

    let exploding = false
    for (const satellite of this.satellites) {
      if (satellite.explosion?.update(time)) {
        this.finishExplosion(satellite)
      } else if (satellite.explosion) {
        exploding = true
      }
    }

    const { renderer, camera } = this
    renderer.clear()
    // 低性能模式不画光晕层
    if (!this.lowPerformance) {
      this.updateGlows(time)
      renderer.render(this.glowScene, camera)
    }
    renderer.clearDepth()
    renderer.render(this.orbitScene, camera)
    renderer.clearDepth()
    renderer.render(this.cardScene, camera)

    return exploding
  }

  resize(): void {
    const width = this.host.clientWidth
    if (width <= 0) {
      return
    }

    this.camera.aspect = width / C.containerHeight
    this.camera.updateProjectionMatrix()
    this.renderer.setPixelRatio(getPixelRatio(this.lowPerformance))
    this.renderer.setSize(width, C.containerHeight)
  }

  dispose(): void {
    this.clearExplosions()
    disposeSceneResources(this.glowScene)
    disposeSceneResources(this.orbitScene)
    disposeSceneResources(this.cardScene)
    this.glowTexture.dispose()
    this.disposeRenderer()
    this.satellites = []
    this.centerCard = null
    this.centerGlow = null
    this.centerIconCanvas = null
    this.centerRainbow = null
  }

  // ==================== 内部 ====================

  private createRenderer(): THREE.WebGLRenderer {
    const renderer = new THREE.WebGLRenderer({
      antialias: !this.lowPerformance,
      alpha: true,
      powerPreference: this.lowPerformance ? 'low-power' : 'high-performance',
    })
    // 三层叠在同一块画布上，清屏由 renderFrame 自己管
    renderer.autoClear = false
    renderer.setClearColor(0x000000, 0)
    renderer.setPixelRatio(getPixelRatio(this.lowPerformance))
    renderer.setSize(Math.max(1, this.host.clientWidth), C.containerHeight)

    const canvas = renderer.domElement
    canvas.setAttribute('aria-label', '脚本卫星互动区域')
    canvas.style.position = 'absolute'
    canvas.style.top = '0'
    canvas.style.left = '0'
    canvas.style.zIndex = '1'
    canvas.style.touchAction = 'manipulation'
    this.host.appendChild(canvas)
    return renderer
  }

  private disposeRenderer(): void {
    this.renderer.domElement.remove()
    this.renderer.dispose()
  }

  /** 光晕贴图的颜色、透明度和大小每帧由 updateGlows 按状态重算，这里只建空壳 */
  private createGlowSprite(): THREE.Sprite {
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: this.glowTexture,
        transparent: true,
        blending: THREE.AdditiveBlending,
        opacity: 0,
      })
    )
    this.glowScene.add(sprite)
    return sprite
  }

  private updateGlows(time: number): void {
    for (const satellite of this.satellites) {
      const anchor = satellite.card.position
      applyGlow(
        satellite.activityGlow,
        getActivityGlow(satellite.status, time),
        anchor,
        C.activityGlowZOffset
      )
      applyGlow(
        satellite.errorGlow,
        getErrorGlow(satellite.status, time),
        anchor,
        C.errorGlowZOffset
      )
    }

    if (this.centerGlow && this.centerCard) {
      applyGlow(
        this.centerGlow,
        getCenterGlow(this.centerGlowMode, time),
        this.centerCard.position,
        C.activityGlowZOffset
      )
    }
  }

  private setSatelliteVisible(satellite: Satellite, visible: boolean): void {
    satellite.card.visible = visible
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
