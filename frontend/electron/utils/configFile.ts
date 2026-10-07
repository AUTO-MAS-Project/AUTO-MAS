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

/** 清理旧外观前同步确认磁盘仍选中它，不覆盖其他窗口刚保存的选择。 */
export function clearAppearanceConfigIfCurrent(
  configPath: string,
  expectedId: string,
  isInvalid: () => boolean
): { cleared: boolean; config: Record<string, unknown> } {
  const current: Record<string, unknown> = fs.existsSync(configPath)
    ? JSON.parse(fs.readFileSync(configPath, 'utf8'))
    : {}
  if (current.appearanceId !== expectedId || !isInvalid()) {
    return { cleared: false, config: current }
  }
  const config = { ...current, appearanceId: null }
  fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8')
  return { cleared: true, config }
}
