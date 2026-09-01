/**
 * Runtime 子进程的环境变量覆盖
 *
 * 目前只有遥测一项：用户关闭匿名遥测时透传 `AUTO_MAS_TELEMETRY=disabled` 给
 * `auto-mas-runtime.exe`，让 Runtime 自己的上报也一并关闭；开启时不设该变量——不是显式
 * 清空，只是不去覆盖 Runtime 自己的默认值。`--offline` 是完全独立的网络开关（禁止任何联网
 * 尝试），不能拿来当遥测开关用。
 *
 * 遥测开关的权威来源是后端持久化的 `GlobalConfig.Function.IfEnableTelemetry`
 * （`<appRoot>/config/Config.json`），与 Electron 主进程自身 Sentry 开关（见 `../sentry.ts`
 * 的 `configureMainSentry`）读的是同一份配置、同一条「非 false 即视为开启」规则。
 */

import * as fs from 'fs'
import * as path from 'path'

import { getLogger } from '../logger'

const logger = getLogger('Runtime环境变量')

/** 透传给 Runtime 的遥测开关环境变量名。 */
export const RUNTIME_TELEMETRY_ENV = 'AUTO_MAS_TELEMETRY'

/**
 * 读取后端持久化配置里的遥测开关。
 *
 * 文件不存在、字段缺失或 JSON 损坏都按开启处理——只有明确写了 `false` 才是用户关闭过。
 */
function isTelemetryEnabled(appRoot: string): boolean {
  try {
    const configPath = path.join(appRoot, 'config', 'Config.json')
    if (!fs.existsSync(configPath)) return true

    const parsed = JSON.parse(fs.readFileSync(configPath, 'utf8')) as {
      Function?: { IfEnableTelemetry?: unknown }
    }
    return parsed.Function?.IfEnableTelemetry !== false
  } catch (error) {
    logger.warn(
      `读取遥测开关失败，按开启处理: ${error instanceof Error ? error.message : String(error)}`
    )
    return true
  }
}

/**
 * 构建传给 `RuntimeClient` 的环境变量覆盖。
 *
 * 关闭遥测时返回 `{ AUTO_MAS_TELEMETRY: 'disabled' }`；开启时返回空对象（不设该变量）。
 */
export function buildRuntimeEnv(appRoot: string): NodeJS.ProcessEnv {
  return isTelemetryEnabled(appRoot) ? {} : { [RUNTIME_TELEMETRY_ENV]: 'disabled' }
}
