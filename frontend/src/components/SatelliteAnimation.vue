<template>
  <div ref="container" class="satellite-container">
    <div v-if="loading" class="loading-spinner"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useTheme } from '@/composables/useTheme'
import { useLowPerfMode } from '@/composables/useLowPerfMode'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { satelliteModules, centerIconUrl } from '@/composables/satellite-config'
import {
  getSatelliteModuleStatuses,
  type SatelliteModuleStatus,
} from '@/composables/useSatelliteStatus'
import type { ScriptType } from '@/types/script'
import { Service } from '@/api'
import * as THREE from 'three'

const logger = window.electronAPI.getLogger('卫星动画')

const CONFIG = {
  // 尺寸自适应：不再使用固定容器高度/轨道半径，
  // 轨道半径由容器宽高比推导（见 computeLayout），任何宽度下轨道不裁切
  fallbackWidth: 800,
  fallbackHeight: 420,
  baseAspect: 2, // 基准设计宽高比（800x400），用于卡片/辉光比例基准
  minCardScale: 0.7,
  maxCardScale: 1.6,
  orbitEdgePadding: 14, // 世界单位：轨道极点（含卫星卡半宽）与可视边缘的留白
  orbitVerticalFill: 0.92, // 轨道纵向可用高度占可视高度的比例
  orbitTilt: 0.35,
  orbitOpacity: 0.4,
  centerCardSize: 90,
  centerCardDepth: 10,
  satelliteCardSize: 60,
  satelliteCardDepth: 8,
  satelliteOrbitSpeed: 0.0006,
  satelliteFloatAmplitude: 10,
  satelliteFloatSpeed: 1.2,
  centerFloatAmplitude: 4,
  centerFloatSpeed: 0.8,
  cameraFov: 50,
  cameraPosition: { x: 0, y: 80, z: 500 },
  cardAppearDelay: 150,
  cardAppearDuration: 400,
  glowSizeMultiplier: 3.5,
  activityGlowZOffset: -5,
  errorGlowZOffset: -3,
  statusUpdateInterval: 10000,
}

/**
 * 随容器尺寸推导的场景布局（世界单位）。
 * 相机固定不动，容器宽高比只改变视锥在 z=0 平面的可视世界宽度；
 * 轨道半径、卡片/辉光比例均相对可视尺寸计算，而非绝对像素。
 */
interface SceneLayout {
  width: number
  height: number
  orbitRadiusX: number
  orbitRadiusY: number
  cardScale: number
  centerCardSize: number
  satelliteCardSize: number
  satelliteFloatAmplitude: number
  centerFloatAmplitude: number
}

function computeLayout(width: number, height: number): SceneLayout {
  const w = Math.max(width, 1)
  const h = Math.max(height, 1)
  const { x, y, z } = CONFIG.cameraPosition
  const cameraDistance = Math.hypot(x, y, z)
  // 垂直 fov 固定 → 可视世界高度恒定；宽度随容器宽高比伸缩
  const halfFovRad = THREE.MathUtils.degToRad(CONFIG.cameraFov / 2)
  const visibleHeight = 2 * cameraDistance * Math.tan(halfFovRad)
  const visibleWidth = visibleHeight * (w / h)

  // 卡片/辉光比例：相对基准宽高比的可视宽度开方缩放，避免宽屏下卡片过大或窄屏下过小
  const baseVisibleWidth = visibleHeight * CONFIG.baseAspect
  const cardScale = THREE.MathUtils.clamp(
    Math.sqrt(visibleWidth / baseVisibleWidth),
    CONFIG.minCardScale,
    CONFIG.maxCardScale
  )

  const satelliteCardSize = CONFIG.satelliteCardSize * cardScale
  const satelliteFloatAmplitude = CONFIG.satelliteFloatAmplitude * cardScale
  const satelliteHalf = satelliteCardSize / 2

  // 横向：轨道极点 + 卫星卡半宽 + 留白 ≤ 可视半宽 → 铺满且不裁切
  const orbitRadiusX = Math.max(
    visibleWidth / 2 - satelliteHalf - CONFIG.orbitEdgePadding,
    satelliteCardSize
  )
  // 纵向：投影半径 rY*cos(tilt) + 浮动幅度 + 卫星卡半宽 ≤ 可视半高 * orbitVerticalFill
  const orbitRadiusY = Math.max(
    ((visibleHeight / 2) * CONFIG.orbitVerticalFill - satelliteHalf - satelliteFloatAmplitude) /
      Math.cos(CONFIG.orbitTilt),
    satelliteCardSize
  )

  return {
    width: w,
    height: h,
    orbitRadiusX,
    orbitRadiusY,
    cardScale,
    centerCardSize: CONFIG.centerCardSize * cardScale,
    satelliteCardSize,
    satelliteFloatAmplitude,
    centerFloatAmplitude: CONFIG.centerFloatAmplitude * cardScale,
  }
}

const container = ref<HTMLDivElement | null>(null)
const loading = ref(true)

let layout: SceneLayout = computeLayout(CONFIG.fallbackWidth, CONFIG.fallbackHeight)
let resizeObserver: ResizeObserver | null = null
// 卡片出现动画是否已完成（完成后 resize 需手动同步新的 cardScale）
let cardsRevealed = false

function measureContainer(): { width: number; height: number } {
  const el = container.value
  return {
    width: el?.clientWidth || CONFIG.fallbackWidth,
    height: el?.clientHeight || CONFIG.fallbackHeight,
  }
}

let orbitScene: THREE.Scene | null = null
let glowScene: THREE.Scene | null = null
let cardScene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let orbitRenderer: THREE.WebGLRenderer | null = null
let glowRenderer: THREE.WebGLRenderer | null = null
let cardRenderer: THREE.WebGLRenderer | null = null
let animationFrameId: number | null = null
let appearAnimationFrameId: number | null = null
let isUnmounted = false

type CardMesh = THREE.Mesh<THREE.BoxGeometry, THREE.Material[]>

let satellites: CardMesh[] = []
let orbitLine: THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial> | null = null
let centerCard: CardMesh | null = null

interface SatelliteState {
  type: ScriptType
  activityGlowSprite: THREE.Sprite | null
  errorGlowSprite: THREE.Sprite | null
  status: SatelliteModuleStatus
}
let satelliteStates: Map<CardMesh, SatelliteState> = new Map()
let centerGlowSprite: THREE.Sprite | null = null
let updateInterval: ReturnType<typeof setInterval> | null = null
const centerGlowMode = ref<'rainbow' | 'green'>('green')

const { isDark } = useTheme()
const { isLowPerf } = useLowPerfMode()
const { getScripts } = useScriptRegistryApi()
const prefersReducedMotion = ref(false)
const motionAllowed = computed(() => !isLowPerf.value && !prefersReducedMotion.value)
let reducedMotionQuery: MediaQueryList | null = null

const syncReducedMotion = (event: MediaQueryListEvent) => {
  prefersReducedMotion.value = event.matches
}

onUnmounted(() => {
  isUnmounted = true
  resizeObserver?.disconnect()
  resizeObserver = null
  window.removeEventListener('resize', handleResize)
  reducedMotionQuery?.removeEventListener?.('change', syncReducedMotion)
  reducedMotionQuery = null
  if (animationFrameId !== null) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
  if (appearAnimationFrameId !== null) {
    cancelAnimationFrame(appearAnimationFrameId)
    appearAnimationFrameId = null
  }

  if (updateInterval) {
    clearInterval(updateInterval)
    updateInterval = null
  }

  disposeSceneResources(orbitScene)
  disposeSceneResources(glowScene)
  disposeSceneResources(cardScene)
  disposeRenderer(orbitRenderer)
  disposeRenderer(glowRenderer)
  disposeRenderer(cardRenderer)

  orbitScene = null
  glowScene = null
  cardScene = null
  camera = null
  orbitRenderer = null
  glowRenderer = null
  cardRenderer = null
  satellites = []
  orbitLine = null
  centerCard = null
  centerGlowSprite = null
  satelliteStates.clear()
})

function disposeRenderer(renderer: THREE.WebGLRenderer | null): void {
  if (!renderer) return
  const el = renderer.domElement
  if (el.parentElement) {
    el.parentElement.removeChild(el)
  }
  renderer.dispose()
}

function disposeMaterial(
  material: THREE.Material,
  disposedMaterials: Set<THREE.Material>,
  disposedTextures: Set<THREE.Texture>
): void {
  if (disposedMaterials.has(material)) return
  disposedMaterials.add(material)

  const materialWithMap = material as THREE.Material & { map?: THREE.Texture | null }
  if (materialWithMap.map && !disposedTextures.has(materialWithMap.map)) {
    disposedTextures.add(materialWithMap.map)
    materialWithMap.map.dispose()
  }
  material.dispose()
}

function disposeSceneResources(scene: THREE.Scene | null): void {
  if (!scene) return
  const disposedGeometries = new Set<THREE.BufferGeometry>()
  const disposedMaterials = new Set<THREE.Material>()
  const disposedTextures = new Set<THREE.Texture>()

  scene.traverse(object => {
    const objectWithResources = object as THREE.Object3D & {
      geometry?: THREE.BufferGeometry
      material?: THREE.Material | THREE.Material[]
    }

    if (objectWithResources.geometry && !disposedGeometries.has(objectWithResources.geometry)) {
      disposedGeometries.add(objectWithResources.geometry)
      objectWithResources.geometry.dispose()
    }

    const { material } = objectWithResources
    if (Array.isArray(material)) {
      material.forEach(mat => disposeMaterial(mat, disposedMaterials, disposedTextures))
    } else if (material) {
      disposeMaterial(material, disposedMaterials, disposedTextures)
    }
  })

  scene.clear()
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

async function loadImageToCanvas(url: string): Promise<HTMLCanvasElement> {
  return new Promise(resolve => {
    const img = new Image()
    let settled = false
    const finish = (canvas: HTMLCanvasElement) => {
      if (settled) return
      settled = true
      resolve(canvas)
    }
    const fallback = () => {
      const canvas = document.createElement('canvas')
      canvas.width = 64
      canvas.height = 64
      const ctx = canvas.getContext('2d')!
      ctx.fillStyle = '#888888'
      ctx.fillRect(0, 0, 64, 64)
      finish(canvas)
    }
    const timer = window.setTimeout(fallback, 5000)
    img.onload = () => {
      window.clearTimeout(timer)
      const canvas = document.createElement('canvas')
      canvas.width = img.width
      canvas.height = img.height
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(img, 0, 0)
      finish(canvas)
    }
    img.onerror = () => {
      window.clearTimeout(timer)
      fallback()
    }
    img.src = url
  })
}

function getThemeColors() {
  if (isDark.value) {
    return {
      sideColor: '#2a2a2a',
      ambientColor: 0x404040,
      light1Color: 0x999999,
      light2Color: 0x777777,
      orbitColor: 0x555555,
    }
  }
  return {
    sideColor: '#f0f0f0',
    ambientColor: 0xffffff,
    light1Color: 0xffffff,
    light2Color: 0xdddddd,
    orbitColor: 0xbbbbbb,
  }
}

async function createCard(size: number, depth: number, imageUrl: string): Promise<CardMesh> {
  const canvas = await loadImageToCanvas(imageUrl)
  const texture = new THREE.CanvasTexture(canvas)
  texture.needsUpdate = true
  texture.colorSpace = THREE.SRGBColorSpace

  const colors = getThemeColors()
  const frontMat = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    opacity: 0,
  })
  const sideMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color(colors.sideColor),
    roughness: 0.9,
    metalness: 0,
  })

  const materials: THREE.Material[] = [sideMat, sideMat, sideMat, sideMat, frontMat, sideMat]
  const box = new THREE.Mesh<THREE.BoxGeometry, THREE.Material[]>(
    new THREE.BoxGeometry(size, size, depth),
    materials
  )
  box.scale.set(0.01, 0.01, 0.01)
  box.castShadow = false
  box.receiveShadow = false
  return box
}

function createEllipticalOrbit(): THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial> {
  // 单位圆几何 + scale 表达椭圆半径：resize 时只需更新 scale，无需重建几何
  const curve = new THREE.EllipseCurve(0, 0, 1, 1, 0, 2 * Math.PI, false, 0)
  const points = curve.getPoints(128)
  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  const colors = getThemeColors()
  const material = new THREE.LineBasicMaterial({
    color: colors.orbitColor,
    transparent: true,
    opacity: CONFIG.orbitOpacity,
  })
  const line = new THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial>(geometry, material)
  line.scale.set(layout.orbitRadiusX, layout.orbitRadiusY, 1)
  line.rotation.x = CONFIG.orbitTilt
  return line
}

function getCardFrontMaterial(card: CardMesh): THREE.MeshBasicMaterial | null {
  const material = card.material[4]
  return material instanceof THREE.MeshBasicMaterial ? material : null
}

function updateAllThemeColors() {
  const colors = getThemeColors()
  const sideColor = new THREE.Color(colors.sideColor)
  const orbitColor = new THREE.Color(colors.orbitColor)

  cardScene?.traverse((obj: any) => {
    if (obj.isMesh && obj.material) {
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material]
      for (const mat of mats) {
        if (mat.isMeshStandardMaterial && !mat.map) {
          mat.color.copy(sideColor)
        }
      }
    }
    if (obj.isAmbientLight) obj.color.setHex(colors.ambientColor)
    if (obj.isDirectionalLight) {
      obj.color.setHex(obj === obj.parent?.children[1] ? colors.light1Color : colors.light2Color)
    }
  })

  orbitScene?.traverse((obj: any) => {
    if (obj.isLine && obj.material) {
      obj.material.color.copy(orbitColor)
    }
  })
}

async function initScene(): Promise<void> {
  if (!container.value) return
  try {
    await initSceneInternal()
  } catch (err) {
    logger.error(`初始化场景失败: ${String(err)}`)
  } finally {
    loading.value = false
  }
}

async function initSceneInternal(): Promise<void> {
  if (!container.value) return

  let userScripts: Awaited<ReturnType<typeof getScripts>> = []
  try {
    userScripts = await getScripts()
  } catch (err) {
    logger.warn(`获取脚本列表失败，按空集合处理: ${String(err)}`)
  }

  const userScriptTypes = new Set<ScriptType>(userScripts.map(s => s.type as ScriptType))
  const enabledModules = satelliteModules.filter(
    m => m.enabled && userScriptTypes.has(m.scriptType)
  )
  const numSatellites = enabledModules.length

  if (numSatellites === 0) {
    logger.info('没有可显示的卫星模块，仅渲染中心图标和轨道')
  }

  const { width: w, height: h } = measureContainer()
  layout = computeLayout(w, h)

  camera = new THREE.PerspectiveCamera(CONFIG.cameraFov, w / h, 0.1, 5000)
  camera.position.set(CONFIG.cameraPosition.x, CONFIG.cameraPosition.y, CONFIG.cameraPosition.z)
  camera.lookAt(0, 0, 0)

  orbitScene = new THREE.Scene()
  orbitRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  orbitRenderer.setSize(w, h)
  orbitRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  orbitRenderer.setClearColor(0x000000, 0)
  orbitRenderer.domElement.style.position = 'absolute'
  orbitRenderer.domElement.style.top = '0'
  orbitRenderer.domElement.style.left = '0'
  orbitRenderer.domElement.style.zIndex = '1'
  container.value.appendChild(orbitRenderer.domElement)

  glowScene = new THREE.Scene()
  glowRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  glowRenderer.setSize(w, h)
  glowRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  glowRenderer.setClearColor(0x000000, 0)
  glowRenderer.domElement.style.position = 'absolute'
  glowRenderer.domElement.style.top = '0'
  glowRenderer.domElement.style.left = '0'
  glowRenderer.domElement.style.zIndex = '1.5'
  glowRenderer.domElement.style.pointerEvents = 'none'
  container.value.appendChild(glowRenderer.domElement)

  cardScene = new THREE.Scene()
  cardRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  cardRenderer.setSize(w, h)
  cardRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  cardRenderer.setClearColor(0x000000, 0)
  cardRenderer.domElement.style.position = 'absolute'
  cardRenderer.domElement.style.top = '0'
  cardRenderer.domElement.style.left = '0'
  cardRenderer.domElement.style.zIndex = '2'
  cardRenderer.domElement.style.pointerEvents = 'none'
  container.value.appendChild(cardRenderer.domElement)

  const colors = getThemeColors()
  const ambient = new THREE.AmbientLight(colors.ambientColor, 0.6)
  cardScene.add(ambient)
  const dl1 = new THREE.DirectionalLight(colors.light1Color, 0.5)
  dl1.position.set(200, 300, 400)
  cardScene.add(dl1)
  const dl2 = new THREE.DirectionalLight(colors.light2Color, 0.3)
  dl2.position.set(-200, -100, 200)
  cardScene.add(dl2)

  orbitLine = createEllipticalOrbit()
  orbitScene.add(orbitLine)

  const glowTexture = createGlowTexture()

  centerCard = await createCard(CONFIG.centerCardSize, CONFIG.centerCardDepth, centerIconUrl)
  centerCard.position.set(0, 0, 0)
  cardScene.add(centerCard)

  const centerGlowMaterial = new THREE.SpriteMaterial({
    map: glowTexture,
    transparent: true,
    blending: THREE.AdditiveBlending,
    color: new THREE.Color(0xffaa66),
    opacity: 0,
  })
  const centerGlow = new THREE.Sprite(centerGlowMaterial)
  centerGlow.scale.set(
    layout.centerCardSize * CONFIG.glowSizeMultiplier * 0.9,
    layout.centerCardSize * CONFIG.glowSizeMultiplier * 0.9,
    1
  )
  centerGlowSprite = centerGlow
  glowScene.add(centerGlow)

  for (let i = 0; i < numSatellites; i++) {
    const module = enabledModules[i]
    const sat = await createCard(
      CONFIG.satelliteCardSize,
      CONFIG.satelliteCardDepth,
      module.iconUrl
    )
    sat.userData.angle = (i / numSatellites) * Math.PI * 2
    sat.userData.index = i
    satellites.push(sat)
    cardScene.add(sat)

    const activityGlowMaterial = new THREE.SpriteMaterial({
      map: glowTexture,
      transparent: true,
      blending: THREE.AdditiveBlending,
      color: new THREE.Color(0x6ce08a),
      opacity: 0,
    })
    const activityGlowSprite = new THREE.Sprite(activityGlowMaterial)
    activityGlowSprite.scale.set(
      layout.satelliteCardSize * CONFIG.glowSizeMultiplier,
      layout.satelliteCardSize * CONFIG.glowSizeMultiplier,
      1
    )
    glowScene.add(activityGlowSprite)

    const errorGlowMaterial = new THREE.SpriteMaterial({
      map: glowTexture,
      transparent: true,
      blending: THREE.AdditiveBlending,
      color: new THREE.Color(0xff5a5f),
      opacity: 0,
    })
    const errorGlowSprite = new THREE.Sprite(errorGlowMaterial)
    errorGlowSprite.scale.set(
      layout.satelliteCardSize * CONFIG.glowSizeMultiplier * 1.08,
      layout.satelliteCardSize * CONFIG.glowSizeMultiplier * 1.08,
      1
    )
    glowScene.add(errorGlowSprite)

    satelliteStates.set(sat, {
      type: module.scriptType,
      activityGlowSprite,
      errorGlowSprite,
      status: {
        queued: false,
        running: false,
        errorVisible: false,
      },
    })
  }

  loading.value = false

  animateAppear()
}

function animateAppear() {
  if (!motionAllowed.value) {
    revealCardsImmediately()
    return
  }

  const appearStart = Date.now()
  const totalDuration = CONFIG.cardAppearDelay * (satellites.length + 1) + CONFIG.cardAppearDuration

  function step() {
    if (isUnmounted) return

    const elapsed = Date.now() - appearStart
    if (elapsed > totalDuration) {
      revealCardsImmediately()
      return
    }

    // 几何按基准尺寸创建，实际大小随布局比例（layout.cardScale）缩放
    const centerProgress = Math.min(1, elapsed / CONFIG.cardAppearDuration)
    const easedCenter = easeOutCubic(centerProgress)
    if (centerCard) {
      const frontMaterial = getCardFrontMaterial(centerCard)
      if (frontMaterial) frontMaterial.opacity = easedCenter
      centerCard.scale.setScalar(easedCenter * layout.cardScale)
    }

    satellites.forEach((sat, i) => {
      const delay = CONFIG.cardAppearDelay * (i + 1)
      const progress = Math.min(1, (elapsed - delay) / CONFIG.cardAppearDuration)
      const eased = easeOutCubic(Math.max(0, progress))
      const frontMaterial = getCardFrontMaterial(sat)
      if (frontMaterial) frontMaterial.opacity = eased
      sat.scale.setScalar(eased * layout.cardScale)
    })

    appearAnimationFrameId = requestAnimationFrame(step)
  }

  appearAnimationFrameId = requestAnimationFrame(step)
}

function revealCardsImmediately(): void {
  cardsRevealed = true
  if (centerCard) {
    const frontMaterial = getCardFrontMaterial(centerCard)
    if (frontMaterial) frontMaterial.opacity = 1
    centerCard.scale.setScalar(layout.cardScale)
  }
  satellites.forEach(satellite => {
    const frontMaterial = getCardFrontMaterial(satellite)
    if (frontMaterial) frontMaterial.opacity = 1
    satellite.scale.setScalar(layout.cardScale)
  })
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

function animate(): void {
  if (isUnmounted || !camera) return

  const time = motionAllowed.value ? Date.now() : 0
  const numSatellites = satellites.length

  for (let i = 0; i < numSatellites; i++) {
    const sat = satellites[i]
    const angle = sat.userData.angle + time * CONFIG.satelliteOrbitSpeed
    const x = Math.cos(angle) * layout.orbitRadiusX
    const y = Math.sin(angle) * layout.orbitRadiusY
    const tiltedY = y * Math.cos(CONFIG.orbitTilt)
    const z = y * Math.sin(CONFIG.orbitTilt)
    const floatOffset =
      Math.sin(time * CONFIG.satelliteFloatSpeed * 0.001 + i * ((Math.PI * 2) / numSatellites)) *
      layout.satelliteFloatAmplitude

    sat.position.set(x, tiltedY + floatOffset, z)
    sat.lookAt(camera.position)
    sat.rotation.z = 0
  }

  if (centerCard) {
    centerCard.lookAt(camera.position)
    centerCard.rotation.z = 0
    const centerFloat =
      Math.sin(time * CONFIG.centerFloatSpeed * 0.001) * layout.centerFloatAmplitude
    centerCard.position.y = centerFloat
  }

  satelliteStates.forEach((state, sat) => {
    if (state.activityGlowSprite) {
      state.activityGlowSprite.position.set(
        sat.position.x,
        sat.position.y,
        sat.position.z + CONFIG.activityGlowZOffset
      )

      const baseScale = layout.satelliteCardSize * CONFIG.glowSizeMultiplier
      if (state.status.errorVisible) {
        state.activityGlowSprite.material.opacity = 0
      } else if (state.status.running) {
        const breathe = 0.5 + 0.5 * Math.sin(time * 0.003)
        const pulseFactor = 1 + breathe * 0.12
        state.activityGlowSprite.material.color.setHex(0x6ce08a)
        state.activityGlowSprite.material.opacity = 0.4 + breathe * 0.55
        state.activityGlowSprite.scale.set(baseScale * pulseFactor, baseScale * pulseFactor, 1)
      } else if (state.status.queued) {
        state.activityGlowSprite.material.color.setHex(0x6ce08a)
        state.activityGlowSprite.material.opacity = 0.62
        state.activityGlowSprite.scale.set(baseScale, baseScale, 1)
      } else {
        state.activityGlowSprite.material.opacity = 0
      }
    }

    if (state.errorGlowSprite) {
      state.errorGlowSprite.position.set(
        sat.position.x,
        sat.position.y,
        sat.position.z + CONFIG.errorGlowZOffset
      )

      if (state.status.errorVisible) {
        const faintPulse = state.status.running
          ? 0.5 + 0.5 * Math.sin(time * 0.003)
          : 0.5 + 0.5 * Math.sin(time * 0.0016)
        const baseScale = layout.satelliteCardSize * CONFIG.glowSizeMultiplier * 1.08
        const pulseFactor = state.status.running ? 1 + faintPulse * 0.12 : 1 + faintPulse * 0.04
        state.errorGlowSprite.material.color.setHex(state.status.running ? 0xffc247 : 0xff5a5f)
        state.errorGlowSprite.material.opacity = state.status.running
          ? 0.4 + faintPulse * 0.32
          : 0.42
        state.errorGlowSprite.scale.set(baseScale * pulseFactor, baseScale * pulseFactor, 1)
      } else {
        state.errorGlowSprite.material.opacity = 0
      }
    }
  })

  if (centerGlowSprite && centerCard) {
    centerGlowSprite.position.set(
      centerCard.position.x,
      centerCard.position.y,
      centerCard.position.z + CONFIG.activityGlowZOffset
    )

    if (centerGlowMode.value === 'rainbow') {
      const hue = (time * 0.0008) % 1
      const flash = 0.5 + 0.5 * Math.sin(time * 0.006)
      centerGlowSprite.material.color.setHSL(hue, 0.75, 0.6)
      centerGlowSprite.material.opacity = 0.58 + flash * 0.34
      centerGlowSprite.scale.setScalar(
        layout.centerCardSize * (CONFIG.glowSizeMultiplier * 0.82 + flash * 0.1)
      )
    } else {
      centerGlowSprite.material.color.setHex(0x6ce08a)
      centerGlowSprite.material.opacity = 0.85
      centerGlowSprite.scale.setScalar(layout.centerCardSize * CONFIG.glowSizeMultiplier * 0.85)
    }
  }

  if (orbitRenderer && orbitScene) orbitRenderer.render(orbitScene, camera)
  if (glowRenderer && glowScene) glowRenderer.render(glowScene, camera)
  if (cardRenderer && cardScene) cardRenderer.render(cardScene, camera)

  animationFrameId = motionAllowed.value ? requestAnimationFrame(animate) : null
}

function handleResize(): void {
  if (!container.value || !camera) return
  const { width: w, height: h } = measureContainer()
  layout = computeLayout(w, h)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  if (orbitRenderer) orbitRenderer.setSize(w, h)
  if (glowRenderer) glowRenderer.setSize(w, h)
  if (cardRenderer) cardRenderer.setSize(w, h)
  orbitLine?.scale.set(layout.orbitRadiusX, layout.orbitRadiusY, 1)
  // 出现动画已结束时，卡片比例需随新布局同步；动画进行中由每帧 eased * cardScale 覆盖
  if (cardsRevealed) revealCardsImmediately()
  if (!motionAllowed.value) animate()
}

watch(isDark, () => {
  updateAllThemeColors()
  if (!motionAllowed.value) animate()
})

watch(motionAllowed, enabled => {
  if (enabled) {
    if (animationFrameId === null) animate()
    return
  }

  if (animationFrameId !== null) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
  if (appearAnimationFrameId !== null) {
    cancelAnimationFrame(appearAnimationFrameId)
    appearAnimationFrameId = null
  }
  revealCardsImmediately()
  animate()
})

async function updateSatelliteStates() {
  try {
    const statusByType = await getSatelliteModuleStatuses()

    satelliteStates.forEach(state => {
      state.status = statusByType.get(state.type) ?? {
        queued: false,
        running: false,
        errorVisible: false,
      }
    })
    if (!motionAllowed.value) animate()
  } catch (error) {
    logger.error(`更新状态失败: ${String(error)}`)
  }
}

onMounted(async () => {
  isUnmounted = false
  if (typeof window.matchMedia === 'function') {
    reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    prefersReducedMotion.value = reducedMotionQuery.matches
    reducedMotionQuery.addEventListener?.('change', syncReducedMotion)
  }
  try {
    await initScene()
  } catch (e) {
    logger.error(`init failed: ${String(e)}`)
  }
  animate()
  // 容器尺寸自适应：优先 ResizeObserver（卡片跨度/容器查询变化也会触发），
  // 不可用时回退 window resize
  if (typeof ResizeObserver !== 'undefined' && container.value) {
    resizeObserver = new ResizeObserver(() => handleResize())
    resizeObserver.observe(container.value)
  } else {
    window.addEventListener('resize', handleResize)
  }

  updateSatelliteStates()
  updateInterval = setInterval(updateSatelliteStates, CONFIG.statusUpdateInterval)

  // 检查更新状态
  const version = import.meta.env.VITE_APP_VERSION || '1.0.0'
  try {
    const updateRes = await Service.checkUpdateApiUpdateCheckPost({
      current_version: version,
      if_force: false,
    })
    if (updateRes.code === 200 && updateRes.if_need_update) {
      centerGlowMode.value = 'rainbow'
    }
  } catch {
    // 静默失败，保持绿色
  }
})
</script>

<style scoped>
.satellite-container {
  width: 100%;
  /* 高度跟随父卡片（flex 列布局）自适应，不再固定像素高度 */
  flex: 1 1 auto;
  min-height: 300px;
  position: relative;
  overflow: hidden;
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
