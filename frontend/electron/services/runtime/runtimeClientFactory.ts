/**
 * RuntimeClient 构造工厂
 *
 * `runtimeInitializationService.ts`（W9b）与 `backendService.ts`（W9c）各有一处构造
 * `RuntimeClient` 的地方，此前分别裸 `new RuntimeClient(...)`，遥测开关这类需要每次构造都
 * 生效的策略只能各写一份。收敛到这里统一注入 `buildRuntimeEnv()`，两个调用点都改成调这个
 * 工厂，不改它们原有的控制流程。调用方显式传入的 `env` 优先于这里注入的默认值。
 */

import { RuntimeClient, RuntimeClientOptions } from './client'
import type { RuntimeLaunchMode } from './launchConfig'
import { buildRuntimeEnv } from './runtimeEnv'

/** 工厂在 `RuntimeClientOptions` 之外多收两项，只用来决定注入哪些环境变量，不传给客户端。 */
export interface CreateRuntimeClientOptions extends RuntimeClientOptions {
  /**
   * 用户数据根（`config/Config.json` 所在处），缺省与 `appRoot` 相同。`development` 模式下
   * `appRoot` 是仓外的 Runtime 根目录而配置在源码根，两者必须分开传，否则遥测开关读不到。
   */
  dataRoot?: string
  /** 本次启动链路；`development` 时透传 `AUTO_MAS_ENV=development`。 */
  launchMode?: RuntimeLaunchMode
}

export function createRuntimeClient(options: CreateRuntimeClientOptions): RuntimeClient {
  const { dataRoot, launchMode, ...clientOptions } = options
  return new RuntimeClient({
    ...clientOptions,
    env: { ...buildRuntimeEnv(dataRoot ?? options.appRoot, launchMode), ...options.env },
  })
}
