import * as fs from 'fs'
import * as path from 'path'
import { randomUUID } from 'node:crypto'

function readConfigFile(configPath: string): Record<string, unknown> {
  if (!fs.existsSync(configPath)) return {}
  const config: unknown = JSON.parse(fs.readFileSync(configPath, 'utf8'))
  if (config === null || typeof config !== 'object' || Array.isArray(config)) {
    throw new Error('前端配置文件必须包含 JSON 对象')
  }
  return config as Record<string, unknown>
}

function writeConfigFile(configPath: string, config: Record<string, unknown>): void {
  fs.mkdirSync(path.dirname(configPath), { recursive: true })
  const tempPath = `${configPath}.${randomUUID()}.tmp`
  try {
    fs.writeFileSync(tempPath, JSON.stringify(config, null, 2), 'utf8')
    fs.renameSync(tempPath, configPath)
  } catch (error) {
    fs.rmSync(tempPath, { force: true })
    throw error
  }
}

// 在主进程中同步读取、合并和写入，期间不让出事件循环给其他配置写入。
export function patchConfigFile(
  configPath: string,
  patch: Record<string, unknown>,
  defaults: Record<string, unknown> = {}
): Record<string, unknown> {
  const current = readConfigFile(configPath)
  const config = { ...defaults, ...current, ...patch }
  writeConfigFile(configPath, config)
  return config
}

/** 清理旧外观前同步确认磁盘仍选中它，不覆盖其他窗口刚保存的选择。 */
export function clearAppearanceConfigIfCurrent(
  configPath: string,
  expectedId: string,
  isInvalid: () => boolean
): { cleared: boolean; config: Record<string, unknown> } {
  const current = readConfigFile(configPath)
  if (current.appearanceId !== expectedId || !isInvalid()) {
    return { cleared: false, config: current }
  }
  const config = { ...current, appearanceId: null }
  writeConfigFile(configPath, config)
  return { cleared: true, config }
}
