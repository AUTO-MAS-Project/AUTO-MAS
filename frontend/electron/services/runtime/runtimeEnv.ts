/**
 * Runtime 子进程的环境变量覆盖
 *
 * 两项，都只在需要时才设，不去覆盖 Runtime 自己的默认值：
 * - 遥测：用户关闭匿名遥测时透传 `AUTO_MAS_TELEMETRY=disabled` 给 `auto-mas-runtime.exe`，
 *   让 Runtime 自己的上报也一并关闭；开启时不设该变量。`--offline` 是完全独立的网络开关
 *   （禁止任何联网尝试），不能拿来当遥测开关用；
 * - 开发标记：`development` 模式透传 `AUTO_MAS_ENV=development`。Runtime 把自己的环境原样交给
 *   `uv run` 再交给后端，后端 `main.py` 的 `is_development_environment()` 读到它就按开发环境
 *   关闭 Sentry 上报。受监督时端口、`/api/core/close`、工作目录忽略开发标记是契约，但遥测不该
 *   跟着变成生产；旧链路（Electron 自己 spawn python）早就这么注入，这里只是补齐新链路。
 *
 * 遥测开关的权威来源是后端持久化的 `GlobalConfig.Function.IfEnableTelemetry`
 * （`<dataRoot>/config/Config.json`），与 Electron 主进程自身 Sentry 开关（见 `../sentry.ts`
 * 的 `configureMainSentry`）读的是同一份配置、同一条「非 false 即视为开启」规则。`dataRoot`
 * 是用户数据根（`getAppRoot()`），不是 `--app-root`：`development` 模式下两者不是同一个目录。
 */

import * as fs from 'fs'
import * as path from 'path'

import { getLogger } from '../logger'
import type { RuntimeLaunchMode } from './launchConfig'

const logger = getLogger('Runtime环境变量')

/** 透传给 Runtime 的遥测开关环境变量名。 */
export const RUNTIME_TELEMETRY_ENV = 'AUTO_MAS_TELEMETRY'

/** 透传给 Runtime（再到后端）的运行环境标记变量名，与旧链路 `createBackendEnvironment` 同名。 */
export const RUNTIME_APP_ENV = 'AUTO_MAS_ENV'

/**
 * 读取后端持久化配置里的遥测开关。
 *
 * 文件不存在、字段缺失或 JSON 损坏都按开启处理——只有明确写了 `false` 才是用户关闭过。
 */
function isTelemetryEnabled(dataRoot: string): boolean {
  try {
    const configPath = path.join(dataRoot, 'config', 'Config.json')
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
 * @param dataRoot 用户数据根，`config/Config.json` 所在处。
 * @param launchMode 本次启动链路；`development` 时追加 `AUTO_MAS_ENV=development`，其它模式
 *   （含未指定）不碰该变量。
 *
 * 关闭遥测时含 `AUTO_MAS_TELEMETRY: 'disabled'`；开启时不含该键。什么都不需要设时返回空对象。
 */
export function buildRuntimeEnv(
  dataRoot: string,
  launchMode?: RuntimeLaunchMode
): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {}
  if (!isTelemetryEnabled(dataRoot)) {
    env[RUNTIME_TELEMETRY_ENV] = 'disabled'
  }
  if (launchMode === 'development') {
    env[RUNTIME_APP_ENV] = 'development'
  }
  return env
}
