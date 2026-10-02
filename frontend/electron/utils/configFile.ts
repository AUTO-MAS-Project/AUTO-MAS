import * as fs from 'fs'
import * as path from 'path'

// 在主进程中同步读取、合并和写入，期间不让出事件循环给其他配置写入。
export function patchConfigFile(
  configPath: string,
  patch: Record<string, unknown>,
  defaults: Record<string, unknown> = {}
): Record<string, unknown> {
  const current = fs.existsSync(configPath) ? JSON.parse(fs.readFileSync(configPath, 'utf8')) : {}
  const config = { ...defaults, ...current, ...patch }
  fs.mkdirSync(path.dirname(configPath), { recursive: true })
  fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8')
  return config
}
