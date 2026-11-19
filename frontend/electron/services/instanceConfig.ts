/**
 * 实例配置 - 区分开发环境与用户安装的正式版
 *
 * 两者默认共用同一个后端端口与同一个 Electron userData 目录，导致无法同时运行。
 * 本模块集中提供运行环境判定、后端端口与实例名，供主进程与后端服务复用。
 *
 * 不依赖本目录下其它服务，避免与环境或后端启动服务形成循环导入。
 */

import * as path from 'path'
import { app } from 'electron'
import type { ApplicationEnvironment, BackendOwnership } from '../../src/types/environment'

// ==================== 常量 ====================

// 正式版固定端口；开发环境错开一位，与 main.py 的 DEFAULT_HTTP_PORT / DEV_HTTP_PORT 保持一致
const DEFAULT_HTTP_PORT = 36163
const DEV_HTTP_PORT = 36164

// 全局快捷键是系统级独占资源，两版同时运行时必须错开，否则后注册的一方静默失效
const STOP_ALL_TASKS_SHORTCUT = 'Control+Shift+Alt+M'
const DEV_STOP_ALL_TASKS_SHORTCUT = 'Control+Shift+Alt+N'

// ==================== 工具函数 ====================

/** 显式选择开发后端；不读取 .env，不根据端口或目录是否存在自动切换。 */
export function getDeveloperBackendRepo(): string | undefined {
  const configured = process.env.AUTO_MAS_BACKEND_REPO?.trim()
  return configured ? path.resolve(configured) : undefined
}

// 使用开发后端的安装版也隔离端口、用户数据与遥测。
export function getApplicationEnvironment(): ApplicationEnvironment {
  return app?.isPackaged && !getDeveloperBackendRepo() ? 'production' : 'development'
}

export function isDevelopmentEnvironment(): boolean {
  return getApplicationEnvironment() === 'development'
}

export function getRendererEnvironmentArguments(): string[] {
  return [
    `--auto-mas-environment=${getApplicationEnvironment()}`,
    `--auto-mas-backend-ownership=${getBackendOwnership()}`,
  ]
}

/** 只连接入口必须显式选择，不根据端口占用接管已有进程。 */
export function getBackendOwnership(): BackendOwnership {
  return process.argv.includes('--connect-existing-backend') ? 'external' : 'owned'
}

export function getDevelopmentServerUrl(): string | undefined {
  return !app?.isPackaged ? process.env.VITE_DEV_SERVER_URL : undefined
}

// 解析端口号，非法值返回 undefined 交由调用方回退
function parsePort(value: string | undefined): number | undefined {
  if (!value || !/^\d+$/.test(value.trim())) {
    return undefined
  }

  const port = Number(value.trim())
  return port >= 1 && port <= 65535 ? port : undefined
}

// 解析后端 HTTP/WS 端口：环境变量优先，其次按运行环境分流
export function resolveHttpPort(): number {
  const configured = parsePort(process.env.AUTO_MAS_HTTP_PORT)
  if (configured !== undefined) {
    return configured
  }

  return isDevelopmentEnvironment() ? DEV_HTTP_PORT : DEFAULT_HTTP_PORT
}

// 停止全部任务的全局快捷键，开发环境错开以免与正式版互抢
export function resolveStopAllTasksShortcut(): string {
  return isDevelopmentEnvironment() ? DEV_STOP_ALL_TASKS_SHORTCUT : STOP_ALL_TASKS_SHORTCUT
}

// 后端默认端点，云端镜像配置未下发时使用
export function getDefaultApiEndpoints(): { local: string; websocket: string } {
  const port = resolveHttpPort()
  return {
    local: `http://127.0.0.1:${port}`,
    websocket: `ws://127.0.0.1:${port}`,
  }
}

/** 开发版使用独立的用户数据目录；正式版名称来自 package.json 的 productName。 */
export function applyInstanceIdentity(): void {
  if (!app || !isDevelopmentEnvironment()) {
    return
  }

  const instanceName = `${app.getName()}-dev`
  const developerHome = process.env.AUTO_MAS_DEVELOPER_HOME?.trim()
  app.setPath('userData', path.join(developerHome || app.getPath('appData'), instanceName))
  app.setName(instanceName)
}
