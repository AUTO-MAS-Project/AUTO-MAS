/**
 * RuntimeClient 构造工厂
 *
 * `runtimeInitializationService.ts`（W9b）与 `backendService.ts`（W9c）各有一处构造
 * `RuntimeClient` 的地方，此前分别裸 `new RuntimeClient(...)`，遥测开关这类需要每次构造都
 * 生效的策略只能各写一份。收敛到这里统一注入 `buildRuntimeEnv()`，两个调用点都改成调这个
 * 工厂，不改它们原有的控制流程。调用方显式传入的 `env` 优先于这里注入的默认值。
 */

import { RuntimeClient, RuntimeClientOptions } from './client'
import { buildRuntimeEnv } from './runtimeEnv'

export function createRuntimeClient(options: RuntimeClientOptions): RuntimeClient {
  return new RuntimeClient({
    ...options,
    env: { ...buildRuntimeEnv(options.appRoot), ...options.env },
  })
}
