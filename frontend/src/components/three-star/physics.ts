/** 无量纲牛顿点质量；所有状态与积分运算均使用 JS double，不依赖显示层。 */
export interface BodyInitial {
  mass: number
  position: readonly [number, number, number]
  velocity: readonly [number, number, number]
}

export const PHYSICS_MODEL = {
  units: 'G=1, dimensionless mass/length/time',
  integrator: 'Dormand-Prince 5(4), revision 1',
  relativeTolerance: 1e-9,
  absoluteTolerance: 1e-11,
  minStep: 1e-7,
  maxStep: 0.02,
  minSeparation: 1e-4,
} as const

/** 自定义初值：略离开同一平面的三个等质量点；不承诺周期性、稳定性或混沌。 */
export const DEFAULT_BODIES: readonly BodyInitial[] = [
  { mass: 1, position: [-0.97, 0.243, 0.15], velocity: [0.466, 0.432, 0.08] },
  { mass: 1, position: [0.97, -0.243, -0.15], velocity: [0.466, 0.432, -0.08] },
  { mass: 1, position: [0, 0, 0], velocity: [-0.932, -0.864, 0] },
]

export type PhysicsFault = 'nearEncounter' | 'precision' | 'nonFinite'
export interface SolverOptions {
  relativeTolerance: number
  absoluteTolerance: number
  minStep: number
  maxStep: number
  minSeparation: number
}

// Dormand & Prince (1980), DOI 10.1016/0771-050X(80)90013-3.
// 仅采用公开数学系数，独立实现；不复制求解器代码、不引入数值运行时。
const A = [
  [],
  [1 / 5],
  [3 / 40, 9 / 40],
  [44 / 45, -56 / 15, 32 / 9],
  [19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729],
  [9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656],
  [35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84],
]
const B = A[6]
const E = [
  35 / 384 - 5179 / 57600,
  0,
  500 / 1113 - 7571 / 16695,
  125 / 192 - 393 / 640,
  -2187 / 6784 + 92097 / 339200,
  11 / 84 - 187 / 2100,
  -1 / 40,
]

export function invariants(state: ArrayLike<number>, masses: readonly number[]) {
  let kinetic = 0
  let potential = 0
  let separation = Infinity
  const momentum = [0, 0, 0]
  const angularMomentum = [0, 0, 0]
  for (let i = 0; i < masses.length; i++) {
    const o = i * 6
    const m = masses[i]
    kinetic += (m / 2) * (state[o + 3] ** 2 + state[o + 4] ** 2 + state[o + 5] ** 2)
    for (let k = 0; k < 3; k++) {
      momentum[k] += m * state[o + k + 3]
      const j = (k + 1) % 3
      const l = (k + 2) % 3
      angularMomentum[k] += m * (state[o + j] * state[o + l + 3] - state[o + l] * state[o + j + 3])
    }
    for (let j = i + 1; j < masses.length; j++) {
      const r = Math.hypot(...[0, 1, 2].map(k => state[j * 6 + k] - state[o + k]))
      separation = Math.min(separation, r)
      potential -= (m * masses[j]) / r
    }
  }
  return {
    energy: kinetic + potential,
    energyScale: kinetic + Math.abs(potential),
    momentum,
    angularMomentum,
    separation,
  }
}

export class ThreeBodySolver {
  readonly masses: readonly number[]
  readonly options: Readonly<SolverOptions>
  readonly initial: ReturnType<typeof invariants>
  time = 0
  paused = false
  fault: PhysicsFault | null = null
  private readonly initialState: Float64Array
  private state: Float64Array
  private readonly stages = Array.from({ length: 7 }, () => new Float64Array(18))
  private readonly trial = new Float64Array(18)
  private readonly candidate = new Float64Array(18)
  private stepSize: number

  constructor(
    bodies: readonly BodyInitial[] = DEFAULT_BODIES,
    options: Partial<SolverOptions> = {}
  ) {
    if (
      bodies.length !== 3 ||
      bodies.some(
        body =>
          !Number.isFinite(body.mass) ||
          body.mass <= 0 ||
          body.position.length !== 3 ||
          body.velocity.length !== 3 ||
          [...body.position, ...body.velocity].some(x => !Number.isFinite(x))
      )
    ) {
      throw new Error('Expected three finite positive point masses')
    }
    this.options = Object.freeze({ ...PHYSICS_MODEL, ...options })
    const o = this.options
    if (
      [o.relativeTolerance, o.absoluteTolerance, o.minStep, o.maxStep, o.minSeparation].some(
        x => !Number.isFinite(x) || x <= 0
      ) ||
      o.maxStep < o.minStep
    )
      throw new Error('Invalid solver options')
    this.masses = Object.freeze(bodies.map(body => body.mass))
    const totalMass = this.masses.reduce((a, b) => a + b, 0)
    if (!Number.isFinite(totalMass)) throw new Error('Invalid total mass')
    this.initialState = new Float64Array(18)
    for (let k = 0; k < 6; k++) {
      const values = bodies.map(body => (k < 3 ? body.position[k] : body.velocity[k - 3]))
      const center = values.reduce((sum, value, i) => sum + value * (this.masses[i] / totalMass), 0)
      for (let i = 0; i < 3; i++) this.initialState[i * 6 + k] = values[i] - center
    }
    this.state = this.initialState.slice()
    this.initial = invariants(this.state, this.masses)
    if (
      ![...this.state, this.initial.energy, this.initial.energyScale].every(Number.isFinite) ||
      this.initial.separation <= o.minSeparation
    )
      throw new Error('Invalid initial separation or scale')
    this.stepSize = Math.min(0.001, o.maxStep)
  }

  /** 复制已接受状态；显示层得不到可写的积分缓冲。 */
  snapshot(): Float64Array {
    return this.state.slice()
  }

  diagnostics() {
    const current = invariants(this.state, this.masses)
    return {
      ...current,
      // 近零总能量采用初始 K+|U| 归一化，不能用 |E0|。
      energyError: Math.abs(current.energy - this.initial.energy) / this.initial.energyScale,
      momentumError: Math.hypot(...current.momentum.map((x, i) => x - this.initial.momentum[i])),
      angularMomentumError: Math.hypot(
        ...current.angularMomentum.map((x, i) => x - this.initial.angularMomentum[i])
      ),
    }
  }

  pause(): void {
    this.paused = true
  }
  resume(): void {
    if (!this.fault) this.paused = false
  }
  reset(): void {
    this.state.set(this.initialState)
    this.time = 0
    this.paused = false
    this.fault = null
    this.stepSize = Math.min(0.001, this.options.maxStep)
  }

  /** 有界工作量；未完成的目标时间由调用方丢弃，不存墙钟欠账。 */
  advance(duration: number, maxAttempts = 64, outOfTime: () => boolean = () => false) {
    if (
      !Number.isFinite(duration) ||
      duration < 0 ||
      !Number.isInteger(maxAttempts) ||
      maxAttempts < 0
    )
      throw new Error('Invalid advance budget')
    const target = this.time + duration
    if (!Number.isFinite(target)) throw new Error('Invalid target time')
    let attempts = 0
    let accepted = 0
    while (!this.paused && this.time < target && attempts < maxAttempts && !outOfTime()) {
      attempts++
      let encounterStep = Infinity
      for (let i = 0; i < 3; i++)
        for (let j = i + 1; j < 3; j++) {
          const r = Math.hypot(...[0, 1, 2].map(k => this.state[j * 6 + k] - this.state[i * 6 + k]))
          encounterStep = Math.min(
            encounterStep,
            0.03 * Math.sqrt(r ** 3 / (this.masses[i] + this.masses[j]))
          )
        }
      const remaining = target - this.time
      const h = Math.min(this.stepSize, this.options.maxStep, encounterStep, remaining)
      if (encounterStep < this.options.minStep) {
        this.stop('nearEncounter')
        break
      }
      if (this.time + h === this.time) {
        this.stop('precision')
        break
      }
      let trialFault: PhysicsFault | null = null
      for (let stage = 0; stage < 7; stage++) {
        this.trial.set(this.state)
        for (let j = 0; j < A[stage].length; j++)
          for (let k = 0; k < 18; k++) this.trial[k] += h * A[stage][j] * this.stages[j][k]
        trialFault = this.derivative(this.trial, this.stages[stage])
        if (trialFault) break
      }
      let error = 0
      if (!trialFault)
        for (let k = 0; k < 18; k++) {
          let value = this.state[k]
          let difference = 0
          for (let j = 0; j < 7; j++) {
            if (j < B.length) value += h * B[j] * this.stages[j][k]
            difference += h * E[j] * this.stages[j][k]
          }
          this.candidate[k] = value
          const scale =
            this.options.absoluteTolerance +
            this.options.relativeTolerance * Math.max(Math.abs(value), Math.abs(this.state[k]))
          error = Math.max(error, Math.abs(difference) / scale)
          if (!Number.isFinite(value) || !Number.isFinite(error)) trialFault = 'nonFinite'
        }
      if (trialFault || error > 1) {
        if (h <= this.options.minStep) {
          this.stop(trialFault ?? 'precision')
          break
        }
        this.stepSize = Math.max(
          this.options.minStep,
          h * (trialFault ? 0.25 : Math.max(0.1, 0.9 * error ** -0.2))
        )
        continue
      }
      this.state.set(this.candidate)
      this.time += h
      accepted++
      this.stepSize = Math.max(
        this.options.minStep,
        Math.min(this.options.maxStep, h * Math.min(4, error === 0 ? 4 : 0.9 * error ** -0.2))
      )
    }
    return { accepted, attempts, budgetLimited: !this.paused && this.time < target }
  }

  private stop(fault: PhysicsFault): void {
    this.fault = fault
    this.paused = true
  }

  private derivative(state: Float64Array, result: Float64Array): PhysicsFault | null {
    if (!state.every(Number.isFinite)) return 'nonFinite'
    result.fill(0)
    for (let i = 0; i < 3; i++) for (let k = 0; k < 3; k++) result[i * 6 + k] = state[i * 6 + k + 3]
    for (let i = 0; i < 3; i++)
      for (let j = i + 1; j < 3; j++) {
        const dx = state[j * 6] - state[i * 6]
        const dy = state[j * 6 + 1] - state[i * 6 + 1]
        const dz = state[j * 6 + 2] - state[i * 6 + 2]
        const r = Math.hypot(dx, dy, dz)
        if (r <= this.options.minSeparation) return 'nearEncounter'
        const inverseCube = 1 / (r * r * r)
        for (let k = 0; k < 3; k++) {
          const force = [dx, dy, dz][k] * inverseCube
          result[i * 6 + k + 3] += this.masses[j] * force
          result[j * 6 + k + 3] -= this.masses[i] * force
        }
      }
    return result.every(Number.isFinite) ? null : 'nonFinite'
  }
}
