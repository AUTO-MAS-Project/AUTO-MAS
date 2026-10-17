import {
  Color,
  HalfFloatType,
  Mesh,
  NearestFilter,
  OrthographicCamera,
  PlaneGeometry,
  Scene,
  ShaderMaterial,
  Vector2,
  Vector3,
  WebGLRenderer,
  WebGLRenderTarget,
  type Texture,
} from 'three'
import {
  advectionFragmentShaderSource,
  divergenceFragmentShaderSource,
  gradientSubtractFragmentShaderSource,
  pressureFragmentShaderSource,
} from '@/components/inspira/fluidShaders'
import { FLUID_DT, STAR_COLORS, type FluidSplat } from './visualState'

const VELOCITY_SIZE = 96
const DYE_SIZE = 256
const PRESSURE_ITERATIONS = 12

const vertexShader = `
  varying vec2 vUv;
  varying vec2 vL; varying vec2 vR; varying vec2 vT; varying vec2 vB;
  uniform vec2 texelSize;
  void main() {
    vUv = uv;
    vL = uv - vec2(texelSize.x, 0.0); vR = uv + vec2(texelSize.x, 0.0);
    vT = uv + vec2(0.0, texelSize.y); vB = uv - vec2(0.0, texelSize.y);
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`
const splatShader = `
  varying vec2 vUv;
  uniform sampler2D uTarget;
  uniform vec2 point;
  uniform vec3 impulse;
  uniform float aspectRatio;
  uniform float limit;
  void main() {
    vec2 p = vUv - point; p.x *= aspectRatio;
    float weight = exp(-dot(p,p) / 0.00018);
    vec3 result = texture2D(uTarget, vUv).xyz + impulse * weight;
    gl_FragColor = vec4(clamp(result, vec3(-limit), vec3(limit)), 1.0);
  }
`

/** 单向、屏幕空间视觉流体。复用光标的四个纯 shader，不持有输入或动画循环。 */
export class StarFluid {
  private readonly targets: WebGLRenderTarget[] = []
  private readonly materials: ShaderMaterial[] = []
  private readonly scene = new Scene()
  private readonly camera = new OrthographicCamera(-1, 1, 1, -1, 0, 1)
  private readonly geometry = new PlaneGeometry(2, 2)
  private readonly quad: Mesh<PlaneGeometry, ShaderMaterial>
  private readonly velocity: WebGLRenderTarget[]
  private readonly dye: WebGLRenderTarget[]
  private readonly pressure: WebGLRenderTarget[]
  private readonly divergence: WebGLRenderTarget
  private readonly advect: ShaderMaterial
  private readonly diverge: ShaderMaterial
  private readonly solvePressure: ShaderMaterial
  private readonly project: ShaderMaterial
  private readonly splat: ShaderMaterial
  private disposed = false

  constructor(private readonly renderer: WebGLRenderer) {
    this.advect = this.material(advectionFragmentShaderSource, { MANUAL_FILTERING: 1 })
    this.diverge = this.material(divergenceFragmentShaderSource)
    this.solvePressure = this.material(pressureFragmentShaderSource)
    this.project = this.material(gradientSubtractFragmentShaderSource)
    this.splat = this.material(splatShader)
    this.quad = new Mesh(this.geometry, this.splat)
    this.quad.frustumCulled = false
    this.scene.add(this.quad)
    try {
      const gl = renderer.getContext()
      if (
        !gl.getExtension('EXT_color_buffer_float') ||
        gl.getParameter(gl.MAX_TEXTURE_SIZE) < DYE_SIZE
      )
        throw new Error('Float framebuffer unavailable')
      this.velocity = [this.target(VELOCITY_SIZE), this.target(VELOCITY_SIZE)]
      this.dye = [this.target(DYE_SIZE), this.target(DYE_SIZE)]
      this.pressure = [this.target(VELOCITY_SIZE), this.target(VELOCITY_SIZE)]
      this.divergence = this.target(VELOCITY_SIZE)
      for (const target of this.targets) {
        renderer.setRenderTarget(target)
        if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE)
          throw new Error('Incomplete float framebuffer')
      }
      renderer.setRenderTarget(null)
      this.clear()
    } catch (error) {
      this.dispose()
      throw error
    }
  }

  get texture(): Texture {
    return this.dye[0].texture
  }

  clear(): void {
    const previous = this.renderer.getRenderTarget()
    const color = this.renderer.getClearColor(new Color())
    const alpha = this.renderer.getClearAlpha()
    this.renderer.setClearColor(0, 0)
    for (const target of this.targets) {
      this.renderer.setRenderTarget(target)
      this.renderer.clear()
    }
    this.renderer.setRenderTarget(previous)
    this.renderer.setClearColor(color, alpha)
  }

  update(dt: number, sources: readonly FluidSplat[], aspect: number): void {
    if (this.disposed || !Number.isFinite(dt) || dt <= 0) return
    const time = Math.min(dt, FLUID_DT)
    const previous = this.renderer.getRenderTarget()
    // 平流速度后再注入、投影；压力每次归零，防止旧解无限累积。
    this.advection(this.velocity, this.velocity[0].texture, time, 1.5)
    for (const source of sources.slice(0, 3 * 8)) {
      const u = this.splat.uniforms
      u.point.value.set(source.x, source.y)
      u.aspectRatio.value = aspect
      u.limit.value = 48
      u.impulse.value.set(
        source.vx * 96 * source.amount * 18,
        source.vy * 96 * source.amount * 18,
        0
      )
      this.ping(this.splat, this.velocity, { uTarget: this.velocity[0].texture })
      const color = new Color(STAR_COLORS[source.star])
      const intensity = source.amount * (1.5 + Math.min(1, Math.hypot(source.vx, source.vy) * 2))
      u.limit.value = 2
      u.impulse.value.set(color.r, color.g, color.b).multiplyScalar(intensity)
      this.ping(this.splat, this.dye, { uTarget: this.dye[0].texture })
    }
    this.pass(this.diverge, this.divergence, { uVelocity: this.velocity[0].texture })
    for (const target of this.pressure) {
      this.renderer.setRenderTarget(target)
      this.renderer.clear()
    }
    for (let i = 0; i < PRESSURE_ITERATIONS; i++)
      this.ping(this.solvePressure, this.pressure, {
        uPressure: this.pressure[0].texture,
        uDivergence: this.divergence.texture,
      })
    this.ping(this.project, this.velocity, {
      uPressure: this.pressure[0].texture,
      uVelocity: this.velocity[0].texture,
    })
    this.advection(this.dye, this.velocity[0].texture, time, 0.8)
    this.renderer.setRenderTarget(previous)
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.renderer.setRenderTarget(null)
    this.targets.forEach(target => target.dispose())
    this.materials.forEach(material => material.dispose())
    this.geometry.dispose()
    this.scene.clear()
  }

  private material(fragmentShader: string, defines = {}): ShaderMaterial {
    const material = new ShaderMaterial({
      vertexShader,
      fragmentShader,
      defines,
      depthTest: false,
      depthWrite: false,
      uniforms: {
        texelSize: { value: new Vector2(1 / VELOCITY_SIZE, 1 / VELOCITY_SIZE) },
        dyeTexelSize: { value: new Vector2() },
        dt: { value: 0 },
        dissipation: { value: 0 },
        uVelocity: { value: null },
        uSource: { value: null },
        uTarget: { value: null },
        uPressure: { value: null },
        uDivergence: { value: null },
        point: { value: new Vector2() },
        impulse: { value: new Vector3() },
        limit: { value: 2 },
        aspectRatio: { value: 1 },
      },
    })
    this.materials.push(material)
    return material
  }
  private target(size: number): WebGLRenderTarget {
    const target = new WebGLRenderTarget(size, size, {
      type: HalfFloatType,
      minFilter: NearestFilter,
      magFilter: NearestFilter,
      depthBuffer: false,
      stencilBuffer: false,
    })
    this.targets.push(target)
    return target
  }
  private pass(
    material: ShaderMaterial,
    target: WebGLRenderTarget,
    textures: Record<string, Texture>
  ): void {
    for (const [name, texture] of Object.entries(textures)) material.uniforms[name].value = texture
    this.quad.material = material
    this.renderer.setRenderTarget(target)
    this.renderer.render(this.scene, this.camera)
  }
  private ping(
    material: ShaderMaterial,
    pair: WebGLRenderTarget[],
    textures: Record<string, Texture>
  ): void {
    this.pass(material, pair[1], textures)
    pair.reverse()
  }
  private advection(
    pair: WebGLRenderTarget[],
    velocity: Texture,
    dt: number,
    dissipation: number
  ): void {
    this.advect.uniforms.dt.value = dt
    this.advect.uniforms.dissipation.value = dissipation
    this.advect.uniforms.dyeTexelSize.value.set(1 / pair[0].width, 1 / pair[0].height)
    this.ping(this.advect, pair, { uVelocity: velocity, uSource: pair[0].texture })
  }
}
