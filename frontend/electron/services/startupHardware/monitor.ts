import { startPortableProbe } from './portable'
import { totalmem, freemem } from 'node:os'
import { AsyncLocalStorage } from 'node:async_hooks'
import { spawn, type ChildProcess } from 'node:child_process'
import { createInterface } from 'node:readline'
import { band, SampleSummary, type Fields, type RawSample, type TimedSample } from './summary'
import { localReadings, type StartupHardwareLog } from './localLog'
import type { RuntimeEvent } from '../runtime/protocol'

export interface ProbeConfig {
  reportHostFailure?: (stage: string, code: string) => void
  log: StartupHardwareLog
  executable?: string
  graphics: () => Promise<unknown>
  directories: string[]
  scope: 'desktop' | 'managed'
  acceleration: 'yes' | 'no' | 'unknown'
}
const maxDuration = 10 * 60_000
const recentWindow = 15_000

export class StartupAttempt {
  readonly started = performance.now()
  readonly wallStart = Date.now()
  readonly reportHostFailure: ProbeConfig['reportHostFailure']
  private readonly overall = new SampleSummary(this.started)
  private readonly stages = new Set<SampleSummary>()
  private recent: TimedSample[] = []
  private child?: ChildProcess
  private stopPortable?: () => void
  private until?: NodeJS.Timeout
  private firstFrame?: NodeJS.Timeout
  private last = 0
  private frozen?: number
  private readonly cleanup = new Set<() => void>()
  private readonly log: StartupHardwareLog
  private failureLogged = false
  onStop(close: () => void) {
    this.cleanup.add(close)
    return () => this.cleanup.delete(close)
  }
  private readonly details: Fields
  private previousSource = ''
  private downloads = 0
  private command = ''
  private operation = ''
  private lastItem = ''
  private lastBytes = 0
  private switches = 0
  private retries = 0
  private activityStarted = 0
  private activity = ''
  private readonly durations = new Map<string, number>()
  constructor(
    readonly generation: number | null,
    config: ProbeConfig
  ) {
    this.reportHostFailure = config.reportHostFailure
    this.log = config.log
    this.log.write('开始', {
      attempt: this.wallStart,
      units: 'CPU/内存/活动时间为百分比，容量为 GiB，速度为 MiB/s，延迟为 ms，排队数为个数',
    })
    this.details = {
      arch: band('arch', process.arch) ?? 'unknown',
      scope: config.scope,
      acceleration: config.acceleration,
    }
    const total = totalmem(),
      available = freemem()
    if (total > 0)
      this.log.write('起始内存', {
        attempt: this.wallStart,
        ram_gib: Math.round((total / 2 ** 30) * 100) / 100,
        available_gib: Math.round((available / 2 ** 30) * 100) / 100,
      })
    this.until = setTimeout(() => this.stop(), maxDuration)
    this.until.unref()
    const fallback = () => {
      if (!this.sampling || this.stopPortable) return
      this.stopPortable = startPortableProbe(config.directories, config.graphics, data =>
        this.accept(data)
      )
    }
    if (!config.executable) {
      fallback()
      return
    }
    const child = spawn(config.executable, [String(process.pid), ...config.directories], {
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'ignore'],
    })
    this.child = child
    this.firstFrame = setTimeout(() => {
      if (!this.last && this.sampling) {
        child.kill()
        fallback()
      }
    }, 5000)
    this.firstFrame.unref()
    child.on('error', fallback)
    child.stdin.on('error', () => {})
    const lines = createInterface({ input: child.stdout })
    lines.on('line', line => {
      if (!this.sampling || line.length > 32768) return
      try {
        const data: unknown = JSON.parse(line)
        if (data && typeof data === 'object' && !Array.isArray(data)) this.accept(data as RawSample)
      } catch {
        /* 忽略损坏的一帧。 */
      }
    })
    child.once('close', () => {
      lines.close()
      fallback()
    })
  }
  private accept(data: RawSample) {
    if (!this.sampling) return
    clearTimeout(this.firstFrame)
    const at = performance.now(),
      sample = { at, previous: this.last || at, data }
    if (!this.last)
      this.log.write('硬件配置和首次读数', {
        attempt: this.wallStart,
        readings: localReadings(data),
      })
    this.last = at
    this.recent = this.recent.filter(item => item.at >= at - recentWindow)
    this.recent.push(sample)
    this.overall.add(sample)
    for (const stage of this.stages) stage.add(sample)
  }
  logResult(
    stage: string,
    outcome: string,
    code = 'none',
    started = this.started,
    stageSummary?: Fields
  ) {
    const at = performance.now()
    const latest = this.recent.at(-1)
    this.log.write('阶段结果', {
      attempt: this.wallStart,
      stage,
      outcome,
      code,
      elapsed_ms: Math.round(at - started),
      sample_age_ms: latest ? Math.round(at - latest.at) : null,
      readings: latest && at - latest.at <= recentWindow ? localReadings(latest.data) : {},
      summary: stageSummary ?? this.snapshot(),
    })
    if (outcome === 'failure' && !this.failureLogged) {
      this.failureLogged = true
      this.log.write('失败前15秒', {
        attempt: this.wallStart,
        stage,
        samples: this.recent
          .filter(s => s.at >= at - recentWindow)
          .map(s => ({
            offset_ms: Math.round(s.at - this.started),
            readings: localReadings(s.data),
          })),
      })
    }
  }
  revokeUpload() {
    for (const close of this.cleanup) close()
    this.cleanup.clear()
  }
  stop() {
    if (this.frozen !== undefined) return
    this.frozen = performance.now()
    this.revokeUpload()
    clearTimeout(this.until)
    clearTimeout(this.firstFrame)
    this.stopPortable?.()
    this.child?.stdin?.end()
    this.child?.kill()
    this.child = undefined
  }
  get sampling() {
    return this.frozen === undefined
  }
  beginStage(stage: string) {
    const start = performance.now()
    const summary = new SampleSummary(start)
    this.stages.add(summary)
    return (outcome: string, code?: string) => {
      this.stages.delete(summary)
      const fields = summary.fields()
      this.logResult(stage, outcome, code, start, fields)
      return {
        ...fields,
        ...this.details,
        coverage: summary.hasInterval ? 'sampled' : 'insufficient',
      }
    }
  }
  desktopDownload(bytes: number | undefined, speed: number | undefined, sourceIndex: number) {
    if (bytes !== undefined)
      this.details.downloaded = band('downloaded', bytes / 1048576) ?? 'unknown'
    if (speed !== undefined)
      this.details.download_speed = band('download_speed', speed / 1048576) ?? 'unknown'
    this.details.source_switches =
      band('source_switches', Math.max(0, sourceIndex - 1)) ?? 'unknown'
  }
  retry() {
    this.failureLogged = false
    this.details.retries = band('retries', ++this.retries)!
  }
  progress(event: RuntimeEvent) {
    if (!this.sampling) return
    if (event.type === 'hello') {
      this.command = event.command
      this.operation = event.operationId
      this.previousSource = ''
      return
    }
    if (event.operationId !== this.operation) return
    if (event.type === 'result') {
      this.finishActivity(performance.now())
      this.activityStarted = 0
      this.activity = ''
      if (this.command === 'dependencies rebuild' && event.success) this.details.env_rebuilt = 'yes'
      const archive = event.details.startupArchive
      if (archive && typeof archive === 'object') {
        const stats = archive as Record<string, unknown>
        if (typeof stats.cached === 'boolean')
          this.details.cache_reused = stats.cached ? 'yes' : 'no'
        for (const [key, phase] of [
          ['downloadMs', 'download'],
          ['verifyMs', 'verify'],
          ['unpackMs', 'unpack'],
        ]) {
          const ms = stats[key]
          if (typeof ms === 'number' && Number.isFinite(ms) && ms >= 0)
            this.durations.set(phase, ms)
        }
      }
      if (event.stage === 'bootstrap' && event.success) {
        if (event.details.unchanged === true) this.details.env_rebuilt = 'no'
      }
      return
    }
    if (event.type === 'progress') {
      if (event.stage === 'network.probe') return
      const stage = event.stage
      const active =
        stage === 'uv.download'
          ? 'other'
          : stage.includes('download')
            ? 'download'
            : stage.includes('verify')
              ? 'verify'
              : stage.includes('extract')
                ? 'unpack'
                : stage.split('.')[0]
      const now = performance.now()
      if (active !== this.activity || event.status !== 'running') {
        this.finishActivity(now)
        this.activity = event.status === 'running' ? active : ''
        this.activityStarted = event.status === 'running' ? now : 0
      }
      this.details.activity = band('activity', active) ?? 'unknown'
      const byteProgress =
        event.current !== undefined &&
        (stage === 'uv.download' ||
          ((stage === 'python.install' || stage === 'dependencies.sync') &&
            event.bytesPerSecond !== undefined))
      if (byteProgress && event.current !== undefined) {
        const item =
          event.operationId +
          '|' +
          stage +
          (stage === 'uv.download' ? '|' + (event.source ?? '') : '')
        const from = item === this.lastItem && event.current >= this.lastBytes ? this.lastBytes : 0
        this.downloads += event.current - from
        this.lastItem = item
        this.lastBytes = event.current
        this.details.downloaded = band('downloaded', this.downloads / 1048576)!
      }
      if (event.bytesPerSecond !== undefined) {
        this.details.download_speed =
          band('download_speed', event.bytesPerSecond / 1048576) ?? 'unknown'
        if (event.source) {
          if (this.previousSource && this.previousSource !== event.source) this.switches++
          this.previousSource = event.source
          this.details.source_switches = band('source_switches', this.switches)!
        }
      }
      if (stage === 'dependencies.rebuild' && event.status === 'succeeded')
        this.details.env_rebuilt = 'yes'
    }
  }
  private finishActivity(now: number) {
    if (this.activityStarted)
      this.durations.set(
        this.activity,
        (this.durations.get(this.activity) ?? 0) + now - this.activityStarted
      )
  }
  snapshot(recent = false): Fields {
    const now = performance.now()
    const endOfSampling = this.frozen ?? now
    let summary = this.overall
    if (recent) {
      summary = new SampleSummary(now - recentWindow)
      for (const item of this.recent) if (item.at >= now - recentWindow) summary.add(item)
    }
    const times: Fields = {}
    for (const activity of [
      'download',
      'verify',
      'unpack',
      'dependencies',
      'workspace',
      'python',
      'backend',
    ]) {
      const elapsed =
        (this.durations.get(activity) ?? 0) +
        (activity === this.activity ? endOfSampling - this.activityStarted : 0)
      if (elapsed > 0)
        times[activity + '_time'] = band(activity + '_time', elapsed / 1000) ?? 'unknown'
    }
    return {
      ...summary.fields(),
      ...this.details,
      ...times,
      startup_duration: band('startup_duration', (now - this.started) / 1000) ?? 'unknown',
      coverage: summary.hasInterval ? 'sampled' : 'insufficient',
      sample_age: this.last
        ? band('sample_age', (performance.now() - this.last) / 1000)!
        : 'unknown',
    }
  }
}

let current: StartupAttempt | undefined
let config: (() => ProbeConfig) | undefined
let getGeneration: (() => number | null) | undefined
let sequence = 0
export function setupStartupHardware(settings: () => ProbeConfig, generation: () => number | null) {
  config = settings
  getGeneration = generation
  start()
}
function start() {
  clearStartupHardware()
  const generation = getGeneration?.() ?? null
  if (!config) return
  try {
    current = new StartupAttempt(generation, config())
    sequence++
  } catch {
    /* 探针不可用时沿用原启动流程。 */
  }
}
export function clearStartupHardware() {
  current?.stop()
  current = undefined
}
export function localStartupAttempt() {
  return current
}
export function revokeHardwareUpload() {
  current?.revokeUpload()
}
export function startupAttempt() {
  return current && current.generation !== null && getGeneration?.() === current.generation
    ? current
    : undefined
}
const running = new AsyncLocalStorage<WeakRef<StartupAttempt> | undefined>()
export function inStartupOperation<T>(run: () => T) {
  const active = current
  return running.run(active ? new WeakRef(active) : undefined, run)
}
export function operationAttempt() {
  const active = running.getStore()?.deref()
  return active === current ? active : undefined
}

export function claimStartupAttempt() {
  if (!current) start()
  return current ? sequence : null
}
export function finishStartupAttempt(id: unknown, outcome: string, code: string) {
  if (id !== sequence || !current) return undefined
  current.logResult('initialization', outcome, code)
  const summary = startupAttempt()?.snapshot() ?? {}
  clearStartupHardware()
  return summary
}
