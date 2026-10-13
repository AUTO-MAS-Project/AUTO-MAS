import * as THREE from 'three'
import { easeOutCubic } from './motion'
import { createPointCloud, RENDER_ORDER, type PointCloud } from './sceneParts'

/** 一段放完就收的特效 */
export interface SceneEffect {
  /** 推进到 time；返回 true 表示放完了，可以 dispose */
  update(time: number): boolean
  dispose(): void
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

/** 随机单位向量（球面均匀） */
function randomDirection(out: THREE.Vector3): THREE.Vector3 {
  const theta = Math.random() * Math.PI * 2
  const phi = Math.acos(2 * Math.random() - 1)
  return out.set(Math.sin(phi) * Math.cos(theta), Math.cos(phi), Math.sin(phi) * Math.sin(theta))
}

// ==================== 粒子爆发 ====================

export interface PointBurstOptions {
  origin: THREE.Vector3
  count: number
  /** 初速度范围（单位/毫秒） */
  speed: readonly [number, number]
  /** 额外往上的初速度，烟花和金粉往上冒一点更好看 */
  lift?: number
  gravity: number
  life: number
  size: readonly [number, number]
  color: (index: number, out: THREE.Color) => void
  startTime: number
  pixelRatio: number
  /** 压在所有东西上面，不被星核和卫星挡住 */
  overlay?: boolean
}

/** 一团从 origin 炸开的发光粒子，带重力和闪烁，边飞边淡 */
export class PointBurst implements SceneEffect {
  private readonly scene: THREE.Scene
  private readonly cloud: PointCloud
  private readonly velocities: Float32Array
  private readonly origin: THREE.Vector3
  private readonly options: PointBurstOptions

  constructor(scene: THREE.Scene, options: PointBurstOptions) {
    this.scene = scene
    this.options = options
    this.origin = options.origin.clone()
    this.cloud = createPointCloud(
      options.count,
      options.overlay ? RENDER_ORDER.overlay : RENDER_ORDER.effect,
      true
    )
    const { material } = this.cloud.points
    material.uniforms.uPixelRatio.value = options.pixelRatio
    if (options.overlay) material.depthTest = false

    this.velocities = new Float32Array(options.count * 3)
    const direction = new THREE.Vector3()
    const color = new THREE.Color()
    for (let i = 0; i < options.count; i++) {
      randomDirection(direction).multiplyScalar(randomBetween(...options.speed))
      direction.y += options.lift ?? 0
      this.velocities.set([direction.x, direction.y, direction.z], i * 3)
      options.color(i, color)
      this.cloud.colors.set([color.r, color.g, color.b], i * 3)
      this.cloud.sizes[i] = randomBetween(...options.size)
    }
    this.cloud.commit()
    scene.add(this.cloud.points)
  }

  update(time: number): boolean {
    const { count, gravity, life, startTime } = this.options
    const age = time - startTime
    const { positions, alphas } = this.cloud
    this.cloud.points.material.uniforms.uTime.value = time

    // 位置按出发点、初速度和重力直接算，掉帧也不会飞丢
    const alpha = age < 0 ? 0 : Math.pow(Math.max(0, 1 - age / life), 1.5)
    const t = Math.max(0, age)
    const drop = 0.5 * gravity * t * t
    for (let i = 0; i < count; i++) {
      positions[i * 3] = this.origin.x + this.velocities[i * 3] * t
      positions[i * 3 + 1] = this.origin.y + this.velocities[i * 3 + 1] * t - drop
      positions[i * 3 + 2] = this.origin.z + this.velocities[i * 3 + 2] * t
      alphas[i] = alpha
    }
    this.cloud.commit()
    return age > life
  }

  dispose(): void {
    this.scene.remove(this.cloud.points)
    this.cloud.points.geometry.dispose()
    this.cloud.points.material.dispose()
  }
}

// ==================== 道具雨 ====================

export interface ShowerParticle {
  position: THREE.Vector3
  velocity: THREE.Vector3
  size: number
  delay: number
  life: number
  /** 自转速度（弧度/毫秒） */
  spin: number
  /** 左右摆动幅度 */
  sway: number
}

export interface SpriteShowerOptions {
  /** 贴图归这个特效所有，放完一起释放 */
  texture: THREE.Texture
  particles: readonly ShowerParticle[]
  gravity: number
  startTime: number
  blending: THREE.Blending
}

/** 一批带贴图的小道具：原石雨、爱心之类，各自带延迟、自转和摆动 */
export class SpriteShower implements SceneEffect {
  private readonly scene: THREE.Scene
  private readonly options: SpriteShowerOptions
  private readonly sprites: THREE.Sprite[]

  constructor(scene: THREE.Scene, options: SpriteShowerOptions) {
    this.scene = scene
    this.options = options
    this.sprites = options.particles.map(particle => {
      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: options.texture,
          transparent: true,
          depthTest: false,
          depthWrite: false,
          blending: options.blending,
          opacity: 0,
        })
      )
      sprite.renderOrder = RENDER_ORDER.overlay
      sprite.scale.setScalar(particle.size)
      sprite.visible = false
      scene.add(sprite)
      return sprite
    })
  }

  update(time: number): boolean {
    let alive = false
    this.options.particles.forEach((particle, index) => {
      const sprite = this.sprites[index]
      const age = time - this.options.startTime - particle.delay
      if (age < 0 || age > particle.life) {
        sprite.visible = false
        alive ||= age < 0
        return
      }

      alive = true
      sprite.visible = true
      sprite.position.set(
        particle.position.x +
          particle.velocity.x * age +
          Math.sin(age * 0.004 + index) * particle.sway,
        particle.position.y + particle.velocity.y * age - 0.5 * this.options.gravity * age * age,
        particle.position.z + particle.velocity.z * age
      )
      sprite.material.rotation = particle.spin * age
      sprite.material.opacity = Math.min(1, age / 200, (particle.life - age) / 450)
    })
    return !alive
  }

  dispose(): void {
    for (const sprite of this.sprites) {
      this.scene.remove(sprite)
      sprite.material.dispose()
    }
    this.options.texture.dispose()
  }
}

// ==================== 线条 ====================

/** 一批两端颜色不同的线段，挂在镜头下面，坐标是镜头空间（-z 是前方） */
class CameraStreaks {
  readonly positions: Float32Array
  readonly colors: Float32Array
  private readonly lines: THREE.LineSegments<THREE.BufferGeometry, THREE.LineBasicMaterial>
  private readonly camera: THREE.Camera

  constructor(camera: THREE.Camera, count: number) {
    this.camera = camera
    this.positions = new Float32Array(count * 6)
    this.colors = new Float32Array(count * 8)
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute(
      'position',
      new THREE.BufferAttribute(this.positions, 3).setUsage(THREE.DynamicDrawUsage)
    )
    // 4 个分量：带 alpha 的顶点色，线段尾巴才能淡出去
    geometry.setAttribute(
      'color',
      new THREE.BufferAttribute(this.colors, 4).setUsage(THREE.DynamicDrawUsage)
    )
    this.lines = new THREE.LineSegments(
      geometry,
      new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        depthTest: false,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
    )
    this.lines.frustumCulled = false
    this.lines.renderOrder = RENDER_ORDER.overlay
    camera.add(this.lines)
  }

  setSegment(
    index: number,
    head: readonly [number, number, number],
    tail: readonly [number, number, number],
    headColor: readonly [number, number, number, number],
    tailColor: readonly [number, number, number, number]
  ): void {
    this.positions.set(head, index * 6)
    this.positions.set(tail, index * 6 + 3)
    this.colors.set(headColor, index * 8)
    this.colors.set(tailColor, index * 8 + 4)
  }

  commit(): void {
    this.lines.geometry.attributes.position.needsUpdate = true
    this.lines.geometry.attributes.color.needsUpdate = true
  }

  dispose(): void {
    this.camera.remove(this.lines)
    this.lines.geometry.dispose()
    this.lines.material.dispose()
  }
}

const WARP_COUNT = 320
const WARP_MS = 2000

/** 入场的曲速跃迁：星光拉成线迎面冲过来，越来越慢，最后淡掉 */
export class WarpEffect implements SceneEffect {
  private readonly streaks: CameraStreaks
  private readonly startTime: number
  private readonly seeds: Float32Array

  constructor(camera: THREE.Camera, startTime: number) {
    this.startTime = startTime
    this.streaks = new CameraStreaks(camera, WARP_COUNT)
    // 每条线：方位角、离轴半径、初始深度
    this.seeds = new Float32Array(WARP_COUNT * 3)
    for (let i = 0; i < WARP_COUNT; i++) {
      this.seeds.set(
        [Math.random() * Math.PI * 2, randomBetween(30, 520), randomBetween(200, 4200)],
        i * 3
      )
    }
  }

  update(time: number): boolean {
    const elapsed = time - this.startTime
    const progress = Math.min(1, elapsed / WARP_MS)
    // 速度从很快降到 0；走过的距离是速度的积分
    const travelled = 5200 * easeOutCubic(progress)
    const speed = 1 - progress
    const fade = Math.min(1, elapsed / 150) * Math.max(0, 1 - Math.max(0, progress - 0.55) / 0.45)

    for (let i = 0; i < WARP_COUNT; i++) {
      const angle = this.seeds[i * 3]
      const radius = this.seeds[i * 3 + 1]
      const depth = ((((this.seeds[i * 3 + 2] - travelled) % 4200) + 4200) % 4200) + 80
      const length = 40 + 900 * speed
      const x = Math.cos(angle) * radius
      const y = Math.sin(angle) * radius * 0.6
      const near = Math.min(1, 900 / depth)
      this.streaks.setSegment(
        i,
        [x, y, -depth],
        [x, y, -depth - length],
        [0.75, 0.9, 1, fade * near],
        [0.4, 0.6, 1, 0]
      )
    }
    this.streaks.commit()
    return elapsed >= WARP_MS
  }

  dispose(): void {
    this.streaks.dispose()
  }
}

const RAIN_COUNT = 420

/** 暴雨：斜着落的雨幕，铺满镜头前方，前后渐入渐出 */
export class RainEffect implements SceneEffect {
  private readonly streaks: CameraStreaks
  private readonly startTime: number
  private readonly duration: number
  private readonly seeds: Float32Array

  constructor(camera: THREE.Camera, startTime: number, duration: number) {
    this.startTime = startTime
    this.duration = duration
    this.streaks = new CameraStreaks(camera, RAIN_COUNT)
    // 每条雨丝：横向位置（-1~1）、下落相位、深度、速度
    this.seeds = new Float32Array(RAIN_COUNT * 4)
    for (let i = 0; i < RAIN_COUNT; i++) {
      this.seeds.set(
        [
          randomBetween(-1.2, 1.2),
          Math.random(),
          randomBetween(300, 1600),
          randomBetween(0.8, 1.3),
        ],
        i * 4
      )
    }
  }

  update(time: number): boolean {
    const elapsed = time - this.startTime
    const fade = Math.min(1, elapsed / 500, (this.duration - elapsed) / 900)
    // 镜头视角 24°：深度 d 处半高约 0.21d，半宽再乘宽高比（这里按 3 估，宁可多铺）
    for (let i = 0; i < RAIN_COUNT; i++) {
      const lateral = this.seeds[i * 4]
      const depth = this.seeds[i * 4 + 2]
      const halfHeight = depth * 0.22
      const cycle =
        (this.seeds[i * 4 + 1] + ((elapsed * 0.0011 * this.seeds[i * 4 + 3]) / halfHeight) * 400) %
        1
      const y = halfHeight * (1 - 2 * cycle)
      const x = lateral * halfHeight * 3 - (y + halfHeight) * 0.18
      const length = halfHeight * 0.12
      this.streaks.setSegment(
        i,
        [x, y, -depth],
        [x + length * 0.18, y + length, -depth],
        [0.72, 0.8, 0.95, 0.55 * Math.max(0, fade)],
        [0.72, 0.8, 0.95, 0]
      )
    }
    this.streaks.commit()
    return elapsed >= this.duration
  }

  dispose(): void {
    this.streaks.dispose()
  }
}

// ==================== 流星 ====================

/** 背景里偶尔划过的流星，点中可以许愿 */
export class ShootingStar implements SceneEffect {
  readonly head = new THREE.Vector3()
  private readonly streaks: CameraStreaks
  private readonly glow: THREE.Sprite
  private readonly camera: THREE.Camera
  private readonly startTime: number
  private readonly duration = randomBetween(900, 1400)
  private readonly from: THREE.Vector3
  private readonly to: THREE.Vector3
  private caught = false

  constructor(camera: THREE.Camera, glowTexture: THREE.Texture, startTime: number) {
    this.camera = camera
    this.startTime = startTime
    this.streaks = new CameraStreaks(camera, 1)
    // 在镜头前远处，从上方一侧斜着划到另一侧
    const depth = randomBetween(1700, 2400)
    const halfHeight = depth * 0.21
    const side = Math.random() < 0.5 ? -1 : 1
    this.from = new THREE.Vector3(
      side * randomBetween(0.3, 2) * halfHeight,
      randomBetween(0.4, 1) * halfHeight,
      -depth
    )
    this.to = this.from
      .clone()
      .add(
        new THREE.Vector3(
          -side * randomBetween(1.2, 2) * halfHeight,
          -randomBetween(0.6, 1.1) * halfHeight,
          0
        )
      )

    this.glow = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glowTexture,
        color: 0xdff4ff,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthTest: false,
        depthWrite: false,
      })
    )
    this.glow.renderOrder = RENDER_ORDER.overlay
    this.glow.scale.setScalar(depth * 0.035)
    camera.add(this.glow)
  }

  /** 头部在世界坐标里的位置，拾取用 */
  worldHead(out: THREE.Vector3): THREE.Vector3 {
    return this.camera.localToWorld(out.copy(this.head))
  }

  /** 被点中了：这一颗就此消失 */
  catch(): void {
    this.caught = true
  }

  update(time: number): boolean {
    const progress = (time - this.startTime) / this.duration
    if (this.caught || progress >= 1) {
      this.glow.visible = false
      return true
    }

    const eased = Math.max(0, progress)
    this.head.lerpVectors(this.from, this.to, eased)
    const tail = this.head.clone().sub(this.to.clone().sub(this.from).multiplyScalar(0.28))
    const fade = Math.min(1, progress / 0.12, (1 - progress) / 0.3)
    this.streaks.setSegment(
      0,
      [this.head.x, this.head.y, this.head.z],
      [tail.x, tail.y, tail.z],
      [1, 1, 1, 0.9 * fade],
      [0.5, 0.75, 1, 0]
    )
    this.streaks.commit()
    this.glow.position.copy(this.head)
    this.glow.material.opacity = fade
    return false
  }

  dispose(): void {
    this.streaks.dispose()
    this.camera.remove(this.glow)
    this.glow.material.dispose()
  }
}

// ==================== 出金 ====================

const GOLD_FALL_MS = 750

/**
 * 出金：一颗金色流星从右上方天外砸向目标，带一道长尾；砸中那一刻回调 onImpact，
 * 由场景接着放冲击波、金粉和星核闪光。
 */
export class GoldMeteor implements SceneEffect {
  private readonly scene: THREE.Scene
  private readonly startTime: number
  private readonly start: THREE.Vector3
  private readonly getTarget: () => THREE.Vector3
  private readonly onImpact: (time: number, at: THREE.Vector3) => void
  private readonly head: THREE.Sprite
  private readonly rays: THREE.Sprite
  private readonly trail: THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial>
  private impacted = false
  private impactAt = 0

  constructor(
    scene: THREE.Scene,
    options: {
      camera: THREE.Camera
      glowTexture: THREE.Texture
      raysTexture: THREE.Texture
      color: number
      startTime: number
      getTarget: () => THREE.Vector3
      onImpact: (time: number, at: THREE.Vector3) => void
    }
  ) {
    this.scene = scene
    this.startTime = options.startTime
    this.getTarget = options.getTarget
    this.onImpact = options.onImpact

    // 起点：目标的右上方、偏向镜头一侧，按镜头的右、上方向摆，转了镜头也一样从右上方来
    const right = new THREE.Vector3().setFromMatrixColumn(options.camera.matrixWorld, 0)
    const up = new THREE.Vector3().setFromMatrixColumn(options.camera.matrixWorld, 1)
    this.start = options.getTarget().clone().addScaledVector(right, 900).addScaledVector(up, 760)

    const makeSprite = (map: THREE.Texture, size: number) => {
      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map,
          color: options.color,
          transparent: true,
          blending: THREE.AdditiveBlending,
          depthTest: false,
          depthWrite: false,
        })
      )
      sprite.renderOrder = RENDER_ORDER.overlay
      sprite.scale.setScalar(size)
      scene.add(sprite)
      return sprite
    }
    this.head = makeSprite(options.glowTexture, 150)
    this.rays = makeSprite(options.raysTexture, 260)

    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3))
    geometry.setAttribute(
      'color',
      new THREE.BufferAttribute(new Float32Array([1, 0.95, 0.7, 1, 1, 0.7, 0.2, 0]), 4)
    )
    this.trail = new THREE.Line(
      geometry,
      new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        depthTest: false,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
    )
    this.trail.frustumCulled = false
    this.trail.renderOrder = RENDER_ORDER.overlay
    scene.add(this.trail)
  }

  update(time: number): boolean {
    const elapsed = time - this.startTime
    const target = this.getTarget()

    if (!this.impacted) {
      // 越落越快
      const progress = Math.min(1, Math.max(0, elapsed / GOLD_FALL_MS))
      const eased = progress * progress
      const position = this.start.clone().lerp(target, eased)
      const tail = position.clone().lerp(this.start, 0.35)
      this.head.position.copy(position)
      this.rays.position.copy(position)
      this.rays.material.rotation = elapsed * 0.004
      const positions = this.trail.geometry.attributes.position as THREE.BufferAttribute
      positions.setXYZ(0, position.x, position.y, position.z)
      positions.setXYZ(1, tail.x, tail.y, tail.z)
      positions.needsUpdate = true

      if (progress >= 1) {
        this.impacted = true
        this.impactAt = time
        this.trail.visible = false
        this.onImpact(time, target.clone())
      }
      return false
    }

    // 砸中之后光芒炸开再淡掉
    const after = (time - this.impactAt) / 900
    this.head.position.copy(target)
    this.rays.position.copy(target)
    this.head.material.opacity = Math.max(0, 1 - after)
    this.head.scale.setScalar(150 + after * 300)
    this.rays.material.opacity = Math.max(0, 1 - after)
    this.rays.scale.setScalar(260 + easeOutCubic(Math.min(1, after)) * 1100)
    this.rays.material.rotation += 0.01
    return after >= 1
  }

  dispose(): void {
    this.scene.remove(this.head, this.rays, this.trail)
    this.head.material.dispose()
    this.rays.material.dispose()
    this.trail.geometry.dispose()
    this.trail.material.dispose()
  }
}
