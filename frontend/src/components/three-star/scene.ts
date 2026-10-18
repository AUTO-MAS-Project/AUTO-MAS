import {
  Color,
  HalfFloatType,
  LinearFilter,
  Mesh,
  MeshBasicMaterial,
  OrthographicCamera,
  PerspectiveCamera,
  PlaneGeometry,
  RepeatWrapping,
  Scene,
  ShaderMaterial,
  SphereGeometry,
  SRGBColorSpace,
  TextureLoader,
  Vector2,
  Vector3,
  WebGLRenderer,
  WebGLRenderTarget,
  type Texture,
} from 'three'
import skyUrl from '@/assets/three-star/starmap_4k.jpg'
import { StarFluid } from './fluid'
import { FIELD_HALF_SIZE } from './fluid3dShaders'
import { FLUID_DT, STAR_COLORS, allowsGpu, pathSplats, type EmissionPoint } from './visualState'
import { starFragment, starVertex } from './starShaders'
import { screenVertex, skyFragment, volumeFragment, volumeOutputFragment } from './volumeShaders'
import type { TaskFlash } from './taskFeedback'

export interface ProjectedStar {
  x: number
  y: number
  outside: boolean
  direction: number
}
const STAR_RADIUS = 0.17
const MAX_DRAWING_PIXELS = 2_500_000

/** 只消费已接受快照；世界空间球体、体积星冕及三维速度/染料场。 */
export class ThreeStarScene {
  readonly ready: Promise<void>
  private readonly renderer: WebGLRenderer
  private readonly world = new Scene()
  private readonly screen = new Scene()
  private readonly camera = new PerspectiveCamera(34, 1, 0.05, 300)
  private readonly screenCamera = new OrthographicCamera(-1, 1, 1, -1, 0, 1)
  private readonly sphere = new SphereGeometry(1, 64, 48)
  private readonly plane = new PlaneGeometry(2, 2)
  private readonly materials: ShaderMaterial[] = []
  private readonly stars: Mesh<SphereGeometry, ShaderMaterial>[] = []
  private readonly colors = STAR_COLORS.map(color => new Color(color))
  private readonly centers = [new Vector3(), new Vector3(), new Vector3()]
  private readonly fluid: StarFluid
  private readonly sky: ShaderMaterial
  private readonly volume: ShaderMaterial
  private readonly output: ShaderMaterial
  private readonly volumeTarget = new WebGLRenderTarget(1, 1, {
    type: HalfFloatType,
    minFilter: LinearFilter,
    magFilter: LinearFilter,
    depthBuffer: false,
  })
  private readonly quad: Mesh<PlaneGeometry, ShaderMaterial>
  private readonly pulseMaterial = new MeshBasicMaterial({
    color: 0xffdfa5,
    transparent: true,
    opacity: 0,
    depthWrite: false,
  })
  private readonly pulse = new Mesh(this.sphere, this.pulseMaterial)
  private skyTexture: Texture | null = null
  private previous: EmissionPoint[] | null = null
  private fluidElapsed = 0
  private elapsed = 0
  private flash: { kind: TaskFlash; at: number } | null = null
  private distance = 3.8
  private pointer = new Vector2()
  private readonly tmp = new Vector3()
  private disposed = false

  constructor(canvas: HTMLCanvasElement, hardware: boolean | null, dark: boolean) {
    const context = canvas.getContext('webgl2', {
      alpha: true,
      antialias: true,
      failIfMajorPerformanceCaveat: true,
    })
    if (!context) throw new Error('WebGL2 unavailable')
    const debug = context.getExtension('WEBGL_debug_renderer_info')
    const name = debug ? String(context.getParameter(debug.UNMASKED_RENDERER_WEBGL)) : null
    if (!allowsGpu(name, hardware) || context.getParameter(context.MAX_TEXTURE_SIZE) < 4096) {
      context.getExtension('WEBGL_lose_context')?.loseContext()
      throw new Error('Hardware rendering or 4K sky unavailable')
    }
    this.renderer = new WebGLRenderer({ canvas, context, alpha: true, antialias: true })
    this.renderer.autoClear = false
    this.renderer.setClearColor(0, 0)
    this.renderer.debug.onShaderError = () => {
      throw new Error('Star shader compilation failed')
    }
    try {
      this.fluid = new StarFluid(this.renderer)
      const view = {
        inverseProjection: { value: this.camera.projectionMatrixInverse },
        viewToWorld: { value: this.camera.matrixWorld },
        dark: { value: dark ? 1 : 0 },
      }
      this.sky = new ShaderMaterial({
        vertexShader: screenVertex,
        fragmentShader: skyFragment,
        depthTest: false,
        depthWrite: false,
        uniforms: { ...view, sky: { value: null } },
      })
      this.volume = new ShaderMaterial({
        vertexShader: screenVertex,
        fragmentShader: volumeFragment,
        depthTest: false,
        depthWrite: false,
        uniforms: {
          ...view,
          dye: { value: this.fluid.texture },
          eye: { value: this.camera.position },
          centers: { value: this.centers },
          colors: { value: this.colors },
          flashes: { value: [0, 0, 0] },
          time: { value: 0 },
        },
      })
      this.output = new ShaderMaterial({
        vertexShader: screenVertex,
        fragmentShader: volumeOutputFragment,
        transparent: true,
        depthTest: false,
        depthWrite: false,
        uniforms: { volume: { value: this.volumeTarget.texture } },
      })
      this.materials.push(this.sky, this.volume, this.output)
      this.quad = new Mesh(this.plane, this.sky)
      this.quad.frustumCulled = false
      this.screen.add(this.quad)
      for (const color of STAR_COLORS) {
        const surface = new ShaderMaterial({
          vertexShader: starVertex,
          fragmentShader: starFragment,
          uniforms: {
            color: { value: new Color(color) },
            time: { value: 0 },
            dark: { value: dark ? 1 : 0 },
            flash: { value: 0 },
          },
        })
        this.materials.push(surface)
        const star = new Mesh(this.sphere, surface)
        star.scale.setScalar(STAR_RADIUS)
        this.stars.push(star)
        this.world.add(star)
      }
      this.pulse.scale.setScalar(0.025)
      this.world.add(this.pulse)
      this.resize()
      this.ready = new TextureLoader().loadAsync(skyUrl).then(texture => {
        if (this.disposed) {
          texture.dispose()
          return
        }
        this.skyTexture = texture
        texture.colorSpace = SRGBColorSpace
        texture.wrapS = RepeatWrapping
        texture.anisotropy = Math.min(4, this.renderer.capabilities.getMaxAnisotropy())
        this.sky.uniforms.sky.value = texture
      })
    } catch (error) {
      this.dispose()
      throw error
    }
  }

  setDark(dark: boolean): void {
    this.materials.forEach(material => {
      if (material.uniforms.dark) material.uniforms.dark.value = dark ? 1 : 0
    })
  }
  setPointer(x: number, y: number): void {
    this.pointer.set(x * 0.025, y * 0.025)
  }

  resize(): void {
    const rect = this.renderer.domElement.getBoundingClientRect()
    const width = Math.max(1, rect.width),
      height = Math.max(1, rect.height)
    const scale = Math.min(1, 1920 / width, 720 / height)
    const w = Math.round(width * scale),
      h = Math.round(height * scale)
    const dpr = Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(MAX_DRAWING_PIXELS / (w * h)))
    this.renderer.setPixelRatio(dpr)
    this.renderer.setSize(w, h, false)
    this.camera.aspect = width / height
    this.camera.updateProjectionMatrix()
    // 只降低柔和气体的积分图像尺寸；球面与星图走最终画布分辨率。
    const volumeScale = Math.min(0.65, 960 / (w * dpr), 384 / (h * dpr))
    this.volumeTarget.setSize(
      Math.max(1, Math.round(w * dpr * volumeScale)),
      Math.max(1, Math.round(h * dpr * volumeScale))
    )
    const gl = this.renderer.getContext()
    this.renderer.setRenderTarget(this.volumeTarget)
    const complete = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE
    this.renderer.setRenderTarget(null)
    if (!complete) throw new Error('Incomplete volume framebuffer')
  }

  trigger(kind: TaskFlash): void {
    this.flash = { kind, at: this.elapsed }
  }

  /** 暂停/恢复和重置清除显示残留；相机移动不再清场或改变流体坐标。 */
  clearTransient(): void {
    this.fluid?.clear()
    this.previous = null
    this.fluidElapsed = 0
    this.flash = null
    this.pulseMaterial.opacity = 0
  }

  render(state: ArrayLike<number>, dt = 0, moving = false): ProjectedStar[] {
    this.elapsed += dt
    let extent = 1
    for (let i = 0; i < 3; i++) {
      const p = this.stars[i].position.set(state[i * 6], state[i * 6 + 1], state[i * 6 + 2])
      this.centers[i].copy(p)
      extent = Math.max(extent, p.length())
    }
    // 只拉远观察点，绝不拉回逃逸天体。最大距离之外仍显示方向标注。
    const wanted = Math.min(80, Math.max(3.8, (extent * 3.4) / Math.min(1, this.camera.aspect)))
    this.distance += (wanted - this.distance) * (1 - Math.exp(-dt * 2))
    this.camera.position.set(
      this.pointer.x * this.distance,
      this.distance * (0.38 + this.pointer.y),
      this.distance
    )
    this.camera.lookAt(0, 0, 0)
    this.camera.updateMatrixWorld()
    // 注入点始终在固定世界体积中；视差/拉远只改变采样射线。
    const points = this.stars.map(star => ({
      x: star.position.x / (2 * FIELD_HALF_SIZE) + 0.5,
      y: star.position.y / (2 * FIELD_HALF_SIZE) + 0.5,
      z: star.position.z / (2 * FIELD_HALF_SIZE) + 0.5,
    }))
    if (moving && dt > 0) {
      this.fluidElapsed = Math.min(FLUID_DT * 2, this.fluidElapsed + dt)
      if (this.fluidElapsed >= FLUID_DT) {
        const sources = this.previous
          ? points.flatMap((point, star) =>
              pathSplats(this.previous![star], point, this.fluidElapsed, star)
            )
          : []
        this.fluid.update(FLUID_DT, sources)
        this.fluidElapsed = 0
        this.previous = points
      }
    } else {
      this.previous = null
      this.fluidElapsed = 0
    }
    this.volume.uniforms.dye.value = this.fluid.texture
    this.volume.uniforms.time.value = this.elapsed
    this.updateLight()
    for (let i = 0; i < 3; i++) this.stars[i].material.uniforms.time.value = this.elapsed + i * 9

    this.quad.material = this.volume
    this.renderer.setRenderTarget(this.volumeTarget)
    this.renderer.clear()
    this.renderer.render(this.screen, this.screenCamera)
    this.renderer.setRenderTarget(null)
    this.renderer.clear()
    this.quad.material = this.sky
    this.renderer.render(this.screen, this.screenCamera)
    this.renderer.render(this.world, this.camera)
    this.quad.material = this.output
    this.renderer.render(this.screen, this.screenCamera)
    return this.stars.map(star => {
      this.tmp.copy(star.position).project(this.camera)
      const x = this.tmp.x * 0.5 + 0.5,
        y = 1 - (this.tmp.y * 0.5 + 0.5)
      return {
        x: Math.max(0.05, Math.min(0.9, x)),
        y: Math.max(0.08, Math.min(0.88, y)),
        outside: x < 0 || x > 1 || y < 0 || y > 1 || Math.abs(this.tmp.z) > 1,
        direction: (Math.atan2(y - 0.5, x - 0.5) * 180) / Math.PI,
      }
    })
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.fluid?.dispose()
    this.skyTexture?.dispose()
    this.volumeTarget.dispose()
    this.materials.forEach(material => material.dispose())
    this.sphere.dispose()
    this.plane.dispose()
    this.pulseMaterial.dispose()
    this.world.clear()
    this.screen.clear()
    this.renderer.dispose()
    // 释放资源但保留 canvas 上下文，允许 contextrestored 及性能设置切回时重建。
  }

  private updateLight(): void {
    this.colors[2].setHex(STAR_COLORS[2])
    const flashes = this.volume.uniforms.flashes.value as number[]
    flashes.fill(0)
    const age = this.flash ? this.elapsed - this.flash.at : Infinity
    const intensity = age < 1.4 ? Math.sin((Math.PI * age) / 1.4) * 0.7 : 0
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
      this.colors[2].setHex(colors[this.flash.kind])
      flashes[2] = intensity
    }
  }
}
