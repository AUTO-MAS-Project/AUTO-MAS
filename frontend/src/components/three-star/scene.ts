import {
  Color,
  Mesh,
  OrthographicCamera,
  PerspectiveCamera,
  PlaneGeometry,
  Scene,
  ShaderMaterial,
  SphereGeometry,
  Sprite,
  SpriteMaterial,
  Vector2,
  Vector3,
  WebGLRenderer,
} from 'three'
import { StarFluid } from './fluid'
import { FLUID_DT, STAR_COLORS, allowsGpu, pathSplats, type EmissionPoint } from './visualState'
import {
  coronaFragment,
  fluidCompositeFragment,
  quadVertex,
  starFragment,
  starVertex,
} from './starShaders'
import type { TaskFlash } from './taskFeedback'

export interface ProjectedStar {
  x: number
  y: number
  outside: boolean
  direction: number
}

/** 仅消费已接受的物理快照；球体拥有深度，二维流体先合成在所有球体后方。 */
export class ThreeStarScene {
  private readonly renderer: WebGLRenderer
  private readonly world = new Scene()
  private readonly screen = new Scene()
  private readonly camera = new PerspectiveCamera(34, 1, 0.05, 300)
  private readonly screenCamera = new OrthographicCamera(-1, 1, 1, -1, 0, 1)
  private readonly sphere = new SphereGeometry(1, 48, 32)
  private readonly plane = new PlaneGeometry(2, 2)
  private readonly materials: ShaderMaterial[] = []
  private readonly stars: Mesh<SphereGeometry, ShaderMaterial>[] = []
  private readonly coronas: Mesh<PlaneGeometry, ShaderMaterial>[] = []
  private readonly fluid: StarFluid
  private readonly composite: ShaderMaterial
  private readonly pulse: Sprite
  private readonly pulseMaterial = new SpriteMaterial({
    color: 0xffdfa5,
    transparent: true,
    opacity: 0,
    depthWrite: false,
  })
  private previous: EmissionPoint[] | null = null
  private fluidElapsed = 0
  private elapsed = 0
  private flash: { kind: TaskFlash; at: number } | null = null
  private distance = 3.8
  private lastFluidDistance = 3.8
  private pointer = new Vector2()
  private lastFluidPointer = new Vector2()
  private readonly tmp = new Vector3()
  private disposed = false

  constructor(canvas: HTMLCanvasElement, hardware: boolean | null, dark: boolean) {
    const context = canvas.getContext('webgl2', {
      alpha: true,
      antialias: false,
      failIfMajorPerformanceCaveat: true,
    })
    if (!context) throw new Error('WebGL2 unavailable')
    const debug = context.getExtension('WEBGL_debug_renderer_info')
    const rendererName = debug ? String(context.getParameter(debug.UNMASKED_RENDERER_WEBGL)) : null
    if (!allowsGpu(rendererName, hardware)) {
      context.getExtension('WEBGL_lose_context')?.loseContext()
      throw new Error('Hardware rendering unconfirmed')
    }
    this.renderer = new WebGLRenderer({ canvas, context, alpha: true, antialias: false })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25))
    this.renderer.autoClear = false
    this.renderer.setClearColor(0, 0)
    this.renderer.debug.onShaderError = () => {
      throw new Error('Star shader compilation failed')
    }
    try {
      this.fluid = new StarFluid(this.renderer)
      this.composite = new ShaderMaterial({
        vertexShader: quadVertex,
        fragmentShader: fluidCompositeFragment,
        transparent: true,
        depthTest: false,
        depthWrite: false,
        uniforms: { dye: { value: this.fluid.texture }, dark: { value: dark ? 1 : 0 } },
      })
      this.materials.push(this.composite)
      this.screen.add(new Mesh(this.plane, this.composite))
      for (const color of STAR_COLORS) {
        const uniforms = {
          color: { value: new Color(color) },
          time: { value: 0 },
          dark: { value: dark ? 1 : 0 },
          flash: { value: 0 },
        }
        const surface = new ShaderMaterial({
          vertexShader: starVertex,
          fragmentShader: starFragment,
          uniforms,
        })
        const corona = new ShaderMaterial({
          vertexShader: quadVertex,
          fragmentShader: coronaFragment,
          uniforms: { ...uniforms, color: { value: new Color(color) }, flash: { value: 0 } },
          transparent: true,
          depthWrite: false,
        })
        this.materials.push(surface, corona)
        const star = new Mesh(this.sphere, surface)
        star.scale.setScalar(0.17)
        const glow = new Mesh(this.plane, corona)
        glow.scale.setScalar(0.37)
        this.stars.push(star)
        this.coronas.push(glow)
        this.world.add(star, glow)
      }
      this.pulse = new Sprite(this.pulseMaterial)
      this.pulse.scale.setScalar(0.04)
      this.world.add(this.pulse)
      this.resize()
    } catch (error) {
      this.dispose()
      throw error
    }
  }

  setDark(dark: boolean): void {
    this.materials.forEach(material => {
      material.uniforms.dark.value = dark ? 1 : 0
    })
  }

  setPointer(x: number, y: number): void {
    this.pointer.set(x * 0.025, y * 0.025)
  }

  resize(): void {
    const rect = this.renderer.domElement.getBoundingClientRect()
    const width = Math.max(1, rect.width)
    const height = Math.max(1, rect.height)
    const scale = Math.min(1, 900 / width, 480 / height)
    this.renderer.setSize(Math.round(width * scale), Math.round(height * scale), false)
    this.camera.aspect = width / height
    this.camera.updateProjectionMatrix()
    this.clearTransient()
  }

  trigger(kind: TaskFlash): void {
    this.flash = { kind, at: this.elapsed }
  }

  /** 暂停/恢复、重置及大幅换镜头清除显示残留，不接触物理状态。 */
  clearTransient(): void {
    this.fluid?.clear()
    this.previous = null
    this.fluidElapsed = 0
    this.flash = null
    if (this.pulse) this.pulseMaterial.opacity = 0
  }

  render(state: ArrayLike<number>, dt = 0, moving = false): ProjectedStar[] {
    this.elapsed += dt
    let extent = 1
    for (let i = 0; i < 3; i++) {
      const position = this.stars[i].position.set(state[i * 6], state[i * 6 + 1], state[i * 6 + 2])
      this.coronas[i].position.copy(position)
      extent = Math.max(extent, position.length())
    }
    // 只调整相机。展示尺度上限之外仍保留物理位置，由方向提示告知用户。
    const wanted = Math.min(80, Math.max(3.8, (extent * 3.4) / Math.min(1, this.camera.aspect)))
    this.distance += (wanted - this.distance) * (1 - Math.exp(-dt * 2))
    this.camera.position.set(
      this.pointer.x * this.distance,
      this.distance * (0.38 + this.pointer.y),
      this.distance
    )
    this.camera.lookAt(0, 0, 0)
    this.camera.updateMatrixWorld()
    const cameraChanged =
      Math.abs(this.distance / this.lastFluidDistance - 1) > 0.015 ||
      this.pointer.distanceTo(this.lastFluidPointer) > 0.002
    if (cameraChanged) {
      this.clearTransient()
      this.lastFluidDistance = this.distance
      this.lastFluidPointer.copy(this.pointer)
    }
    const points: EmissionPoint[] = this.stars.map(star => {
      this.tmp.copy(star.position).project(this.camera)
      return { x: this.tmp.x * 0.5 + 0.5, y: this.tmp.y * 0.5 + 0.5 }
    })
    if (moving && dt > 0) {
      this.fluidElapsed = Math.min(FLUID_DT * 2, this.fluidElapsed + dt)
      if (this.fluidElapsed >= FLUID_DT) {
        const sources = this.previous
          ? points.flatMap((point, star) =>
              pathSplats(this.previous![star], point, this.fluidElapsed, star)
            )
          : []
        this.fluid.update(FLUID_DT, sources, this.camera.aspect)
        // 一帧最多一次流体步；慢机降低显示速度，不追赶欠账。
        this.fluidElapsed = 0
        this.previous = points
      }
    } else this.previous = null
    this.composite.uniforms.dye.value = this.fluid.texture
    this.updateLight()
    for (let i = 0; i < 3; i++) {
      this.stars[i].material.uniforms.time.value = this.elapsed + i * 9
      this.coronas[i].material.uniforms.time.value = this.elapsed + i * 9
      this.coronas[i].quaternion.copy(this.camera.quaternion)
    }
    this.renderer.setRenderTarget(null)
    this.renderer.clear()
    this.renderer.render(this.screen, this.screenCamera)
    this.renderer.render(this.world, this.camera)
    return points.map((point, i) => {
      this.tmp.copy(this.stars[i].position).project(this.camera)
      return {
        x: Math.max(0.05, Math.min(0.9, point.x)),
        y: Math.max(0.08, Math.min(0.88, 1 - point.y)),
        outside:
          point.x < 0 || point.x > 1 || point.y < 0 || point.y > 1 || Math.abs(this.tmp.z) > 1,
        direction: (Math.atan2(0.5 - point.y, point.x - 0.5) * 180) / Math.PI,
      }
    })
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.fluid?.dispose()
    this.materials.forEach(material => material.dispose())
    this.sphere.dispose()
    this.plane.dispose()
    this.pulseMaterial.dispose()
    this.world.clear()
    this.screen.clear()
    this.renderer.dispose()
    // 所有资源已释放；保留 canvas 上下文以便低性能模式切回及 contextrestored 重建。
  }

  private updateLight(): void {
    this.coronas[2].material.uniforms.color.value.setHex(STAR_COLORS[2])
    const age = this.flash ? this.elapsed - this.flash.at : Infinity
    const intensity = age < 1.4 ? Math.sin((Math.PI * age) / 1.4) * 0.7 : 0
    this.stars.forEach(star => {
      star.material.uniforms.flash.value = 0
    })
    this.coronas.forEach(glow => {
      glow.material.uniforms.flash.value = 0
    })
    this.pulseMaterial.opacity = 0
    if (!this.flash || age >= 1.4) {
      this.flash = null
      return
    }
    if (this.flash.kind === 'start') {
      this.pulse.position.lerpVectors(this.stars[0].position, this.stars[1].position, age / 1.4)
      this.pulseMaterial.opacity = intensity * 0.65
    } else {
      const colors = { success: 0x52c489, error: 0xe47b86, cancelled: 0xd2ac72 }
      this.coronas[2].material.uniforms.color.value.setHex(colors[this.flash.kind])
      this.coronas[2].material.uniforms.flash.value = intensity
    }
  }
}
