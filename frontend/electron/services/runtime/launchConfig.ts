/**
 * Runtime 后端监督链路的灰度开关与可执行文件定位
 *
 * 灰度期同时存在两条后端启动链路：
 * - `off`（默认）：Electron 自己 spawn `python.exe`，就绪靠健康检查，停止靠 scoped taskkill；
 * - `development` / `managed`：交给 `auto-mas-runtime.exe backend supervise` 监督。
 *
 * 一次生命周期只走一条链路：模式非 `off` 却找不到可执行文件时，按 `RUNTIME_NOT_FOUND`
 * 失败并展示，绝不静默回退旧链路——否则用户会在不知情的情况下拿到另一套端口与关闭语义。
 *
 * 本任务只提供环境变量开关，配置项与设置界面属于后续任务。
 */

import * as fs from 'fs'
import * as path from 'path'

import { getLogger } from '../logger'

const logger = getLogger('Runtime启动配置')

/** 捆绑在安装包 resources 目录下的 Runtime 文件名。 */
export const RUNTIME_EXECUTABLE_NAME = 'auto-mas-runtime.exe'

/** 灰度开关的环境变量名。 */
export const RUNTIME_MODE_ENV = 'AUTO_MAS_RUNTIME_MODE'

/** 手动指定 Runtime 可执行文件路径的环境变量名。 */
export const RUNTIME_EXE_ENV = 'AUTO_MAS_RUNTIME_EXE'

/**
 * 后端启动链路。
 *
 * `development` 监督开发者自己的源码检出（要求 `<repo>/main.py`、`<repo>/pyproject.toml`
 * 与已存在的 `<repo>/.venv`，Runtime 不创建它们）；`managed` 监督 Runtime 自己维护的受管工作区。
 */
export type RuntimeLaunchMode = 'off' | 'development' | 'managed'

const RUNTIME_LAUNCH_MODES: readonly RuntimeLaunchMode[] = ['off', 'development', 'managed']

/** 灰度开关关闭时的定位信息：不去找可执行文件。 */
export interface RuntimeDisabledLaunchConfig {
  mode: 'off'
  runtimePath: null
  appRoot: string
}

/** 走 Runtime 监督链路时的定位信息。 */
export interface RuntimeSupervisedLaunchConfig {
  mode: Exclude<RuntimeLaunchMode, 'off'>
  /** 找不到可执行文件时为 null，由调用方按 `RUNTIME_NOT_FOUND` 处理。 */
  runtimePath: string | null
  /** 传给 `--app-root`。 */
  appRoot: string
  /** `development` 模式传给 `--repo`；`managed` 模式不传。 */
  repo?: string
}

/** 一次启动所需的全部定位信息，按 `mode` 判别。 */
export type RuntimeLaunchConfig = RuntimeDisabledLaunchConfig | RuntimeSupervisedLaunchConfig

function isRuntimeLaunchMode(value: string): value is RuntimeLaunchMode {
  return (RUNTIME_LAUNCH_MODES as readonly string[]).includes(value)
}

/**
 * 解析灰度开关。
 *
 * 来源优先级：环境变量 `AUTO_MAS_RUNTIME_MODE` → 默认 `off`。非法取值记 warning 后按
 * `off` 处理，避免拼错一个单词就把用户带上一条没验证过的链路。
 */
export function resolveRuntimeLaunchMode(): RuntimeLaunchMode {
  const raw = process.env[RUNTIME_MODE_ENV]
  if (raw === undefined || raw.trim() === '') {
    return 'off'
  }

  const normalized = raw.trim().toLowerCase()
  if (isRuntimeLaunchMode(normalized)) {
    return normalized
  }

  logger.warn(
    `${RUNTIME_MODE_ENV} 取值非法：${raw}，按 off 处理（可选值：off/development/managed）`
  )
  return 'off'
}

function isExistingFile(candidate: string): boolean {
  try {
    return fs.statSync(candidate).isFile()
  } catch {
    return false
  }
}

/**
 * 定位 `auto-mas-runtime.exe`。
 *
 * 优先用环境变量显式指定的路径，其次查安装包捆绑位置 `process.resourcesPath`。
 * 尚未捆绑时返回 null，由调用方转成 `RUNTIME_NOT_FOUND`。
 */
export function resolveRuntimeExecutable(): string | null {
  const configured = process.env[RUNTIME_EXE_ENV]?.trim()
  if (configured) {
    if (isExistingFile(configured)) {
      return path.resolve(configured)
    }
    logger.warn(`${RUNTIME_EXE_ENV} 指向的文件不存在：${configured}`)
  }

  // 非 Electron 环境（单元测试）下 resourcesPath 不存在。
  const resourcesPath = typeof process.resourcesPath === 'string' ? process.resourcesPath : ''
  if (resourcesPath) {
    const bundled = path.join(resourcesPath, RUNTIME_EXECUTABLE_NAME)
    if (isExistingFile(bundled)) {
      return bundled
    }
  }

  return null
}

/**
 * 汇总本次启动的模式与路径。
 *
 * `development` 的 `--repo` 就是当前 appRoot：开发者跑的就是这份源码检出。
 */
export function resolveRuntimeLaunchConfig(appRoot: string): RuntimeLaunchConfig {
  const mode = resolveRuntimeLaunchMode()
  if (mode === 'off') {
    return { mode, runtimePath: null, appRoot }
  }

  return {
    mode,
    runtimePath: resolveRuntimeExecutable(),
    appRoot,
    repo: mode === 'development' ? appRoot : undefined,
  }
}
