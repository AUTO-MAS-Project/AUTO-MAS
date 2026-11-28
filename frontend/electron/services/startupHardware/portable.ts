import { cpus, totalmem, freemem } from 'node:os'
import { realpath, stat, lstat, statfs } from 'node:fs/promises'
import path from 'node:path'
import type { RawSample } from './summary'

export const volumeRoles = [
  'install',
  'workspace',
  'cache',
  'python',
  'venv',
  'electron_temp',
  'backend_temp',
  'runtime_build',
  'runtime_download',
] as const

/** 便携模式只使用系统可确认的显卡类别。驱动未知时保留 CPU、内存和卷读数。 */
export function portableGraphics(info: unknown): RawSample {
  if (!info || typeof info !== 'object' || !('gpuDevice' in info) || !Array.isArray(info.gpuDevice))
    return {}
  const row: RawSample = {}
  let count = 0,
    software = 0,
    ambiguous = false
  for (const device of info.gpuDevice) {
    if (!device || typeof device !== 'object') {
      ambiguous = true
      continue
    }
    const name = String(device.deviceString ?? device.vendorString ?? '')
    if (device.vendorId === 0x1414 || /swiftshader|llvmpipe|software rasterizer/i.test(name)) {
      software++
      continue
    }
    const vendors: Record<number, string> = {
      0x10de: 'NVIDIA',
      0x1002: 'AMD Radeon',
      0x8086: 'Intel',
      0x106b: 'Apple',
    }
    const vendor = vendors[device.vendorId]
    if (!vendor) {
      ambiguous = true
      continue
    }
    if (count < 4) row['gpu' + count + '_series'] = name || vendor
    count++
  }
  if (!ambiguous) row.gpu_count = count
  if (!count && !ambiguous) row.graphics_layout = software ? 'software-only' : 'no-adapter'
  return row
}
async function mounted(directory: string) {
  while (directory) {
    try {
      const resolved = await realpath(directory)
      return { resolved, dev: (await stat(resolved)).dev }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') return
      const parent = path.dirname(directory)
      if (parent === directory) return
      if ((await lstat(directory).catch(() => undefined))?.isSymbolicLink()) return
      directory = parent
    }
  }
}
export function startPortableProbe(
  directories: string[],
  graphics: () => Promise<unknown>,
  emit: (sample: RawSample) => void
) {
  let stopped = false
  let timer: NodeJS.Timeout | undefined
  let previous = cpus(),
    adapters: RawSample = {},
    disk: RawSample = {}
  void graphics()
    .then(info => {
      if (!stopped) adapters = portableGraphics(info)
    })
    .catch(() => {})
  const volumes = Promise.all(directories.map(dir => (dir ? mounted(dir) : undefined)))
  function tick() {
    const now = cpus(),
      ram = totalmem(),
      available = freemem()
    const row: RawSample = {
      ...adapters,
      ...disk,
      ram: ram / 2 ** 30,
      ram_free: available / 2 ** 30,
      ram_used: 100 * (1 - available / ram),
    }
    if (now.length) {
      row.cpu_series = now[0].model
      row.logical_cores = now.length
    }
    let all = 0,
      busy = 0,
      peak = 0
    if (now.length === previous.length)
      now.forEach((core, i) => {
        const time =
          Object.values(core.times).reduce((a, b) => a + b, 0) -
          Object.values(previous[i].times).reduce((a, b) => a + b, 0)
        const used = time - core.times.idle + previous[i].times.idle
        if (time > 0) {
          all += time
          busy += used
          peak = Math.max(peak, (100 * used) / time)
        }
      })
    previous = now
    if (all > 0) {
      row.cpu = (100 * busy) / all
      row.core = peak
    }
    if (!stopped) emit(row)
  }
  let diskTimer: NodeJS.Timeout | undefined
  async function space() {
    const mounts = await volumes
    const unique = new Map<number, Awaited<ReturnType<typeof statfs>>>()
    const sample: RawSample = {}
    for (const [i, mount] of mounts.entries()) {
      if (stopped) return
      if (!mount) continue
      let v = unique.get(mount.dev)
      if (!v) {
        v = await statfs(mount.resolved).catch(() => undefined)
        if (!v) continue
        unique.set(mount.dev, v)
      }
      const role = volumeRoles[i]
      const blocks = Number(v.blocks),
        size = Number(v.bsize)
      if (blocks > 0) {
        sample[role + '_capacity'] = (blocks * size) / 2 ** 30
        sample[role + '_free'] = (Number(v.bavail) * size) / 2 ** 30
        sample[role + '_used'] = 100 * (1 - Number(v.bfree) / blocks)
      }
      if (mount.dev === mounts[0]?.dev) sample[role + '_location'] = 'same-volume'
    }
    disk = sample
    if (!stopped) {
      diskTimer = setTimeout(() => {
        void space().catch(() => {})
      }, 1000)
      diskTimer.unref()
    }
  }
  void space().catch(() => {})
  tick()
  timer = setInterval(tick, 1000)
  timer.unref()
  return () => {
    stopped = true
    clearInterval(timer)
    clearTimeout(diskTimer)
  }
}
