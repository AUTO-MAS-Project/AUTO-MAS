/**
 * RuntimeClient 构造工厂
 *
 * `runtimeInitializationService.ts`（W9b）与 `backendService.ts`（W9c）各有一处构造
 * `RuntimeClient` 的地方，此前分别裸 `new RuntimeClient(...)`，遥测开关这类需要每次构造都
 * 生效的策略只能各写一份。收敛到这里统一注入 `buildRuntimeEnv()`，两个调用点都改成调这个
 * 工厂，不改它们原有的控制流程。应用环境始终由 Electron 决定；其它显式 `env` 保留覆盖能力。
 */

import { RuntimeClient, RuntimeClientOptions } from './client'
import { getApplicationEnvironment } from '../instanceConfig'
import { buildRuntimeEnv, RUNTIME_APP_ENV } from './runtimeEnv'

/** 工厂在 `RuntimeClientOptions` 之外多收用户数据根，只用来决定注入哪些环境变量，不传给客户端。 */
export interface CreateRuntimeClientOptions extends RuntimeClientOptions {
  /**
   * 用户数据根（`config/Config.json` 所在处），缺省与 `appRoot` 相同。`development` 模式下
   * `appRoot` 是仓外的 Runtime 根目录而配置在源码根，两者必须分开传，否则遥测开关读不到。
   */
  dataRoot?: string
}

export function createRuntimeClient(options: CreateRuntimeClientOptions): RuntimeClient {
  const { dataRoot, ...clientOptions } = options
  return new RuntimeClient({
    ...clientOptions,
    env: {
      ...buildRuntimeEnv(dataRoot ?? options.appRoot),
      ...options.env,
      [RUNTIME_APP_ENV]: getApplicationEnvironment(),
    },
  })
}
