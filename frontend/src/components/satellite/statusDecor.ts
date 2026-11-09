import * as THREE from 'three'
import { SATELLITE_COLORS, SATELLITE_CONFIG as C } from './config'
import type { StatusKind } from './motion'
import { RENDER_ORDER } from './sceneParts'

// ==================== 状态徽标贴图 ====================

type BadgeKind = Exclude<StatusKind, 'idle'>

const BADGE_COLORS: Record<BadgeKind, string> = {
  scheduled: '#7f9c90',
  failed: '#ff4d57',
}

/** 已安排用圆点、最近失败用叹号；全用路径画，不依赖字体。 */
function drawBadge(kind: BadgeKind): THREE.CanvasTexture {
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const c = size / 2
  ctx.shadowColor = 'rgba(0, 0, 0, 0.35)'
  ctx.shadowBlur = 4
  ctx.fillStyle = BADGE_COLORS[kind]
  ctx.beginPath()
  ctx.arc(c, c, 26, 0, Math.PI * 2)
  ctx.fill()
  ctx.shadowBlur = 0
  ctx.lineWidth = 3
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)'
  ctx.stroke()

  ctx.fillStyle = '#ffffff'
  ctx.strokeStyle = '#ffffff'
  ctx.lineCap = 'round'
  if (kind === 'scheduled') {
    for (const dx of [-10, 0, 10]) {
      ctx.beginPath()
      ctx.arc(c + dx, c, 3.6, 0, Math.PI * 2)
      ctx.fill()
    }
  } else if (kind === 'failed') {
    ctx.lineWidth = 6
    ctx.beginPath()
    ctx.moveTo(c, c - 13)
    ctx.lineTo(c, c + 3)
    ctx.stroke()
    ctx.beginPath()
    ctx.arc(c, c + 12, 3.4, 0, Math.PI * 2)
    ctx.fill()
  }

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

/** 一个场景里所有卫星共用的状态贴图 */
export interface StatusTextures {
  rays: THREE.Texture
  glow: THREE.Texture
  badges: Record<BadgeKind, THREE.Texture>
}

export function createBadgeTextures(): Record<BadgeKind, THREE.Texture> {
  return {
    scheduled: drawBadge('scheduled'),
    failed: drawBadge('failed'),
  }
}

// ==================== 每种状态的样子 ====================

interface StatusStyle {
  color: number
  /** 光芒的不透明度和转速（弧度/毫秒） */
  raysOpacity: number
  raysSpin: number
  /** 外圈：进度弧（转）、整环（呼吸），或者没有 */
  ring: 'full' | null
  ringSpin: number
  /** 绕着转的小光点 */
  dots: boolean
}

const STATUS_STYLES: Record<StatusKind, StatusStyle> = {
  idle: {
    color: SATELLITE_COLORS.trailDark,
    raysOpacity: 0.16,
    raysSpin: 0.00015,
    ring: null,
    ringSpin: 0,
    dots: false,
  },
  scheduled: {
    color: SATELLITE_COLORS.active,
    raysOpacity: 0.34,
    raysSpin: 0.0003,
    ring: null,
    ringSpin: 0,
    dots: true,
  },
  failed: {
    color: SATELLITE_COLORS.failed,
    raysOpacity: 0.48,
    raysSpin: 0,
    ring: 'full',
    ringSpin: 0,
    dots: false,
  },
}

const RING_INNER = C.satelliteSize * 0.78
const RING_OUTER = C.satelliteSize * 0.84
const DOT_COUNT = 3

/**
 * 卫星的光芒和状态装饰：背后一圈旋转光芒，外圈警示环，已安排时绕转的小光点，
 * 右上角一个状态徽标。全都正对镜头，跟着卫星走。
 */
export class SatelliteDecor {
  private readonly scene: THREE.Scene
  private readonly textures: StatusTextures
  private readonly rays: THREE.Sprite
  private readonly fullRing: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>
  private readonly dots: THREE.Sprite[]
  private readonly badge: THREE.Sprite
  private readonly phase = Math.random() * Math.PI * 2
  private raysRotation = Math.random() * Math.PI * 2
  private ringRotation = 0
  private kind: StatusKind = 'idle'

  private readonly tmpRight = new THREE.Vector3()
  private readonly tmpUp = new THREE.Vector3()
  private readonly tmpForward = new THREE.Vector3()

  constructor(scene: THREE.Scene, textures: StatusTextures) {
    this.scene = scene
    this.textures = textures

    this.rays = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: textures.rays,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        opacity: 0,
      })
    )
    this.rays.renderOrder = RENDER_ORDER.satelliteGlow
    this.rays.scale.setScalar(C.satelliteSize * 3.1)

    const ringMaterial = () =>
      new THREE.MeshBasicMaterial({
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide,
      })
    this.fullRing = new THREE.Mesh(
      new THREE.RingGeometry(RING_INNER, RING_OUTER, 64),
      ringMaterial()
    )
    this.fullRing.renderOrder = RENDER_ORDER.satelliteIcon

    this.dots = Array.from({ length: DOT_COUNT }, () => {
      const dot = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: textures.glow,
          transparent: true,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          color: SATELLITE_COLORS.active,
        })
      )
      dot.renderOrder = RENDER_ORDER.satelliteIcon
      dot.scale.setScalar(16)
      return dot
    })

    this.badge = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: textures.badges.scheduled,
        transparent: true,
        depthWrite: false,
      })
    )
    this.badge.renderOrder = RENDER_ORDER.satelliteIcon
    this.badge.scale.setScalar(22)

    scene.add(this.rays, this.fullRing, this.badge, ...this.dots)
    this.applyKind('idle')
  }

  /**
   * 跟着卫星摆好位置、按状态动起来。fade 是卫星的远近透明度，scale 是它当前的缩放
   * （入场、悬停、404 消失都会改），visible 为假时整套藏起来。
   */
  update(
    kind: StatusKind,
    options: {
      time: number
      dt: number
      anchor: THREE.Vector3
      camera: THREE.Camera
      fade: number
      scale: number
      visible: boolean
      isDark: boolean
    }
  ): void {
    if (kind !== this.kind) this.applyKind(kind)
    const { time, dt, anchor, camera, fade, scale, visible, isDark } = options
    const style = STATUS_STYLES[kind]
    const shown = visible && scale > 0.05

    // 光芒：空闲时浅色主题再淡一点，免得白底上一片灰
    this.raysRotation += dt * style.raysSpin
    const flicker =
      kind === 'failed' ? 0.6 + 0.4 * Math.abs(Math.sin(time * 0.0023 + this.phase)) : 1
    this.rays.visible = shown
    this.rays.position.copy(anchor)
    this.rays.material.rotation = this.raysRotation
    this.rays.material.opacity =
      style.raysOpacity * flicker * fade * (isDark || kind !== 'idle' ? 1 : 0.5)
    this.rays.scale.setScalar(C.satelliteSize * 3.1 * scale)

    // 外圈和徽标正对镜头，用镜头的右、上、前方向摆
    this.tmpRight.setFromMatrixColumn(camera.matrixWorld, 0)
    this.tmpUp.setFromMatrixColumn(camera.matrixWorld, 1)
    this.tmpForward.setFromMatrixColumn(camera.matrixWorld, 2)

    this.ringRotation += dt * style.ringSpin
    this.fullRing.position.copy(anchor).addScaledVector(this.tmpForward, 2)
    this.fullRing.quaternion.copy(camera.quaternion)
    this.fullRing.rotateZ(-this.ringRotation)
    this.fullRing.scale.setScalar(Math.max(0.001, scale))
    this.fullRing.visible = shown && style.ring === 'full'
    this.fullRing.material.opacity =
      (0.35 + 0.45 * Math.abs(Math.sin(time * 0.003 + this.phase))) * fade

    this.dots.forEach((dot, index) => {
      const angle = time * 0.0016 + (index / DOT_COUNT) * Math.PI * 2 + this.phase
      const radius = C.satelliteSize * 0.82 * scale
      dot.visible = shown && style.dots
      dot.position
        .copy(anchor)
        .addScaledVector(this.tmpRight, Math.cos(angle) * radius)
        .addScaledVector(this.tmpUp, Math.sin(angle) * radius)
      dot.material.opacity = 0.85 * fade
    })

    this.badge.visible = shown && kind !== 'idle'
    const corner = C.satelliteSize * 0.55 * scale
    this.badge.position
      .copy(anchor)
      .addScaledVector(this.tmpRight, corner)
      .addScaledVector(this.tmpUp, corner)
      .addScaledVector(this.tmpForward, C.satelliteDepth)
    this.badge.scale.setScalar(
      22 * Math.max(0.001, scale) * (kind === 'failed' ? 1 + 0.08 * flicker : 1)
    )
    this.badge.material.opacity = Math.min(1, fade * 1.2)
  }

  dispose(): void {
    this.scene.remove(this.rays, this.fullRing, this.badge, ...this.dots)
    this.fullRing.geometry.dispose()
    this.fullRing.material.dispose()
    this.rays.material.dispose()
    this.badge.material.dispose()
    this.dots.forEach(dot => dot.material.dispose())
  }

  private applyKind(kind: StatusKind): void {
    this.kind = kind
    const style = STATUS_STYLES[kind]
    this.rays.material.color.setHex(style.color)
    this.fullRing.material.color.setHex(style.color)
    if (kind !== 'idle') {
      this.badge.material.map = this.textures.badges[kind]
      this.badge.material.needsUpdate = true
    }
  }
}
