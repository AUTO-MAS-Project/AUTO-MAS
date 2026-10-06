import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js'
import { SATELLITE_CONFIG as C, type OrbitRing } from './config'
import { getRingBasis, getRingPoint, type GlowAppearance } from './motion'
import { CORE_SHELL_SHADER, ORBIT_SHADER, POINTS_SHADER } from './shaders'

// ==================== 绘制顺序 ====================

/**
 * 透明物体按这个顺序画。轨道排在星核之后、卫星之前，又不写深度：
 * 绕到星核背后的那段被星核挡住，卫星则永远压在轨道上面。
 */
export const RENDER_ORDER = {
  stars: 0,
  coreGlow: 1,
  coreIcon: 2,
  orbit: 3,
  coreDecor: 3,
  trail: 4,
  satelliteGlow: 5,
  satelliteBody: 6,
  satelliteIcon: 7,
  coreShell: 8,
  effect: 9,
  overlay: 10,
} as const

// ==================== 贴图 ====================

export async function loadImageToCanvas(url: string): Promise<HTMLCanvasElement> {
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

export function createCanvasTexture(canvas: HTMLCanvasElement): THREE.CanvasTexture {
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.needsUpdate = true
  return texture
}

export function createGlowTexture(): THREE.CanvasTexture {
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

/** 冲击波：一圈两侧虚化的细光环，贴在正对镜头的平面上往外扩 */
export function createShockwaveTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 256
  const ctx = canvas.getContext('2d')!
  const gradient = ctx.createRadialGradient(128, 128, 0, 128, 128, 128)
  gradient.addColorStop(0, 'rgba(140, 231, 255, 0)')
  gradient.addColorStop(0.78, 'rgba(140, 231, 255, 0)')
  gradient.addColorStop(0.92, 'rgba(200, 245, 255, 0.95)')
  gradient.addColorStop(0.96, 'rgba(140, 231, 255, 0.35)')
  gradient.addColorStop(1, 'rgba(140, 231, 255, 0)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, 256, 256)
  return new THREE.CanvasTexture(canvas)
}

export function createGlowSprite(texture: THREE.Texture, renderOrder: number): THREE.Sprite {
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      opacity: 0,
    })
  )
  sprite.renderOrder = renderOrder
  return sprite
}

export function applyGlow(
  sprite: THREE.Sprite,
  appearance: GlowAppearance | null,
  anchor: THREE.Vector3,
  fade = 1
): void {
  sprite.position.copy(anchor)
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
  sprite.material.opacity = appearance.opacity * fade
  sprite.scale.set(appearance.size, appearance.size, 1)
}

// ==================== 粒子 ====================

/** 一团圆点粒子：位置、颜色、透明度、大小都按点存，每帧可以改 */
export interface PointCloud {
  points: THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial>
  positions: Float32Array
  colors: Float32Array
  alphas: Float32Array
  sizes: Float32Array
  /** 改完数组后调用，把改动推给 GPU */
  commit(): void
}

export function createPointCloud(count: number, renderOrder: number, twinkle = false): PointCloud {
  const positions = new Float32Array(count * 3)
  const colors = new Float32Array(count * 3)
  const alphas = new Float32Array(count)
  const sizes = new Float32Array(count)
  const phases = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    phases[i] = Math.random() * Math.PI * 2
  }

  const geometry = new THREE.BufferGeometry()
  const attributes = {
    position: new THREE.BufferAttribute(positions, 3),
    aColor: new THREE.BufferAttribute(colors, 3),
    aAlpha: new THREE.BufferAttribute(alphas, 1),
    aSize: new THREE.BufferAttribute(sizes, 1),
  }
  for (const [name, attribute] of Object.entries(attributes)) {
    attribute.setUsage(THREE.DynamicDrawUsage)
    geometry.setAttribute(name, attribute)
  }
  geometry.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1))

  const material = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uPixelRatio: { value: 1 },
      uTwinkle: { value: twinkle ? 1 : 0 },
    },
    vertexShader: POINTS_SHADER.vertex,
    fragmentShader: POINTS_SHADER.fragment,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    premultipliedAlpha: true,
  })

  const points = new THREE.Points(geometry, material)
  points.renderOrder = renderOrder
  points.frustumCulled = false

  return {
    points,
    positions,
    colors,
    alphas,
    sizes,
    commit() {
      for (const attribute of Object.values(attributes)) {
        attribute.needsUpdate = true
      }
    },
  }
}

/** 星空：围着星核的一个大球壳，只在深色主题下显示 */
export function createStarfield(): PointCloud {
  const cloud = createPointCloud(C.starCount, RENDER_ORDER.stars, true)
  const color = new THREE.Color()
  for (let i = 0; i < C.starCount; i++) {
    const radius = 1500 + Math.random() * 1100
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    cloud.positions.set(
      [
        radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.cos(phi),
        radius * Math.sin(phi) * Math.sin(theta),
      ],
      i * 3
    )
    color.setHSL(0.55 + Math.random() * 0.12, 0.5, 0.75 + Math.random() * 0.25)
    cloud.colors.set([color.r, color.g, color.b], i * 3)
    cloud.alphas[i] = 0.35 + Math.random() * 0.6
    cloud.sizes[i] = 6 + Math.random() * 12
  }
  cloud.commit()
  return cloud
}

/** 星核周围一圈缓慢旋转的尘埃盘 */
export function createCoreSwirl(): PointCloud {
  const cloud = createPointCloud(C.swirlCount, RENDER_ORDER.coreDecor, true)
  const color = new THREE.Color()
  for (let i = 0; i < C.swirlCount; i++) {
    const radius = 84 + Math.pow(Math.random(), 1.6) * 70
    const angle = Math.random() * Math.PI * 2
    cloud.positions.set(
      [radius * Math.cos(angle), (Math.random() - 0.5) * 10, radius * Math.sin(angle)],
      i * 3
    )
    color.setHSL(0.47 + Math.random() * 0.1, 0.85, 0.62)
    cloud.colors.set([color.r, color.g, color.b], i * 3)
    cloud.alphas[i] = 0.25 + Math.random() * 0.5
    cloud.sizes[i] = 2.5 + Math.random() * 4
  }
  cloud.commit()
  cloud.points.rotation.x = 0.42
  cloud.points.rotation.z = -0.18
  return cloud
}

// ==================== 星核 ====================

export function createCoreShell(): THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial> {
  const shell = new THREE.Mesh(
    new THREE.SphereGeometry(C.coreShellRadius, 48, 32),
    new THREE.ShaderMaterial({
      uniforms: {
        uColor: { value: new THREE.Color(0x6ce08a) },
        uIntensity: { value: 1 },
        uTime: { value: 0 },
      },
      vertexShader: CORE_SHELL_SHADER.vertex,
      fragmentShader: CORE_SHELL_SHADER.fragment,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      premultipliedAlpha: true,
    })
  )
  shell.renderOrder = RENDER_ORDER.coreShell
  return shell
}

/** 星核外两圈陀螺仪环 */
export function createGyroRing(
  radius: number,
  tube: number
): THREE.Mesh<THREE.TorusGeometry, THREE.MeshBasicMaterial> {
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(radius, tube, 6, 160),
    new THREE.MeshBasicMaterial({
      transparent: true,
      opacity: 0.55,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
  )
  ring.renderOrder = RENDER_ORDER.coreDecor
  return ring
}

// ==================== 轨道 ====================

const ORBIT_SEGMENTS = 240

export type OrbitLine = THREE.LineLoop<THREE.BufferGeometry, THREE.ShaderMaterial>

export function createOrbitLine(ring: OrbitRing): OrbitLine {
  const basis = getRingBasis(ring)
  const positions = new Float32Array(ORBIT_SEGMENTS * 3)
  const angles = new Float32Array(ORBIT_SEGMENTS)
  for (let i = 0; i < ORBIT_SEGMENTS; i++) {
    const angle = (i / ORBIT_SEGMENTS) * Math.PI * 2
    const point = getRingPoint(basis, ring.radius, angle)
    positions.set([point.x, point.y, point.z], i * 3)
    angles[i] = angle
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('aAngle', new THREE.BufferAttribute(angles, 1))

  const line = new THREE.LineLoop(
    geometry,
    new THREE.ShaderMaterial({
      uniforms: {
        uColor: { value: new THREE.Color() },
        uOpacity: { value: 1 },
        uRadius: { value: ring.radius },
        uCenterDepth: { value: -C.cameraDistance },
        uTime: { value: 0 },
        uFlow: { value: 1 },
      },
      vertexShader: ORBIT_SHADER.vertex,
      fragmentShader: ORBIT_SHADER.fragment,
      transparent: true,
      depthWrite: false,
    })
  )
  line.renderOrder = RENDER_ORDER.orbit
  return line
}

// ==================== 卫星 ====================

export interface SatelliteTile {
  root: THREE.Group
  body: THREE.Mesh<RoundedBoxGeometry, THREE.MeshStandardMaterial>
  /** 正反两面共用一个图标材质 */
  iconMaterial: THREE.MeshBasicMaterial
}

/** 一块圆角玻璃方块，图标贴在正反两面：翻过来看也是正的 */
export function createSatelliteTile(iconCanvas: HTMLCanvasElement): SatelliteTile {
  const size = C.satelliteSize
  const depth = C.satelliteDepth
  const body = new THREE.Mesh(
    new RoundedBoxGeometry(size, size, depth, 4, 11),
    new THREE.MeshStandardMaterial({
      metalness: 0.72,
      roughness: 0.26,
      transparent: true,
      opacity: 0,
      envMapIntensity: 1.15,
    })
  )
  body.renderOrder = RENDER_ORDER.satelliteBody

  const iconMaterial = new THREE.MeshBasicMaterial({
    map: createCanvasTexture(iconCanvas),
    transparent: true,
    opacity: 0,
    depthWrite: false,
  })
  const iconGeometry = new THREE.PlaneGeometry(size * 0.84, size * 0.84)
  const front = new THREE.Mesh(iconGeometry, iconMaterial)
  front.position.z = depth / 2 + 0.3
  front.renderOrder = RENDER_ORDER.satelliteIcon
  const back = new THREE.Mesh(iconGeometry, iconMaterial)
  back.position.z = -(depth / 2 + 0.3)
  back.rotation.y = Math.PI
  back.renderOrder = RENDER_ORDER.satelliteIcon

  const root = new THREE.Group()
  root.add(body, front, back)
  root.scale.setScalar(0.001)
  return { root, body, iconMaterial }
}

// ==================== 释放 ====================

export function disposeObject(object: THREE.Object3D): void {
  const geometries = new Set<THREE.BufferGeometry>()
  const materials = new Set<THREE.Material>()
  const textures = new Set<THREE.Texture>()

  object.traverse(child => {
    const { geometry, material } = child as THREE.Object3D & {
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
}
