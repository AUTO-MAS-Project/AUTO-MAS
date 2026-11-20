import catalog from './fields.json'

export type Fields = Record<string, string>
export type RawSample = Record<string, unknown>
type Scale = keyof typeof catalog.values
const fields: Readonly<Record<string, Scale | undefined>> = catalog.fields as Record<string, Scale>
const limits: Partial<Record<Scale, readonly number[]>> = {
  startupDuration: [1, 5, 30, 120],
  percent: [20, 50, 75, 90],
  gib: [1, 4, 8, 16, 32, 64, 256, 1024],
  count: [1, 2, 5, 9, 17, 33],
  latency: [1, 5, 20, 100],
  speed: [1, 10, 50, 200],
  iops: [10, 100, 1000],
  duration: [1, 5, 15, 60],
  size: [1, 16, 128, 1024],
}

/** 上传前再次过滤，错误对象或 renderer 自行拼接的字段不能成为设备属性。 */
export function allowedFields(fieldsIn: Fields, compact = false): Fields {
  const selected: Fields = {}
  for (const [key, value] of Object.entries(fieldsIn)) {
    if (!Object.hasOwn(fields, key)) continue
    const scale = fields[key]
    if (!scale || (value !== 'unknown' && !catalog.values[scale].includes(value))) continue
    if (compact && !populationFields.has(key)) continue
    selected[key] = value
  }
  return selected
}

const populationFields = new Set([
  'coverage',
  'startup_duration',
  'scope',
  'cpu_series',
  'logical_cores',
  'ram',
  'gpu0_series',
  'gpu_count',
  'graphics_layout',
  'gpu0_kind',
  'gpu0_shared',
  'install_used',
  'install_bus',
  'install_media',
  'install_fs',
  'cache_location',
  'cpu_avg',
  'cpu_peak',
  'ram_free',
  'commit_peak',
  'gpu0_busy_peak',
  'install_free',
  'cache_free',
  'install_busy_avg',
  'cache_busy_avg',
  'install_read_latency',
  'cache_write_latency',
  'activity',
  'env_rebuilt',
  'cache_reused',
  'retries',
  'downloaded',
  'download_speed',
  'source_switches',
  'download_time',
  'verify_time',
  'unpack_time',
  'dependencies_time',
  'backend_time',
])

export function band(key: string, value: unknown): string | undefined {
  if (!Object.hasOwn(fields, key)) return
  const scale = fields[key]
  if (!scale) return
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0 && limits[scale]) {
    const index = limits[scale]!.findIndex(limit => value < limit)
    return catalog.values[scale][index < 0 ? limits[scale]!.length : index]
  }
  if (typeof value !== 'string') return
  if (scale === 'cpu') {
    const s = value.toLowerCase().replace(/\(r\)|\(tm\)/g, '')
    const intel = s.match(/intel.*core\s+i([3579])\b/i)
    const amd = s.match(/amd.*ryzen\s+([3579])\b/i)
    if (s.includes('apple')) return 'apple'
    if (s.includes('qualcomm') || s.includes('snapdragon')) return 'qualcomm'
    if (intel) return 'intel-core-i' + intel[1]
    if (amd) return 'amd-ryzen-' + amd[1]
    if (s.includes('intel'))
      return s.includes('ultra')
        ? 'intel-core-ultra'
        : s.includes('xeon')
          ? 'intel-xeon'
          : 'intel-other'
    if (s.includes('amd')) return s.includes('epyc') ? 'amd-epyc' : 'amd-other'
    return 'other'
  }
  if (scale === 'gpu') {
    const s = value.toLowerCase(),
      rtx = s.match(/geforce rtx (20|30|40|50)\d\d/)
    if (rtx) return 'geforce-rtx-' + rtx[1]
    if (s.includes('apple')) return 'apple'
    if (s.includes('nvidia')) return s.includes('gtx') ? 'geforce-gtx' : 'nvidia-other'
    if (s.includes('radeon')) return s.includes('rx') ? 'radeon-rx' : 'radeon-other'
    if (s.includes('intel')) return s.includes('arc') ? 'intel-arc' : 'intel-other'
    return 'other'
  }
  return catalog.values[scale].includes(value) ? value : 'unknown'
}

export interface TimedSample {
  at: number
  previous: number
  data: RawSample
}

/** 每组计数器各自保留有效区间。缺失读数不占平均值分母。 */
export class SampleSummary {
  private readonly values: Fields = {}
  private readonly extremes = new Map<string, number>()
  private readonly usage = new Map<
    string,
    { weighted: number; seconds: number; high: number; peak: number; last: number }
  >()
  constructor(private readonly since: number) {}
  add(sample: TimedSample) {
    const interval = (sample.at - sample.previous) / 1000
    for (const [key, value] of Object.entries(sample.data)) {
      if (value == null) continue
      if (typeof value === 'number' && (!Number.isFinite(value) || value < 0)) continue
      if (Object.hasOwn(fields, key + '_avg') && typeof value === 'number') {
        if (sample.previous < this.since || interval <= 0 || interval > 3) continue
        const stat = this.usage.get(key) ?? { weighted: 0, seconds: 0, high: 0, peak: 0, last: 0 }
        stat.weighted += value * interval
        stat.seconds += interval
        if (value >= 90) stat.high += interval
        stat.peak = Math.max(stat.peak, value)
        stat.last = value
        this.usage.set(key, stat)
      } else {
        const target = Object.hasOwn(fields, key + '_peak') ? key + '_peak' : key
        if (!Object.hasOwn(fields, target)) continue
        let observed = value
        if (
          typeof value === 'number' &&
          /(?:_free|_used|_peak|_latency|_speed|_queue|_iops|_dedicated|_shared)$/.test(target)
        ) {
          const old = this.extremes.get(target) ?? value
          observed = target.endsWith('_free') ? Math.min(old, value) : Math.max(old, value)
          this.extremes.set(target, observed as number)
        }
        const cooked = band(target, observed)
        if (cooked !== undefined) this.values[target] = cooked
      }
    }
  }

  get hasInterval() {
    return this.usage.size > 0
  }
  fields(): Fields {
    const summary = { ...this.values }
    for (const [key, stat] of this.usage) {
      for (const [suffix, n] of Object.entries({
        avg: stat.weighted / stat.seconds,
        peak: stat.peak,
        last: stat.last,
        high: stat.high,
      })) {
        const name = key + '_' + suffix
        summary[name] = band(name, n) ?? 'unknown'
      }
    }
    return summary
  }
}
