<template>
  <div ref="container" class="satellite-container">
    <div v-if="loading" class="loading-spinner"></div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '@/composables/useTheme'
import { useScriptApi } from '@/composables/useScriptApi'
import { satelliteModules, centerIconUrl } from '@/composables/satellite-config'
import { useSatelliteStatus, type SatelliteModuleStatus } from '@/composables/useSatelliteStatus'
import type { ScriptType } from '@/types/script'
import { requestUpdateCheck } from '@/composables/useUpdateChecker'
import { usePerformanceStore } from '@/stores/performance'
import { connectionState, onConnected } from '@/services/websocket/connection'
import { createAnimationFrameScheduler } from './satelliteAnimationLoop'
import {
  createExplosionFragmentMotion,
  getExplosionEffectProgress,
  getExplosionPhase,
  SATELLITE_EXPLOSION_CONFIG,
  type ExplosionFragmentMotion,
} from './satelliteExplosion'
import * as THREE from 'three'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('卫星动画')

const CONFIG = {
  containerHeight: 400,
  orbitRadiusX: 400,
  orbitRadiusY: 170,
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
  cardAppearDelay: 150,
  cardAppearDuration: 400,
  glowSizeMultiplier: 3.5,
  activityGlowZOffset: -5,
  errorGlowZOffset: -3,
  statusUpdateInterval: 10000,
}

const container = ref<HTMLDivElement | null>(null)
const loading = ref(true)

let orbitScene: THREE.Scene | null = null
let glowScene: THREE.Scene | null = null
let cardScene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let orbitRenderer: THREE.WebGLRenderer | null = null
let glowRenderer: THREE.WebGLRenderer | null = null
let cardRenderer: THREE.WebGLRenderer | null = null
let appearAnimationFrameId: number | null = null
let allowLowPowerFrame = false
let isUnmounted = false
const animationFrameScheduler = createAnimationFrameScheduler(
  requestAnimationFrame,
  cancelAnimationFrame
)

type CardMesh = THREE.Mesh<THREE.BoxGeometry, THREE.Material[]>

let satellites: CardMesh[] = []
let orbitLine: THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial> | null = null
let centerCard: CardMesh | null = null
let centerIconCanvas: HTMLCanvasElement | null = null
let centerIconRainbow = false
let centerPressed = false
let centerScaleX = 1
let centerScaleY = 1
let centerRainbowCanvas: HTMLCanvasElement | null = null
let centerRainbowTexture: THREE.CanvasTexture | null = null
let centerRainbowExtent: OpaqueExtent | null = null
let centerRainbowStartedAt = 0

interface SatelliteState {
  type: ScriptType
  activityGlowSprite: THREE.Sprite | null
  errorGlowSprite: THREE.Sprite | null
  status: SatelliteModuleStatus
}
// 卫星状态来自任务运行时常驻订阅（WS 增量 + HTTP 快照兜底）
const { statuses: satelliteStatuses, refresh: refreshSatelliteStatuses } = useSatelliteStatus()

let satelliteStates: Map<CardMesh, SatelliteState> = new Map()
let centerGlowSprite: THREE.Sprite | null = null
let glowTexture: THREE.CanvasTexture | null = null
let updateInterval: ReturnType<typeof setInterval> | null = null
// 预览用：临时把默认值设成 rainbow 直接看效果，看完改回 'green'
const centerGlowMode = ref<'rainbow' | 'green'>('green')
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()

interface ExplosionFragment {
  mesh: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>
  motion: ExplosionFragmentMotion
  origin: THREE.Vector3
}

interface SatelliteExplosion {
  group: THREE.Group
  effectScene: THREE.Scene
  fragments: ExplosionFragment[]
  flashSprite: THREE.Sprite
  ringMesh: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>
  startTime: number
  originalOpacity: number
  originalScale: THREE.Vector3
  originalVisible: boolean
}

const satelliteExplosions = new Map<CardMesh, SatelliteExplosion>()
type PointerLikeEvent = Pick<MouseEvent, 'clientX' | 'clientY'>

const { isDark } = useTheme()
const { getScripts } = useScriptApi()
const performanceStore = usePerformanceStore()

function stopAnimation() {
  animationFrameScheduler.cancel()
}

function startAnimation() {
  if (isUnmounted || !camera || performanceStore.isLowPower) {
    return
  }

  animationFrameScheduler.request(animate)
}

function stopAppearAnimation() {
  if (appearAnimationFrameId === null) {
    return
  }

  cancelAnimationFrame(appearAnimationFrameId)
  appearAnimationFrameId = null
}

function stopStatusPolling() {
  if (updateInterval === null) {
    return
  }

  clearInterval(updateInterval)
  updateInterval = null
}

function startStatusPolling() {
  if (
    performanceStore.isBackgrounded ||
    updateInterval !== null ||
    connectionState().value === 'open'
  ) {
    return
  }

  // 周期性 HTTP 快照兜底：只在主 WS 没开着时轮询；WS 开着靠 task.* 事件推送
  updateInterval = setInterval(() => void refreshSatelliteStatuses(), CONFIG.statusUpdateInterval)
}

// 后端未就绪（主 WS 未 open）时不发请求：启动遮罩期间立即初始化会把脚本列表与
// 运行快照打向尚未监听的端口，请求直接以 "Network Error" 弹错，卫星也会整场不渲染。
let disposeBackendReadyListener: (() => void) | null = null

function waitBackendReady(): Promise<void> {
  if (connectionState().value === 'open') return Promise.resolve()
  return new Promise(resolve => {
    disposeBackendReadyListener = onConnected(() => {
      disposeBackendReadyListener = null
      resolve()
    })
  })
}

function showCardsImmediately() {
  // 入场到此为止，把帧号清掉：动画循环靠它判断能不能接管中心卡片的 scale
  appearAnimationFrameId = null

  if (centerCard) {
    const frontMaterial = getCardFrontMaterial(centerCard)
    if (frontMaterial) frontMaterial.opacity = 1
    centerCard.scale.set(1, 1, 1)
  }

  satellites.forEach(sat => {
    const frontMaterial = getCardFrontMaterial(sat)
    if (frontMaterial) frontMaterial.opacity = 1
    sat.scale.set(1, 1, 1)
  })
}

function renderCurrentFrame() {
  if (!camera || performanceStore.isBackgrounded) {
    return
  }

  allowLowPowerFrame = true
  animate()
}

function removeCardInteraction() {
  if (!cardRenderer) {
    return
  }

  cardRenderer.domElement.removeEventListener('click', handleSatelliteClick)
  cardRenderer.domElement.removeEventListener('pointermove', handleSatellitePointerMove)
  cardRenderer.domElement.removeEventListener('pointerleave', resetSatelliteCursor)
  cardRenderer.domElement.removeEventListener('pointerdown', handleCardPointerDown)
  cardRenderer.domElement.removeEventListener('pointerup', handleCardPointerUp)
  cardRenderer.domElement.removeEventListener('pointercancel', handleCardPointerUp)
  cardRenderer.domElement.removeEventListener('pointerleave', handleCardPointerUp)
}

function disposeScene() {
  stopAnimation()
  stopAppearAnimation()
  stopStatusPolling()
  removeCardInteraction()
  clearSatelliteExplosions()

  disposeSceneResources(orbitScene)
  disposeSceneResources(glowScene)
  disposeSceneResources(cardScene)

  const disposedRenderers = new Set<THREE.WebGLRenderer>()
  for (const renderer of [orbitRenderer, glowRenderer, cardRenderer]) {
    if (renderer && !disposedRenderers.has(renderer)) {
      disposedRenderers.add(renderer)
      disposeRenderer(renderer)
    }
  }

  glowTexture?.dispose()
  glowTexture = null

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
  allowLowPowerFrame = false
}

function disposeCardMesh(card: CardMesh) {
  const disposedMaterials = new Set<THREE.Material>()
  const disposedTextures = new Set<THREE.Texture>()
  card.geometry.dispose()
  card.material.forEach(material => disposeMaterial(material, disposedMaterials, disposedTextures))
}

onUnmounted(() => {
  isUnmounted = true
  disposeBackendReadyListener?.()
  window.removeEventListener('resize', handleResize)
  disposeScene()
})

function disposeRenderer(renderer: THREE.WebGLRenderer | null): void {
  if (!renderer) return
  const el = renderer.domElement
  if (el.parentElement) {
    el.parentElement.removeChild(el)
  }
  renderer.dispose()
}

function setSatelliteEffectsVisible(sat: CardMesh, visible: boolean) {
  const state = satelliteStates.get(sat)
  if (!state) {
    return
  }

  state.activityGlowSprite && (state.activityGlowSprite.visible = visible)
  state.errorGlowSprite && (state.errorGlowSprite.visible = visible)
}

function setupCardInteraction() {
  if (!cardRenderer) {
    return
  }

  removeCardInteraction()
  const element = cardRenderer.domElement
  element.setAttribute('aria-label', '脚本卫星互动区域')
  element.style.cursor = 'default'
  element.style.touchAction = 'manipulation'
  element.addEventListener('click', handleSatelliteClick)
  element.addEventListener('pointermove', handleSatellitePointerMove)
  element.addEventListener('pointerleave', resetSatelliteCursor)
  element.addEventListener('pointerdown', handleCardPointerDown)
  element.addEventListener('pointerup', handleCardPointerUp)
  element.addEventListener('pointercancel', handleCardPointerUp)
  element.addEventListener('pointerleave', handleCardPointerUp)
}

function getSatelliteAtPointer(event: PointerLikeEvent): CardMesh | null {
  if (!cardRenderer || !camera || performanceStore.isBackgrounded) {
    return null
  }

  const bounds = cardRenderer.domElement.getBoundingClientRect()
  if (bounds.width <= 0 || bounds.height <= 0) {
    return null
  }

  pointer.set(
    ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
    -((event.clientY - bounds.top) / bounds.height) * 2 + 1
  )
  raycaster.setFromCamera(pointer, camera)

  const hit = raycaster.intersectObjects(satellites, false)[0]
  if (!hit || !hit.object.visible) {
    return null
  }

  const sat = hit.object as CardMesh
  const frontMaterial = getCardFrontMaterial(sat)
  if (!frontMaterial || frontMaterial.opacity <= 0.05 || sat.scale.x <= 0.05) {
    return null
  }

  return sat
}

function handleSatellitePointerMove(event: PointerEvent) {
  if (!cardRenderer) {
    return
  }

  const sat = getSatelliteAtPointer(event)
  cardRenderer.domElement.style.cursor = sat ? 'pointer' : 'default'
}

function resetSatelliteCursor() {
  if (cardRenderer) {
    cardRenderer.domElement.style.cursor = 'default'
  }
}

// ── 中心图标彩蛋：连点 5 次起，每次按固定概率把中心图标换成炫彩版 ──
// 前 4 次不给机会，从第 5 次起每次 0.5%；连点到 30 次保底直接给，命中过就不再触发。
const CENTER_POKE_MIN_CLICKS = 5
const CENTER_POKE_CHANCE = 0.005
/** 手气差也不能点不到头，连点到这个次数一定给 */
const CENTER_POKE_GUARANTEE_CLICKS = 30
/** 中心图标按下去时的形变，照 dsh-whale-widget 的 SQUISH 加大幅度：压扁、横向撑开 */
const CENTER_PRESS_SCALE_X = 1.15
const CENTER_PRESS_SCALE_Y = 0.75
const CENTER_POKE_WINDOW_MS = 1500
let centerPokeCount = 0
let centerPokeLastAt = 0

/** 指针是否落在中心图标上；卫星拾取只看 satellites，中心卡片得单独判一次 */
function isCenterCardHit(event: PointerLikeEvent): boolean {
  if (!centerCard || !cardRenderer || !camera || performanceStore.isBackgrounded) {
    return false
  }

  const bounds = cardRenderer.domElement.getBoundingClientRect()
  if (bounds.width <= 0 || bounds.height <= 0) {
    return false
  }

  pointer.set(
    ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
    -((event.clientY - bounds.top) / bounds.height) * 2 + 1
  )
  raycaster.setFromCamera(pointer, camera)
  return raycaster.intersectObject(centerCard, false).length > 0
}

function registerCenterPoke(): void {
  const now = performance.now()
  // 慢悠悠点不算连点：超过窗口就从头数
  if (now - centerPokeLastAt > CENTER_POKE_WINDOW_MS) {
    centerPokeCount = 0
  }
  centerPokeLastAt = now
  centerPokeCount += 1

  // 连点够数之前不给机会
  if (centerPokeCount < CENTER_POKE_MIN_CLICKS) {
    return
  }
  if (centerIconRainbow) {
    return
  }

  // 保底：点够次数直接给，不再看概率
  if (centerPokeCount >= CENTER_POKE_GUARANTEE_CLICKS) {
    setCenterIconRainbow(true)
    centerPokeCount = 0
    logger.info('中心图标彩蛋触发：连点保底')
    return
  }

  // 连点够数之后，每一次都是同样的概率，不会越点越容易
  if (Math.random() >= CENTER_POKE_CHANCE) {
    return
  }

  setCenterIconRainbow(true)
  centerPokeCount = 0
  logger.info('中心图标彩蛋触发：炫彩图标')
}

/** 在点击处冒一句 star！，加速往上方飘走；彩蛋亮起来之后这句字是彩虹色的 */
function spawnStarBurst(clientX: number, clientY: number): void {
  if (!container.value || isUnmounted) {
    return
  }

  const bounds = container.value.getBoundingClientRect()
  const element = document.createElement('span')
  element.className = centerIconRainbow ? 'star-burst star-burst-rainbow' : 'star-burst'
  element.textContent = t('home.satelliteEgg.star')
  element.style.left = `${clientX - bounds.left}px`
  element.style.top = `${clientY - bounds.top}px`
  container.value.appendChild(element)

  // 左右随机偏一点，整体向上；缓动是强 ease-in，越飞越快
  const driftX = (Math.random() - 0.5) * 90
  const riseY = 220 + Math.random() * 140
  const spin = (Math.random() - 0.5) * 50
  const animation = element.animate(
    [
      { transform: 'translate(-50%, -50%) scale(0.6)', opacity: 0 },
      {
        offset: 0.22,
        transform: `translate(calc(-50% + ${driftX * 0.3}px), calc(-50% - ${riseY * 0.3}px)) scale(1.08) rotate(${spin * 0.35}deg)`,
        opacity: 1,
      },
      {
        transform: `translate(calc(-50% + ${driftX}px), calc(-50% - ${riseY}px)) scale(0.92) rotate(${spin}deg)`,
        opacity: 0,
      },
    ],
    { duration: 1150, easing: 'cubic-bezier(0.5, 0, 1, 1)', fill: 'forwards' }
  )
  animation.onfinish = () => element.remove()
}

/** 按在中心图标上时给它一个压扁的形变，松开还原 */
function handleCardPointerDown(event: PointerEvent): void {
  if (!isCenterCardHit(event)) {
    return
  }
  centerPressed = true
  spawnStarBurst(event.clientX, event.clientY)
}

function handleCardPointerUp(): void {
  centerPressed = false
}

function handleSatelliteClick(event: MouseEvent) {
  if (isCenterCardHit(event)) {
    registerCenterPoke()
    return
  }

  const sat = getSatelliteAtPointer(event)
  if (!sat || satelliteExplosions.has(sat)) {
    return
  }

  startSatelliteExplosion(sat)
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

function getRendererPixelRatio() {
  return Math.min(window.devicePixelRatio || 1, performanceStore.isLowPower ? 1 : 2)
}

function updateRendererPixelRatio() {
  const pixelRatio = getRendererPixelRatio()
  orbitRenderer?.setPixelRatio(pixelRatio)
  glowRenderer?.setPixelRatio(pixelRatio)
  cardRenderer?.setPixelRatio(pixelRatio)
}

function createSceneRenderer(zIndex: string, pointerEvents = true): THREE.WebGLRenderer | null {
  if (!container.value) {
    return null
  }

  const renderer = new THREE.WebGLRenderer({
    antialias: !performanceStore.lowPerformanceMode,
    alpha: true,
    powerPreference: performanceStore.lowPerformanceMode ? 'low-power' : 'high-performance',
  })
  renderer.setSize(Math.max(1, container.value.clientWidth), CONFIG.containerHeight)
  renderer.setPixelRatio(getRendererPixelRatio())
  renderer.setClearColor(0x000000, 0)
  renderer.domElement.style.position = 'absolute'
  renderer.domElement.style.top = '0'
  renderer.domElement.style.left = '0'
  renderer.domElement.style.zIndex = zIndex
  if (!pointerEvents) {
    renderer.domElement.style.pointerEvents = 'none'
  }
  container.value.appendChild(renderer.domElement)
  return renderer
}

function recreateMainRenderers() {
  if (!container.value || !orbitScene || !cardScene) {
    return
  }

  clearSatelliteExplosions()
  removeCardInteraction()
  disposeRenderer(orbitRenderer)
  disposeRenderer(cardRenderer)
  orbitRenderer = createSceneRenderer('1')
  cardRenderer = createSceneRenderer('2')
  setupCardInteraction()
}

function createGlowRenderer(force = false) {
  if (!container.value || !glowScene || glowRenderer || (performanceStore.isLowPower && !force)) {
    return
  }

  const w = Math.max(1, container.value.clientWidth)
  glowRenderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    powerPreference: 'high-performance',
  })
  glowRenderer.setSize(w, CONFIG.containerHeight)
  glowRenderer.setPixelRatio(getRendererPixelRatio())
  glowRenderer.setClearColor(0x000000, 0)
  glowRenderer.domElement.style.position = 'absolute'
  glowRenderer.domElement.style.top = '0'
  glowRenderer.domElement.style.left = '0'
  glowRenderer.domElement.style.zIndex = '1.5'
  glowRenderer.domElement.style.pointerEvents = 'none'
  container.value.appendChild(glowRenderer.domElement)
}

function disposeGlowRenderer() {
  if (!glowRenderer) {
    return
  }

  disposeRenderer(glowRenderer)
  glowRenderer = null
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
  const curve = new THREE.EllipseCurve(
    0,
    0,
    CONFIG.orbitRadiusX,
    CONFIG.orbitRadiusY,
    0,
    2 * Math.PI,
    false,
    0
  )
  const points = curve.getPoints(128)
  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  const colors = getThemeColors()
  const material = new THREE.LineBasicMaterial({
    color: colors.orbitColor,
    transparent: true,
    opacity: CONFIG.orbitOpacity,
  })
  const line = new THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial>(geometry, material)
  line.rotation.x = CONFIG.orbitTilt
  return line
}

function getCardFrontMaterial(card: CardMesh): THREE.MeshBasicMaterial | null {
  const material = card.material[4]
  return material instanceof THREE.MeshBasicMaterial ? material : null
}

function getCardImageCanvas(card: CardMesh): HTMLCanvasElement | null {
  const image = getCardFrontMaterial(card)?.map?.image
  if (!(image instanceof HTMLCanvasElement) || image.width <= 0 || image.height <= 0) {
    return null
  }
  return image
}

/**
 * 图标彩虹的色相站：每 5° 一个。段数给少了，相邻色相之间的插值偏色会连成肉眼可见的分界。
 * 每站存偏移比例和色相角，整体加 phase 偏移就成了流动效果。
 */
const ICON_RAINBOW_SEGMENTS = 72
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
function paintCenterRainbowIcon(
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

/** 炫彩贴图复用同一块画布，每帧只重画内容，靠 needsUpdate 推给 GPU */
function ensureCenterRainbowCanvas(): THREE.CanvasTexture | null {
  if (centerRainbowTexture) {
    return centerRainbowTexture
  }
  if (!centerIconCanvas) {
    return null
  }

  const canvas = document.createElement('canvas')
  canvas.width = centerIconCanvas.width
  canvas.height = centerIconCanvas.height
  const context = canvas.getContext('2d')
  if (!context) {
    return null
  }

  context.drawImage(centerIconCanvas, 0, 0)
  centerRainbowExtent = getOpaqueExtentAlong(
    context,
    canvas.width,
    canvas.height,
    RAINBOW_AXIS_X,
    RAINBOW_AXIS_Y
  )
  centerRainbowCanvas = canvas
  centerRainbowStartedAt = performance.now()

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.needsUpdate = true
  centerRainbowTexture = texture
  return texture
}

/** 每帧把色相往前推一点；只有炫彩图标开着时才动手 */
function updateCenterRainbowIcon(): void {
  if (
    !centerIconRainbow ||
    !centerRainbowCanvas ||
    !centerRainbowTexture ||
    !centerIconCanvas ||
    !centerRainbowExtent
  ) {
    return
  }

  const context = centerRainbowCanvas.getContext('2d')
  if (!context) {
    return
  }

  const elapsed = performance.now() - centerRainbowStartedAt
  const phase = ((elapsed / CENTER_RAINBOW_CYCLE_MS) * 360) % 360
  paintCenterRainbowIcon(context, centerIconCanvas, centerRainbowExtent, phase)
  centerRainbowTexture.needsUpdate = true
}

/** 中心图标的正面贴图在炫彩版和原图之间切换；原图 canvas 一直留着，换回来不用重新加载 */
function setCenterIconRainbow(rainbow: boolean): void {
  if (!centerCard || !centerIconCanvas || centerIconRainbow === rainbow) {
    return
  }

  const frontMaterial = getCardFrontMaterial(centerCard)
  if (!frontMaterial?.map) {
    return
  }

  let texture: THREE.CanvasTexture
  if (rainbow) {
    const rainbowTexture = ensureCenterRainbowCanvas()
    if (!rainbowTexture) {
      return
    }
    texture = rainbowTexture
  } else {
    texture = new THREE.CanvasTexture(centerIconCanvas)
    texture.colorSpace = THREE.SRGBColorSpace
    texture.needsUpdate = true
    // 炫彩用的画布随贴图一起丢掉，下次触发再建
    centerRainbowCanvas = null
    centerRainbowTexture = null
    centerRainbowExtent = null
  }

  frontMaterial.map.dispose()
  frontMaterial.map = texture
  frontMaterial.needsUpdate = true
  centerIconRainbow = rainbow
}

function createFragmentTexture(
  source: HTMLCanvasElement,
  column: number,
  row: number
): THREE.CanvasTexture {
  const columns = SATELLITE_EXPLOSION_CONFIG.fragmentColumns
  const rows = SATELLITE_EXPLOSION_CONFIG.fragmentRows
  const sourceWidth = source.width / columns
  const sourceHeight = source.height / rows
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.ceil(sourceWidth))
  canvas.height = Math.max(1, Math.ceil(sourceHeight))
  const context = canvas.getContext('2d')!
  context.drawImage(
    source,
    column * sourceWidth,
    row * sourceHeight,
    sourceWidth,
    sourceHeight,
    0,
    0,
    canvas.width,
    canvas.height
  )

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.needsUpdate = true
  return texture
}

function disposeExplosionResources(explosion: SatelliteExplosion) {
  cardScene?.remove(explosion.group)
  explosion.effectScene.remove(explosion.flashSprite, explosion.ringMesh)

  explosion.fragments.forEach(fragment => {
    fragment.mesh.geometry.dispose()
    fragment.mesh.material.map?.dispose()
    fragment.mesh.material.dispose()
  })
  explosion.flashSprite.material.dispose()
  explosion.ringMesh.material.dispose()
  explosion.group.clear()
}

function restoreSatelliteAfterExplosion(sat: CardMesh, explosion: SatelliteExplosion) {
  const frontMaterial = getCardFrontMaterial(sat)
  if (frontMaterial) {
    frontMaterial.opacity = explosion.originalOpacity
  }
  sat.scale.copy(explosion.originalScale)
  sat.visible = explosion.originalVisible
  setSatelliteEffectsVisible(sat, true)
}

function clearSatelliteExplosions() {
  satelliteExplosions.forEach((explosion, sat) => {
    restoreSatelliteAfterExplosion(sat, explosion)
    disposeExplosionResources(explosion)
  })
  satelliteExplosions.clear()
}

function startSatelliteExplosion(sat: CardMesh) {
  if (!cardScene || !glowScene || !glowTexture || satelliteExplosions.has(sat)) {
    return
  }

  const source = getCardImageCanvas(sat)
  const frontMaterial = getCardFrontMaterial(sat)
  if (!source || !frontMaterial) {
    return
  }

  const columns = SATELLITE_EXPLOSION_CONFIG.fragmentColumns
  const rows = SATELLITE_EXPLOSION_CONFIG.fragmentRows
  const fragmentWidth = CONFIG.satelliteCardSize / columns
  const fragmentHeight = CONFIG.satelliteCardSize / rows
  const group = new THREE.Group()
  group.position.copy(sat.position)
  group.quaternion.copy(sat.quaternion)
  group.scale.copy(sat.scale)
  group.renderOrder = 2

  const fragments: ExplosionFragment[] = []
  for (let row = 0; row < rows; row++) {
    for (let column = 0; column < columns; column++) {
      const texture = createFragmentTexture(source, column, row)
      const material = new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
      })
      const mesh = new THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>(
        new THREE.PlaneGeometry(fragmentWidth, fragmentHeight),
        material
      )
      const origin = new THREE.Vector3(
        (column + 0.5 - columns / 2) * fragmentWidth,
        (rows / 2 - row - 0.5) * fragmentHeight,
        CONFIG.satelliteCardDepth / 2 + 0.4
      )
      mesh.position.copy(origin)
      group.add(mesh)
      fragments.push({
        mesh,
        motion: createExplosionFragmentMotion(
          row * columns + column,
          columns * rows,
          Number(sat.userData.index ?? 0) + 17
        ),
        origin,
      })
    }
  }

  const flashMaterial = new THREE.SpriteMaterial({
    map: glowTexture,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    color: new THREE.Color(0x8ce7ff),
    opacity: 1,
  })
  const flashSprite = new THREE.Sprite(flashMaterial)
  flashSprite.position.copy(sat.position)
  flashSprite.scale.setScalar(CONFIG.satelliteCardSize * 1.2)
  flashSprite.renderOrder = 3

  const ringMaterial = new THREE.MeshBasicMaterial({
    color: new THREE.Color(0x6ce0ff),
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
    opacity: 0.9,
  })
  const ringMesh = new THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>(
    new THREE.RingGeometry(26, 31, 48),
    ringMaterial
  )
  ringMesh.position.copy(sat.position)
  ringMesh.quaternion.copy(sat.quaternion)
  ringMesh.scale.setScalar(0.2)
  ringMesh.renderOrder = 2

  const effectScene = performanceStore.isLowPower ? cardScene : glowScene

  const explosion: SatelliteExplosion = {
    group,
    effectScene,
    fragments,
    flashSprite,
    ringMesh,
    startTime: Date.now(),
    originalOpacity: frontMaterial.opacity,
    originalScale: sat.scale.clone(),
    originalVisible: sat.visible,
  }

  cardScene.add(group)
  effectScene.add(flashSprite, ringMesh)
  satelliteExplosions.set(sat, explosion)
  sat.visible = false
  setSatelliteEffectsVisible(sat, false)

  if (performanceStore.isLowPower) {
    renderCurrentFrame()
  }
}

function updateSatelliteExplosions(time: number): boolean {
  if (satelliteExplosions.size === 0) {
    return false
  }

  satelliteExplosions.forEach((explosion, sat) => {
    const elapsed = Math.max(0, time - explosion.startTime)
    const phase = getExplosionPhase(elapsed)
    const flightSeconds = Math.min(elapsed, SATELLITE_EXPLOSION_CONFIG.fragmentDuration) / 1000

    explosion.group.position.copy(sat.position)
    explosion.group.quaternion.copy(sat.quaternion)
    explosion.flashSprite.position.copy(sat.position)
    explosion.ringMesh.position.copy(sat.position)
    explosion.ringMesh.quaternion.copy(sat.quaternion)

    explosion.fragments.forEach(fragment => {
      const { mesh, motion, origin } = fragment
      const explodedPosition = new THREE.Vector3(
        origin.x + motion.velocityX * (SATELLITE_EXPLOSION_CONFIG.fragmentDuration / 1000),
        origin.y +
          motion.velocityY * (SATELLITE_EXPLOSION_CONFIG.fragmentDuration / 1000) -
          0.5 *
            SATELLITE_EXPLOSION_CONFIG.fragmentGravity *
            (SATELLITE_EXPLOSION_CONFIG.fragmentDuration / 1000) ** 2,
        origin.z + motion.velocityZ * (SATELLITE_EXPLOSION_CONFIG.fragmentDuration / 1000)
      )
      const explodedRotation = new THREE.Euler(
        motion.rotationX +
          motion.rotationSpeedX * (SATELLITE_EXPLOSION_CONFIG.fragmentDuration / 1000),
        motion.rotationY +
          motion.rotationSpeedY * (SATELLITE_EXPLOSION_CONFIG.fragmentDuration / 1000),
        motion.rotationZ +
          motion.rotationSpeedZ * (SATELLITE_EXPLOSION_CONFIG.fragmentDuration / 1000)
      )

      if (phase.isReassembling) {
        const progress = easeOutCubic(phase.progress)
        mesh.position.lerpVectors(explodedPosition, origin, progress)
        mesh.rotation.x = THREE.MathUtils.lerp(explodedRotation.x, 0, progress)
        mesh.rotation.y = THREE.MathUtils.lerp(explodedRotation.y, 0, progress)
        mesh.rotation.z = THREE.MathUtils.lerp(explodedRotation.z, 0, progress)
        mesh.material.opacity = progress
        return
      }

      mesh.position.set(
        origin.x + motion.velocityX * flightSeconds,
        origin.y +
          motion.velocityY * flightSeconds -
          0.5 * SATELLITE_EXPLOSION_CONFIG.fragmentGravity * flightSeconds ** 2,
        origin.z + motion.velocityZ * flightSeconds
      )
      mesh.rotation.set(
        motion.rotationX + motion.rotationSpeedX * flightSeconds,
        motion.rotationY + motion.rotationSpeedY * flightSeconds,
        motion.rotationZ + motion.rotationSpeedZ * flightSeconds
      )
      mesh.material.opacity =
        1 - getExplosionEffectProgress(elapsed, SATELLITE_EXPLOSION_CONFIG.fragmentDuration)
    })

    const flashProgress = getExplosionEffectProgress(
      elapsed,
      SATELLITE_EXPLOSION_CONFIG.flashDuration
    )
    explosion.flashSprite.material.opacity = 1 - flashProgress
    explosion.flashSprite.scale.setScalar(CONFIG.satelliteCardSize * (1.2 + flashProgress * 0.8))

    const ringProgress = getExplosionEffectProgress(
      elapsed,
      SATELLITE_EXPLOSION_CONFIG.ringDuration
    )
    explosion.ringMesh.material.opacity = (1 - ringProgress) * 0.9
    explosion.ringMesh.scale.setScalar(0.2 + ringProgress * 1.35)

    if (phase.complete) {
      restoreSatelliteAfterExplosion(sat, explosion)
      disposeExplosionResources(explosion)
      satelliteExplosions.delete(sat)
    }
  })

  const hasActiveExplosions = satelliteExplosions.size > 0
  if (!hasActiveExplosions && performanceStore.isLowPower) {
    disposeGlowRenderer()
  }
  return hasActiveExplosions
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
  if (!container.value || isUnmounted) return
  try {
    await initSceneInternal()
  } catch (err) {
    disposeScene()
    logger.error(`初始化场景失败: ${String(err)}`)
  } finally {
    loading.value = false
  }
}

async function initSceneInternal(): Promise<void> {
  if (!container.value || isUnmounted) return

  let userScripts: Awaited<ReturnType<typeof getScripts>> = []
  try {
    userScripts = await getScripts()
  } catch (err) {
    logger.warn(`获取脚本列表失败，按空集合处理: ${String(err)}`)
  }

  if (!container.value || isUnmounted) return

  const userScriptTypes = new Set<ScriptType>(userScripts.map(s => s.type as ScriptType))
  const enabledModules = satelliteModules.filter(
    m => m.enabled && userScriptTypes.has(m.scriptType)
  )
  const numSatellites = enabledModules.length

  if (numSatellites === 0) {
    logger.info('没有可显示的卫星模块，仅渲染中心图标和轨道')
  }

  const w = container.value.clientWidth

  camera = new THREE.PerspectiveCamera(CONFIG.cameraFov, w / CONFIG.containerHeight, 0.1, 5000)
  camera.position.set(0, 80, 500)
  camera.lookAt(0, 0, 0)

  orbitScene = new THREE.Scene()
  glowScene = new THREE.Scene()
  cardScene = new THREE.Scene()
  recreateMainRenderers()
  createGlowRenderer()

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

  glowTexture = createGlowTexture()

  const createdCenterCard = await createCard(
    CONFIG.centerCardSize,
    CONFIG.centerCardDepth,
    centerIconUrl
  )
  if (!container.value || isUnmounted) {
    disposeCardMesh(createdCenterCard)
    disposeScene()
    return
  }

  centerCard = createdCenterCard
  centerIconCanvas = getCardImageCanvas(createdCenterCard)
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
    CONFIG.centerCardSize * CONFIG.glowSizeMultiplier * 0.9,
    CONFIG.centerCardSize * CONFIG.glowSizeMultiplier * 0.9,
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
    if (!container.value || isUnmounted) {
      disposeCardMesh(sat)
      disposeScene()
      return
    }

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
      CONFIG.satelliteCardSize * CONFIG.glowSizeMultiplier,
      CONFIG.satelliteCardSize * CONFIG.glowSizeMultiplier,
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
      CONFIG.satelliteCardSize * CONFIG.glowSizeMultiplier * 1.08,
      CONFIG.satelliteCardSize * CONFIG.glowSizeMultiplier * 1.08,
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
        lastFailed: false,
      },
    })
  }

  loading.value = false

  if (performanceStore.isLowPower) {
    disposeGlowRenderer()
    showCardsImmediately()
    renderCurrentFrame()
  } else {
    animateAppear()
  }
}

function animateAppear() {
  const appearStart = Date.now()
  const totalDuration = CONFIG.cardAppearDelay * (satellites.length + 1) + CONFIG.cardAppearDuration

  function step() {
    if (isUnmounted || performanceStore.isLowPower) return

    const elapsed = Date.now() - appearStart
    if (elapsed > totalDuration) {
      showCardsImmediately()
      return
    }

    const centerProgress = Math.min(1, elapsed / CONFIG.cardAppearDuration)
    const easedCenter = easeOutCubic(centerProgress)
    if (centerCard) {
      const frontMaterial = getCardFrontMaterial(centerCard)
      if (frontMaterial) frontMaterial.opacity = easedCenter
      centerCard.scale.set(easedCenter, easedCenter, easedCenter)
    }

    satellites.forEach((sat, i) => {
      const delay = CONFIG.cardAppearDelay * (i + 1)
      const progress = Math.min(1, (elapsed - delay) / CONFIG.cardAppearDuration)
      const eased = easeOutCubic(Math.max(0, progress))
      const frontMaterial = getCardFrontMaterial(sat)
      if (frontMaterial) frontMaterial.opacity = eased
      sat.scale.set(eased, eased, eased)
    })

    appearAnimationFrameId = requestAnimationFrame(step)
  }

  appearAnimationFrameId = requestAnimationFrame(step)
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

function animate(): void {
  const shouldRenderLowPowerFrame = allowLowPowerFrame
  allowLowPowerFrame = false

  if (
    isUnmounted ||
    !camera ||
    performanceStore.isBackgrounded ||
    (!shouldRenderLowPowerFrame && performanceStore.isLowPower)
  ) {
    return
  }

  const time = Date.now()
  const numSatellites = satellites.length

  for (let i = 0; i < numSatellites; i++) {
    const sat = satellites[i]
    const angle = sat.userData.angle + time * CONFIG.satelliteOrbitSpeed
    const x = Math.cos(angle) * CONFIG.orbitRadiusX
    const y = Math.sin(angle) * CONFIG.orbitRadiusY
    const tiltedY = y * Math.cos(CONFIG.orbitTilt)
    const z = y * Math.sin(CONFIG.orbitTilt)
    const floatOffset =
      Math.sin(time * CONFIG.satelliteFloatSpeed * 0.001 + i * ((Math.PI * 2) / numSatellites)) *
      CONFIG.satelliteFloatAmplitude

    sat.position.set(x, tiltedY + floatOffset, z)
    sat.lookAt(camera.position)
    sat.rotation.z = 0
  }

  if (centerCard) {
    centerCard.lookAt(camera.position)
    centerCard.rotation.z = 0
    const centerFloat =
      Math.sin(time * CONFIG.centerFloatSpeed * 0.001) * CONFIG.centerFloatAmplitude
    centerCard.position.y = centerFloat
    // 入场动画自己写 scale，等它跑完再接管；按压形变平滑逼近，免得一帧跳到位
    if (appearAnimationFrameId === null) {
      const targetX = centerPressed ? CENTER_PRESS_SCALE_X : 1
      const targetY = centerPressed ? CENTER_PRESS_SCALE_Y : 1
      centerScaleX += (targetX - centerScaleX) * 0.35
      centerScaleY += (targetY - centerScaleY) * 0.35
      centerCard.scale.set(centerScaleX, centerScaleY, 1)
    }
  }

  updateCenterRainbowIcon()

  const hasActiveExplosions = updateSatelliteExplosions(time)

  if (performanceStore.isLowPower) {
    if (orbitRenderer && orbitScene) orbitRenderer.render(orbitScene, camera)
    if (glowRenderer && glowScene) glowRenderer.render(glowScene, camera)
    if (cardRenderer && cardScene) cardRenderer.render(cardScene, camera)
    if (hasActiveExplosions && !performanceStore.isBackgrounded) {
      animationFrameScheduler.request(animate)
    }
    return
  }

  satelliteStates.forEach((state, sat) => {
    if (state.activityGlowSprite) {
      state.activityGlowSprite.position.set(
        sat.position.x,
        sat.position.y,
        sat.position.z + CONFIG.activityGlowZOffset
      )

      const baseScale = CONFIG.satelliteCardSize * CONFIG.glowSizeMultiplier
      if (state.status.lastFailed) {
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

      if (state.status.lastFailed) {
        const faintPulse = state.status.running
          ? 0.5 + 0.5 * Math.sin(time * 0.003)
          : 0.5 + 0.5 * Math.sin(time * 0.0016)
        const baseScale = CONFIG.satelliteCardSize * CONFIG.glowSizeMultiplier * 1.08
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
        CONFIG.centerCardSize * (CONFIG.glowSizeMultiplier * 0.82 + flash * 0.1)
      )
    } else {
      centerGlowSprite.material.color.setHex(0x6ce08a)
      centerGlowSprite.material.opacity = 0.85
      centerGlowSprite.scale.setScalar(CONFIG.centerCardSize * CONFIG.glowSizeMultiplier * 0.85)
    }
  }

  if (orbitRenderer && orbitScene) orbitRenderer.render(orbitScene, camera)
  if (glowRenderer && glowScene) glowRenderer.render(glowScene, camera)
  if (cardRenderer && cardScene) cardRenderer.render(cardScene, camera)

  if (!performanceStore.isLowPower) {
    animationFrameScheduler.request(animate)
  }
}

function handleResize(): void {
  if (!container.value || !camera) return
  const w = container.value.clientWidth
  if (w <= 0) return
  camera.aspect = w / CONFIG.containerHeight
  camera.position.set(0, 80, 500)
  camera.updateProjectionMatrix()
  updateRendererPixelRatio()
  if (orbitRenderer) orbitRenderer.setSize(w, CONFIG.containerHeight)
  if (glowRenderer) glowRenderer.setSize(w, CONFIG.containerHeight)
  if (cardRenderer) cardRenderer.setSize(w, CONFIG.containerHeight)
  if (performanceStore.isLowPower) renderCurrentFrame()
}

watch(isDark, () => {
  updateAllThemeColors()
  if (performanceStore.isLowPower) renderCurrentFrame()
})

function updateSatelliteStates() {
  if (isUnmounted) return

  const statusByType = satelliteStatuses.value
  satelliteStates.forEach(state => {
    state.status = statusByType.get(state.type) ?? {
      queued: false,
      running: false,
      lastFailed: false,
    }
  })

  if (performanceStore.isLowPower && !performanceStore.isBackgrounded) {
    renderCurrentFrame()
  }
}

// 常驻订阅推送新状态时同步刷新展示
watch(satelliteStatuses, () => updateSatelliteStates())

watch(
  () => performanceStore.lowPerformanceMode,
  lowPerformanceMode => {
    recreateMainRenderers()

    if (lowPerformanceMode) {
      stopAnimation()
      stopAppearAnimation()
      disposeGlowRenderer()
      showCardsImmediately()
      if (!performanceStore.isBackgrounded) {
        renderCurrentFrame()
      }
      return
    }

    if (!performanceStore.isBackgrounded) {
      createGlowRenderer()
      startAnimation()
    }
  }
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
      stopAnimation()
      stopAppearAnimation()
      stopStatusPolling()
      clearSatelliteExplosions()
      disposeGlowRenderer()
      return
    }

    await nextTick()
    if (isUnmounted) return

    handleResize()
    showCardsImmediately()
    if (performanceStore.lowPerformanceMode) {
      renderCurrentFrame()
    } else {
      createGlowRenderer()
      startAnimation()
    }
    updateSatelliteStates()
    void waitBackendReady().then(() => {
      if (isUnmounted || performanceStore.isBackgrounded) return
      void refreshSatelliteStatuses()
      startStatusPolling()
    })
  }
)

onMounted(async () => {
  isUnmounted = false
  await waitBackendReady()
  if (isUnmounted) return
  try {
    await initScene()
  } catch (e) {
    logger.error(`init failed: ${String(e)}`)
  }
  if (isUnmounted) return

  if (performanceStore.isLowPower) {
    renderCurrentFrame()
  } else {
    startAnimation()
  }
  window.addEventListener('resize', handleResize)

  updateSatelliteStates()
  void refreshSatelliteStatuses()
  startStatusPolling()

  // 检查更新状态
  try {
    const updateRes = await requestUpdateCheck(false)
    if (updateRes.code === 200 && updateRes.if_need_update) {
      if (isUnmounted) return
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
  height: 400px;
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

/* 浮字是运行时创建的，不在模板里，scoped 的选择器要用 :deep 才管得到 */
.satellite-container :deep(.star-burst) {
  position: absolute;
  /* 三个 canvas 的 z-index 是 1/1.5/2，浮字得压在上面才看得见 */
  z-index: 10;
  transform: translate(-50%, -50%);
  font-size: 17px;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: var(--ant-color-warning);
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
  pointer-events: none;
  white-space: nowrap;
  will-change: transform, opacity;
}

.satellite-container :deep(.star-burst-rainbow) {
  background-image: linear-gradient(90deg, #ff5f6d, #ffc371, #47e5bc, #4facfe, #b06ab3, #ff5f6d);
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  -webkit-text-fill-color: transparent;
  text-shadow: none;
  animation: star-rainbow 1.2s linear infinite;
}

@keyframes star-rainbow {
  to {
    background-position: 200% center;
  }
}
</style>
