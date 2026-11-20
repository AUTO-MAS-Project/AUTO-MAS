import { promises as fs } from 'node:fs'
import path from 'node:path'
import catalog from './fields.json'
import type { RawSample } from './summary'

/** debug 根目录已由现有日志和问题包收集器脱敏打包。只在阶段和终态写入。 */
export class StartupHardwareLog {
  private pending = Promise.resolve()
  private readonly file: string
  constructor(private readonly directory: string) {
    this.file = path.join(directory, 'startup-hardware.log')
  }
  write(event: string, details: Record<string, unknown>) {
    const line = JSON.stringify({ time: new Date().toISOString(), event, ...details }) + '\n'
    this.pending = this.pending
      .then(async () => {
        await fs.mkdir(this.directory, { recursive: true })
        const stat = await fs.stat(this.file).catch((error: NodeJS.ErrnoException) => {
          if (error.code !== 'ENOENT') throw error
          return undefined
        })
        if (stat && stat.size + Buffer.byteLength(line) > 2 * 1024 * 1024)
          await fs.rename(this.file, this.file + '.1')
        await fs.appendFile(this.file, line, 'utf8')
      })
      .catch(() => {
        /* 磁盘已满时保留业务的原始错误。 */
      })
  }
  drain() {
    return this.pending
  }
}

/** 本地可读实测值保留两位小数。设备标识、目录、命令行和自由文本都不进入日志。 */
export function localReadings(row: RawSample): Record<string, number | string> {
  const result: Record<string, number | string> = {}
  for (const [key, v] of Object.entries(row)) {
    if (![key, key + '_peak', key + '_avg'].some(name => Object.hasOwn(catalog.fields, name)))
      continue
    if (typeof v === 'number' && Number.isFinite(v) && v >= 0)
      result[key] = Math.round(v * 100) / 100
    else if (
      typeof v === 'string' &&
      (key === 'graphics_layout' ||
        key.endsWith('_series') ||
        key.endsWith('_kind') ||
        /_(fs|bus|media|location)$/.test(key))
    )
      result[key] = v.replace(/[\r\n\t]/g, ' ').slice(0, 96)
  }
  return result
}
