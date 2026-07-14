<template>
  <div ref="container" class="satellite-container">
    <div v-if="loading" class="loading-spinner"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useTheme } from '@/composables/useTheme'
import { useScriptApi } from '@/composables/useScriptApi'
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
const { getScripts } = useScriptApi()

onUnmounted(() => {
  isUnmounted = true
  window.removeEventListener('resize', handleResize)
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

  const w = container.value.clientWidth

  camera = new THREE.PerspectiveCamera(CONFIG.cameraFov, w / CONFIG.containerHeight, 0.1, 5000)
  camera.position.set(0, 80, 500)
  camera.lookAt(0, 0, 0)

  orbitScene = new THREE.Scene()
  orbitRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  orbitRenderer.setSize(w, CONFIG.containerHeight)
  orbitRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  orbitRenderer.setClearColor(0x000000, 0)
  orbitRenderer.domElement.style.position = 'absolute'
  orbitRenderer.domElement.style.top = '0'
  orbitRenderer.domElement.style.left = '0'
  orbitRenderer.domElement.style.zIndex = '1'
  container.value.appendChild(orbitRenderer.domElement)

  glowScene = new THREE.Scene()
  glowRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  glowRenderer.setSize(w, CONFIG.containerHeight)
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
  cardRenderer.setSize(w, CONFIG.containerHeight)
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
        errorVisible: false,
      },
    })
  }

  loading.value = false

  animateAppear()
}

function animateAppear() {
  const appearStart = Date.now()
  const totalDuration = CONFIG.cardAppearDelay * (satellites.length + 1) + CONFIG.cardAppearDuration

  function step() {
    if (isUnmounted) return

    const elapsed = Date.now() - appearStart
    if (elapsed > totalDuration) {
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
  if (isUnmounted || !camera) return

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
  }

  satelliteStates.forEach((state, sat) => {
    if (state.activityGlowSprite) {
      state.activityGlowSprite.position.set(
        sat.position.x,
        sat.position.y,
        sat.position.z + CONFIG.activityGlowZOffset
      )

      const baseScale = CONFIG.satelliteCardSize * CONFIG.glowSizeMultiplier
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

  animationFrameId = requestAnimationFrame(animate)
}

function handleResize(): void {
  if (!container.value || !camera) return
  const w = container.value.clientWidth
  camera.aspect = w / CONFIG.containerHeight
  camera.position.set(0, 80, 500)
  camera.updateProjectionMatrix()
  if (orbitRenderer) orbitRenderer.setSize(w, CONFIG.containerHeight)
  if (glowRenderer) glowRenderer.setSize(w, CONFIG.containerHeight)
  if (cardRenderer) cardRenderer.setSize(w, CONFIG.containerHeight)
}

watch(isDark, () => {
  updateAllThemeColors()
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
  } catch (error) {
    logger.error(`更新状态失败: ${String(error)}`)
  }
}

onMounted(async () => {
  isUnmounted = false
  try {
    await initScene()
  } catch (e) {
    logger.error(`init failed: ${String(e)}`)
  }
  animate()
  window.addEventListener('resize', handleResize)

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
</style>
