import type { SatelliteModule, SatelliteVisualStatus } from '@/composables/useSatelliteStatus'
import * as THREE from 'three'

const ICON_TEXTURE_SIZE = 128
const DEFAULT_IMAGE_TIMEOUT = 5000

const SCENE_CONFIG = {
  cameraFov: 50,
  orbitTilt: 0.35,
  orbitOpacity: 0.4,
  satelliteOrbitSpeed: 0.0006,
  satelliteFloatAmplitude: 10,
  satelliteFloatSpeed: 1.2,
  centerFloatAmplitude: 4,
  centerFloatSpeed: 0.8,
  cardAppearDelay: 150,
  cardAppearDuration: 400,
  glowSizeMultiplier: 3.5,
}

type CardMesh = THREE.Mesh<THREE.BoxGeometry, THREE.Material[]>
type GlowSprite = THREE.Sprite

interface SceneLayout {
  orbitRadiusX: number
  orbitRadiusY: number
  centerCardSize: number
  centerCardDepth: number
  satelliteCardSize: number
  satelliteCardDepth: number
}

interface SatelliteSceneState {
  module: SatelliteModule
  card: CardMesh
  glow: GlowSprite
  baseAngle: number
  visualState: SatelliteVisualStatus
}

export interface PreparedSatelliteModule {
  module: SatelliteModule
  iconCanvas: HTMLCanvasElement
}

function isCrossOriginHttpUrl(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.href)
    return (
      (parsed.protocol === 'http:' || parsed.protocol === 'https:') &&
      parsed.origin !== window.location.origin
    )
  } catch {
    return false
  }
}

/**
 * 加载并验证卫星图标。绘制和像素读取会同时验证跨域权限及图片解码结果。
 */
export function loadSatelliteIconCanvas(
  url: string,
  timeoutMs = DEFAULT_IMAGE_TIMEOUT
): Promise<HTMLCanvasElement> {
  if (!url.trim()) {
    return Promise.reject(new Error('未提供图标地址'))
  }

  return new Promise((resolve, reject) => {
    const image = new Image()
    let settled = false

    const cleanup = () => {
      window.clearTimeout(timer)
      image.onload = null
      image.onerror = null
    }
    const fail = (reason: string) => {
      if (settled) return
      settled = true
      cleanup()
      reject(new Error(reason))
    }
    const timer = window.setTimeout(() => {
      fail('图标加载超时')
    }, timeoutMs)

    image.decoding = 'async'
    if (isCrossOriginHttpUrl(url)) {
      image.crossOrigin = 'anonymous'
    }

    image.onerror = () => fail('图标加载失败')
    image.onload = async () => {
      try {
        await image.decode()
        if (settled) return
        if (image.naturalWidth <= 0 || image.naturalHeight <= 0) {
          fail('图标尺寸无效')
          return
        }

        const canvas = document.createElement('canvas')
        canvas.width = ICON_TEXTURE_SIZE
        canvas.height = ICON_TEXTURE_SIZE
        const context = canvas.getContext('2d')
        if (!context) {
          fail('无法创建图标纹理')
          return
        }

        const scale = Math.min(
          ICON_TEXTURE_SIZE / image.naturalWidth,
          ICON_TEXTURE_SIZE / image.naturalHeight
        )
        const width = image.naturalWidth * scale
        const height = image.naturalHeight * scale
        context.clearRect(0, 0, ICON_TEXTURE_SIZE, ICON_TEXTURE_SIZE)
        context.drawImage(
          image,
          (ICON_TEXTURE_SIZE - width) / 2,
          (ICON_TEXTURE_SIZE - height) / 2,
          width,
          height
        )

        // 跨域图片没有正确的 CORS 响应头时，此处会抛出 SecurityError。
        context.getImageData(0, 0, 1, 1)
        settled = true
        cleanup()
        resolve(canvas)
      } catch {
        fail('图标解码或跨域校验失败')
      }
    }

    image.src = url
  })
}

function createGlowTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = ICON_TEXTURE_SIZE
  canvas.height = ICON_TEXTURE_SIZE
  const context = canvas.getContext('2d')
  if (!context) {
    throw new Error('无法创建光效纹理')
  }

  const center = ICON_TEXTURE_SIZE / 2
  const gradient = context.createRadialGradient(center, center, 0, center, center, center)
  gradient.addColorStop(0, 'rgba(255, 255, 255, 0.85)')
  gradient.addColorStop(0.15, 'rgba(255, 255, 255, 0.55)')
  gradient.addColorStop(0.35, 'rgba(255, 255, 255, 0.2)')
  gradient.addColorStop(0.6, 'rgba(255, 255, 255, 0.05)')
  gradient.addColorStop(1, 'rgba(255, 255, 255, 0)')
  context.fillStyle = gradient
  context.fillRect(0, 0, ICON_TEXTURE_SIZE, ICON_TEXTURE_SIZE)
  return new THREE.CanvasTexture(canvas)
}

function createCard(iconCanvas: HTMLCanvasElement, isDark: boolean): CardMesh {
  const texture = new THREE.CanvasTexture(iconCanvas)
  texture.colorSpace = THREE.SRGBColorSpace

  const frontMaterial = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    opacity: 0,
  })
  const sideMaterial = new THREE.MeshStandardMaterial({
    color: isDark ? 0x2a2a2a : 0xf0f0f0,
    roughness: 0.9,
    metalness: 0,
  })
  const materials: THREE.Material[] = [
    sideMaterial,
    sideMaterial,
    sideMaterial,
    sideMaterial,
    frontMaterial,
    sideMaterial,
  ]

  const card = new THREE.Mesh<THREE.BoxGeometry, THREE.Material[]>(
    new THREE.BoxGeometry(1, 1, 1),
    materials
  )
  card.scale.setScalar(0.01)
  return card
}

function getFrontMaterial(card: CardMesh): THREE.MeshBasicMaterial {
  return card.material[4] as THREE.MeshBasicMaterial
}

function easeOutCubic(value: number): number {
  return 1 - Math.pow(1 - value, 3)
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export class SatelliteAnimationScene {
  private readonly container: HTMLDivElement
  private readonly orbitScene = new THREE.Scene()
  private readonly glowScene = new THREE.Scene()
  private readonly cardScene = new THREE.Scene()
  private readonly camera = new THREE.PerspectiveCamera(SCENE_CONFIG.cameraFov, 1, 0.1, 5000)
  private readonly orbitRenderer: THREE.WebGLRenderer
  private readonly glowRenderer: THREE.WebGLRenderer
  private readonly cardRenderer: THREE.WebGLRenderer
  private readonly ambientLight: THREE.AmbientLight
  private readonly primaryLight: THREE.DirectionalLight
  private readonly secondaryLight: THREE.DirectionalLight
  private readonly glowTexture = createGlowTexture()
  private readonly centerCard: CardMesh
  private readonly centerGlow: GlowSprite
  private readonly satellites: SatelliteSceneState[] = []

  private orbitLine: THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial>
  private isDark: boolean
  private centerGlowMode: 'rainbow' | 'green' = 'green'
  private appearanceStartedAt = performance.now()
  private motionElapsed = 0
  private lastFrameTimestamp: number | null = null
  private layout: SceneLayout = {
    orbitRadiusX: 300,
    orbitRadiusY: 150,
    centerCardSize: 82,
    centerCardDepth: 10,
    satelliteCardSize: 56,
    satelliteCardDepth: 8,
  }

  constructor(
    container: HTMLDivElement,
    centerIconCanvas: HTMLCanvasElement,
    modules: PreparedSatelliteModule[],
    isDark: boolean
  ) {
    this.container = container
    this.isDark = isDark
    const createdRenderers: THREE.WebGLRenderer[] = []

    try {
      this.orbitRenderer = this.createRenderer(1)
      createdRenderers.push(this.orbitRenderer)
      this.glowRenderer = this.createRenderer(2)
      createdRenderers.push(this.glowRenderer)
      this.cardRenderer = this.createRenderer(3)
      createdRenderers.push(this.cardRenderer)

      this.ambientLight = new THREE.AmbientLight(0xffffff, 0.6)
      this.primaryLight = new THREE.DirectionalLight(0xffffff, 0.5)
      this.primaryLight.position.set(200, 300, 400)
      this.secondaryLight = new THREE.DirectionalLight(0xdddddd, 0.3)
      this.secondaryLight.position.set(-200, -100, 200)
      this.cardScene.add(this.ambientLight, this.primaryLight, this.secondaryLight)

      this.orbitLine = this.createOrbitLine()
      this.orbitScene.add(this.orbitLine)

      this.centerCard = createCard(centerIconCanvas, isDark)
      this.cardScene.add(this.centerCard)
      this.centerGlow = this.createGlowSprite()
      this.glowScene.add(this.centerGlow)

      modules.forEach((prepared, index) => {
        const card = createCard(prepared.iconCanvas, isDark)
        const glow = this.createGlowSprite()
        this.cardScene.add(card)
        this.glowScene.add(glow)
        this.satellites.push({
          module: prepared.module,
          card,
          glow,
          baseAngle: (index / modules.length) * Math.PI * 2,
          visualState: 'unknown',
        })
      })

      this.updateTheme(isDark)
      this.resize()
    } catch (error) {
      createdRenderers.forEach(renderer => this.releaseRenderer(renderer))
      this.glowTexture.dispose()
      throw error
    }
  }

  private createRenderer(zIndex: number): THREE.WebGLRenderer {
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    try {
      renderer.setClearColor(0x000000, 0)
      renderer.domElement.style.position = 'absolute'
      renderer.domElement.style.inset = '0'
      renderer.domElement.style.width = '100%'
      renderer.domElement.style.height = '100%'
      renderer.domElement.style.zIndex = String(zIndex)
      renderer.domElement.style.pointerEvents = 'none'
      renderer.domElement.setAttribute('aria-hidden', 'true')
      renderer.domElement.tabIndex = -1
      this.container.appendChild(renderer.domElement)
      return renderer
    } catch (error) {
      this.releaseRenderer(renderer)
      throw error
    }
  }

  private releaseRenderer(renderer: THREE.WebGLRenderer): void {
    renderer.domElement.remove()
    renderer.dispose()
    renderer.forceContextLoss()
  }

  private createGlowSprite(): GlowSprite {
    const material = new THREE.SpriteMaterial({
      map: this.glowTexture,
      transparent: true,
      blending: THREE.AdditiveBlending,
      opacity: 0,
    })
    return new THREE.Sprite(material)
  }

  private createOrbitLine(): THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial> {
    const geometry = this.createOrbitGeometry()
    const material = new THREE.LineBasicMaterial({
      color: this.isDark ? 0x555555 : 0xbbbbbb,
      transparent: true,
      opacity: SCENE_CONFIG.orbitOpacity,
    })
    const line = new THREE.Line(geometry, material)
    line.rotation.x = SCENE_CONFIG.orbitTilt
    return line
  }

  private createOrbitGeometry(): THREE.BufferGeometry {
    const curve = new THREE.EllipseCurve(
      0,
      0,
      this.layout.orbitRadiusX,
      this.layout.orbitRadiusY,
      0,
      Math.PI * 2,
      false,
      0
    )
    return new THREE.BufferGeometry().setFromPoints(curve.getPoints(128))
  }

  updateTheme(isDark: boolean): void {
    this.isDark = isDark
    const sideColor = new THREE.Color(isDark ? 0x2a2a2a : 0xf0f0f0)
    const orbitColor = new THREE.Color(isDark ? 0x555555 : 0xbbbbbb)

    ;[this.centerCard, ...this.satellites.map(item => item.card)].forEach(card => {
      card.material.forEach(material => {
        if (material instanceof THREE.MeshStandardMaterial && !material.map) {
          material.color.copy(sideColor)
        }
      })
    })
    this.orbitLine.material.color.copy(orbitColor)
    this.ambientLight.color.setHex(isDark ? 0x404040 : 0xffffff)
    this.primaryLight.color.setHex(isDark ? 0x999999 : 0xffffff)
    this.secondaryLight.color.setHex(isDark ? 0x777777 : 0xdddddd)
  }

  setCenterGlowMode(mode: 'rainbow' | 'green'): void {
    this.centerGlowMode = mode
  }

  setStatuses(statuses: Map<string, SatelliteVisualStatus>): void {
    this.satellites.forEach(state => {
      state.visualState = statuses.get(state.module.typeKey) ?? 'idle'
    })
  }

  pauseMotion(): void {
    this.lastFrameTimestamp = null
  }

  resize(): void {
    const width = Math.max(1, this.container.clientWidth)
    const height = Math.max(1, this.container.clientHeight)
    const pixelRatio = Math.min(window.devicePixelRatio, 2)
    const cameraZ = 520

    this.camera.aspect = width / height
    this.camera.position.set(0, 70, cameraZ)
    this.camera.lookAt(0, 0, 0)
    this.camera.updateProjectionMatrix()

    const worldHeight = 2 * Math.tan((SCENE_CONFIG.cameraFov * Math.PI) / 360) * cameraZ
    const worldWidth = worldHeight * this.camera.aspect
    const cardScale = clamp(Math.min(width / 900, height / 400), 0.72, 1)
    this.layout = {
      orbitRadiusX: clamp(worldWidth * 0.37, 150, 400),
      orbitRadiusY: clamp(worldHeight * 0.29, 105, 170),
      centerCardSize: 90 * cardScale,
      centerCardDepth: 10 * cardScale,
      satelliteCardSize: 60 * cardScale,
      satelliteCardDepth: 8 * cardScale,
    }

    const previousGeometry = this.orbitLine.geometry
    this.orbitLine.geometry = this.createOrbitGeometry()
    previousGeometry.dispose()
    ;[this.orbitRenderer, this.glowRenderer, this.cardRenderer].forEach(renderer => {
      renderer.setPixelRatio(pixelRatio)
      renderer.setSize(width, height, false)
    })
  }

  render(timestamp: number, motionEnabled: boolean, completeAppearance = false): void {
    if (motionEnabled) {
      if (this.lastFrameTimestamp !== null) {
        this.motionElapsed += Math.max(0, timestamp - this.lastFrameTimestamp)
      }
      this.lastFrameTimestamp = timestamp
    } else {
      this.lastFrameTimestamp = null
    }
    const motionTime = this.motionElapsed
    const appearanceElapsed = completeAppearance
      ? Number.POSITIVE_INFINITY
      : Math.max(0, timestamp - this.appearanceStartedAt)
    const satelliteCount = this.satellites.length

    this.satellites.forEach((state, index) => {
      const angle = state.baseAngle + motionTime * SCENE_CONFIG.satelliteOrbitSpeed
      const orbitY = Math.sin(angle) * this.layout.orbitRadiusY
      const floatOffset = motionEnabled
        ? Math.sin(
            motionTime * SCENE_CONFIG.satelliteFloatSpeed * 0.001 +
              index * ((Math.PI * 2) / satelliteCount)
          ) * SCENE_CONFIG.satelliteFloatAmplitude
        : 0
      state.card.position.set(
        Math.cos(angle) * this.layout.orbitRadiusX,
        orbitY * Math.cos(SCENE_CONFIG.orbitTilt) + floatOffset,
        orbitY * Math.sin(SCENE_CONFIG.orbitTilt)
      )
      state.card.lookAt(this.camera.position)
      state.card.rotation.z = 0

      const delay = SCENE_CONFIG.cardAppearDelay * (index + 1)
      const progress = clamp((appearanceElapsed - delay) / SCENE_CONFIG.cardAppearDuration, 0, 1)
      const appearance = easeOutCubic(progress)
      getFrontMaterial(state.card).opacity = appearance
      state.card.scale.set(
        this.layout.satelliteCardSize * appearance,
        this.layout.satelliteCardSize * appearance,
        this.layout.satelliteCardDepth * appearance
      )
      this.updateSatelliteGlow(state, motionTime, motionEnabled)
    })

    const centerProgress = clamp(appearanceElapsed / SCENE_CONFIG.cardAppearDuration, 0, 1)
    const centerAppearance = easeOutCubic(centerProgress)
    const centerFloat = motionEnabled
      ? Math.sin(motionTime * SCENE_CONFIG.centerFloatSpeed * 0.001) *
        SCENE_CONFIG.centerFloatAmplitude
      : 0
    this.centerCard.position.set(0, centerFloat, 0)
    this.centerCard.lookAt(this.camera.position)
    this.centerCard.rotation.z = 0
    getFrontMaterial(this.centerCard).opacity = centerAppearance
    this.centerCard.scale.set(
      this.layout.centerCardSize * centerAppearance,
      this.layout.centerCardSize * centerAppearance,
      this.layout.centerCardDepth * centerAppearance
    )
    this.updateCenterGlow(motionTime, motionEnabled)

    this.orbitRenderer.render(this.orbitScene, this.camera)
    this.glowRenderer.render(this.glowScene, this.camera)
    this.cardRenderer.render(this.cardScene, this.camera)
  }

  private updateSatelliteGlow(
    state: SatelliteSceneState,
    timestamp: number,
    motionEnabled: boolean
  ): void {
    const cardSize = this.layout.satelliteCardSize
    const baseScale = cardSize * SCENE_CONFIG.glowSizeMultiplier
    const breathe = motionEnabled ? 0.5 + 0.5 * Math.sin(timestamp * 0.003) : 0.5
    const material = state.glow.material

    state.glow.position.set(
      state.card.position.x,
      state.card.position.y,
      state.card.position.z - cardSize * 0.08
    )

    if (state.visualState === 'running') {
      material.color.setHex(0x6ce08a)
      material.opacity = 0.4 + breathe * 0.55
      state.glow.scale.setScalar(baseScale * (1 + breathe * 0.12))
      return
    }
    if (state.visualState === 'warning') {
      material.color.setHex(0xffc247)
      material.opacity = 0.4 + breathe * 0.32
      state.glow.scale.setScalar(baseScale * 1.08 * (1 + breathe * 0.12))
      return
    }
    if (state.visualState === 'failed') {
      material.color.setHex(0xff5a5f)
      material.opacity = 0.52
      state.glow.scale.setScalar(baseScale * 1.08)
      return
    }
    if (state.visualState === 'queued') {
      material.color.setHex(0x6ce08a)
      material.opacity = 0.62
      state.glow.scale.setScalar(baseScale)
      return
    }

    material.opacity = 0
  }

  private updateCenterGlow(timestamp: number, motionEnabled: boolean): void {
    const baseScale = this.layout.centerCardSize * SCENE_CONFIG.glowSizeMultiplier
    const material = this.centerGlow.material
    this.centerGlow.position.set(
      this.centerCard.position.x,
      this.centerCard.position.y,
      this.centerCard.position.z - this.layout.centerCardSize * 0.08
    )

    if (this.centerGlowMode === 'rainbow') {
      const flash = motionEnabled ? 0.5 + 0.5 * Math.sin(timestamp * 0.006) : 0.5
      const hue = motionEnabled ? (timestamp * 0.0008) % 1 : 0.08
      material.color.setHSL(hue, 0.75, 0.6)
      material.opacity = 0.58 + flash * 0.34
      this.centerGlow.scale.setScalar(baseScale * (0.82 + flash * 0.1))
      return
    }

    material.color.setHex(0x6ce08a)
    material.opacity = 0.85
    this.centerGlow.scale.setScalar(baseScale * 0.85)
  }

  dispose(): void {
    const disposedGeometries = new Set<THREE.BufferGeometry>()
    const disposedMaterials = new Set<THREE.Material>()
    const disposedTextures = new Set<THREE.Texture>()

    const disposeMaterial = (material: THREE.Material) => {
      if (disposedMaterials.has(material)) return
      disposedMaterials.add(material)
      const materialWithMap = material as THREE.Material & { map?: THREE.Texture | null }
      if (materialWithMap.map && !disposedTextures.has(materialWithMap.map)) {
        disposedTextures.add(materialWithMap.map)
        materialWithMap.map.dispose()
      }
      material.dispose()
    }

    ;[this.orbitScene, this.glowScene, this.cardScene].forEach(scene => {
      scene.traverse(object => {
        const resourceOwner = object as THREE.Object3D & {
          geometry?: THREE.BufferGeometry
          material?: THREE.Material | THREE.Material[]
        }
        if (resourceOwner.geometry && !disposedGeometries.has(resourceOwner.geometry)) {
          disposedGeometries.add(resourceOwner.geometry)
          resourceOwner.geometry.dispose()
        }
        if (Array.isArray(resourceOwner.material)) {
          resourceOwner.material.forEach(disposeMaterial)
        } else if (resourceOwner.material) {
          disposeMaterial(resourceOwner.material)
        }
      })
      scene.clear()
    })
    ;[this.orbitRenderer, this.glowRenderer, this.cardRenderer].forEach(renderer =>
      this.releaseRenderer(renderer)
    )
  }
}
