/**
 * 实例配置 - 区分开发环境与用户安装的正式版
 *
 * 两者默认共用同一个后端端口与同一个 Electron userData 目录，导致无法同时运行。
 * 本模块集中提供运行环境判定、后端端口与实例名，供主进程、镜像源服务与后端服务复用。
 *
 * 不依赖本目录下其它服务，避免与 environmentService / mirrorService 形成循环导入。
 */

import * as path from 'path'
import { app } from 'electron'

// ==================== 常量 ====================

// 正式版固定端口；开发环境错开一位，与 main.py 的 DEFAULT_HTTP_PORT / DEV_HTTP_PORT 保持一致
const DEFAULT_HTTP_PORT = 36163
const DEV_HTTP_PORT = 36164

// 全局快捷键是系统级独占资源，两版同时运行时必须错开，否则后注册的一方静默失效
const STOP_ALL_TASKS_SHORTCUT = 'Control+Shift+Alt+M'
const DEV_STOP_ALL_TASKS_SHORTCUT = 'Control+Shift+Alt+N'

// ==================== 工具函数 ====================

// 判断是否处于开发环境
export function isDevelopmentEnvironment(): boolean {
  if (process.env.NODE_ENV === 'development' || Boolean(process.env.VITE_DEV_SERVER_URL)) {
    return true
  }

  return Boolean(app) && !app.isPackaged
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

/**
 * 开发环境改用独立的 userData 目录
 *
 * userData 同时决定 Chromium profile 与 requestSingleInstanceLock 的锁键。打包版
 * asar 内的 package.json 仍为 name=frontend，与源码开发版取到同一个目录，后启动的
 * 一方会在窗口创建之前静默退出。必须在 app ready 之前调用。
 */
export function applyInstanceIdentity(): void {
  if (!app || !isDevelopmentEnvironment()) {
    return
  }

  const instanceName = `${app.getName()}-dev`
  app.setPath('userData', path.join(app.getPath('appData'), instanceName))
  app.setName(instanceName)
}
