import * as fs from 'fs'
import * as path from 'path'
import { parse } from 'yaml'

import { getLogger } from './logger'

const logger = getLogger('后端配置')

/** 将升级前的 MAS 文档转成新结构，供首次启动时读取。 */
function legacyDocument(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(legacyDocument)
  if (typeof value !== 'object' || value === null) return value
  const record = value as Record<string, unknown>
  if (Array.isArray(record.instances)) {
    const order = record.instances as Array<{ uid: string; type: string }>
    return {
      order,
      data: Object.fromEntries(order.map(item => [item.uid, legacyDocument(record[item.uid])])),
    }
  }
  const result = Object.fromEntries(
    Object.entries(record)
      .filter(([key]) => key !== 'SubConfigsInfo')
      .map(([key, item]) => [key, legacyDocument(item)])
  )
  if (typeof record.SubConfigsInfo === 'object' && record.SubConfigsInfo !== null) {
    for (const [key, item] of Object.entries(record.SubConfigsInfo)) {
      result[key] = legacyDocument(item)
    }
  }
  return result
}

/** YAML 优先；只有首次升级前允许读取旧 JSON。解析错误由调用方处理。 */
function readDocument(dataRoot: string, yamlName: string, legacyName: string): unknown {
  const configDir = path.join(dataRoot, 'config')
  const yamlPath = path.join(configDir, yamlName)
  if (fs.existsSync(yamlPath)) return parse(fs.readFileSync(yamlPath, 'utf8')) as unknown
  const migrationPath = path.join(configDir, '.config-migration-v2.json')
  if (fs.existsSync(migrationPath)) {
    const migration: unknown = JSON.parse(fs.readFileSync(migrationPath, 'utf8'))
    if (
      typeof migration === 'object' &&
      migration !== null &&
      'complete' in migration &&
      migration.complete === true
    )
      return undefined
  }
  const legacyPath = path.join(configDir, legacyName)
  return fs.existsSync(legacyPath)
    ? legacyDocument(JSON.parse(fs.readFileSync(legacyPath, 'utf8')) as unknown)
    : undefined
}

export function readBackendDocument(
  dataRoot: string,
  yamlName: string,
  legacyName: string
): unknown {
  try {
    return readDocument(dataRoot, yamlName, legacyName)
  } catch (error) {
    logger.warn(`读取后端配置失败: ${error instanceof Error ? error.message : String(error)}`)
    return undefined
  }
}
