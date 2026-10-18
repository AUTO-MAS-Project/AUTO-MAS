import {
  Color,
  HalfFloatType,
  LinearFilter,
  Mesh,
  OrthographicCamera,
  PlaneGeometry,
  Scene,
  ShaderMaterial,
  Vector3,
  Vector4,
  WebGLRenderer,
  WebGLRenderTarget,
  type Texture,
} from 'three'
import { FLUID_DT, STAR_COLORS, type FluidSplat } from './visualState'
import {
  ATLAS_COLUMNS,
  ATLAS_ROWS,
  GRID_SIZE,
  advect3d,
  divergence3d,
  fluidVertex,
  inject3d,
  pressure3d,
  project3d,
} from './fluid3dShaders'

const PRESSURE_ITERATIONS = 12

/** 真正的三维速度/染料场；atlas 只改变存储布局，不把 xyz 投影到屏幕。 */
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
  private readonly inject: ShaderMaterial
  private readonly diverge: ShaderMaterial
  private readonly solve: ShaderMaterial
  private readonly project: ShaderMaterial
  private disposed = false

  constructor(private readonly renderer: WebGLRenderer) {
    this.advect = this.material(advect3d)
    this.inject = this.material(inject3d)
    this.diverge = this.material(divergence3d)
    this.solve = this.material(pressure3d)
    this.project = this.material(project3d)
    this.quad = new Mesh(this.geometry, this.advect)
    this.quad.frustumCulled = false
    this.scene.add(this.quad)
    try {
      const gl = renderer.getContext()
      if (!gl.getExtension('EXT_color_buffer_float')) throw new Error('Float field unavailable')
      this.velocity = [this.target(), this.target()]
      this.dye = [this.target(), this.target()]
      this.pressure = [this.target(), this.target()]
      this.divergence = this.target()
      for (const target of this.targets) {
        renderer.setRenderTarget(target)
        if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE)
          throw new Error('Incomplete 3D field framebuffer')
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

  update(dt: number, sources: readonly FluidSplat[]): void {
    if (this.disposed || !Number.isFinite(dt) || dt <= 0) return
    const time = Math.min(dt, FLUID_DT)
    const previous = this.renderer.getRenderTarget()
    this.advection(this.velocity, this.velocity[0].texture, time, 1.2)
    const splats = sources.slice(0, 24)
    const u = this.inject.uniforms
    u.sourceCount.value = splats.length
    for (let i = 0; i < splats.length; i++) {
      const point = splats[i]
      u.points.value[i].set(point.x, point.y, point.z, point.amount)
      u.momenta.value[i].set(point.vx, point.vy, point.vz)
      u.colors.value[i].setHex(STAR_COLORS[point.star])
    }
    if (splats.length) {
      u.dyeMode.value = 0
      this.ping(this.inject, this.velocity, { source: this.velocity[0].texture })
      u.dyeMode.value = 1
      this.ping(this.inject, this.dye, { source: this.dye[0].texture })
    }
    this.pass(this.diverge, this.divergence, { velocity: this.velocity[0].texture })
    for (const target of this.pressure) {
      this.renderer.setRenderTarget(target)
      this.renderer.clear()
    }
    for (let i = 0; i < PRESSURE_ITERATIONS; i++)
      this.ping(this.solve, this.pressure, {
        pressure: this.pressure[0].texture,
        divergence: this.divergence.texture,
      })
    this.ping(this.project, this.velocity, {
      pressure: this.pressure[0].texture,
      velocity: this.velocity[0].texture,
    })
    this.advection(this.dye, this.velocity[0].texture, time, 0.55)
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

  private material(fragmentShader: string): ShaderMaterial {
    const material = new ShaderMaterial({
      vertexShader: fluidVertex,
      fragmentShader,
      depthTest: false,
      depthWrite: false,
      uniforms: {
        velocity: { value: null },
        source: { value: null },
        pressure: { value: null },
        divergence: { value: null },
        dt: { value: 0 },
        dissipation: { value: 0 },
        dyeMode: { value: 0 },
        sourceCount: { value: 0 },
        points: { value: Array.from({ length: 24 }, () => new Vector4()) },
        momenta: { value: Array.from({ length: 24 }, () => new Vector3()) },
        colors: { value: Array.from({ length: 24 }, () => new Color()) },
      },
    })
    this.materials.push(material)
    return material
  }
  private target(): WebGLRenderTarget {
    const target = new WebGLRenderTarget(GRID_SIZE * ATLAS_COLUMNS, GRID_SIZE * ATLAS_ROWS, {
      type: HalfFloatType,
      minFilter: LinearFilter,
      magFilter: LinearFilter,
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
    this.ping(this.advect, pair, { velocity, source: pair[0].texture })
  }
}
