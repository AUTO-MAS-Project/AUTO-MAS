/**
 * 后端端点 - 渲染进程侧的唯一兜底来源
 *
 * 端点正常由 Electron 的 getApiEndpoint 下发；这里只负责在 IPC 不可用或调用失败时
 * 给出与当前运行环境匹配的兜底地址，避免开发版把请求打到正式版占用的端口上。
 */

// 与 main.py、electron/services/instanceConfig.ts 保持一致
const DEFAULT_HTTP_PORT = 36163

// 构建时由 vite.config.ts 注入，取值为当前运行环境对应的后端端口
const resolvePort = (): number => {
  const injected = import.meta.env.VITE_AUTO_MAS_HTTP_PORT
  if (typeof injected !== 'string' || !/^\d+$/.test(injected)) {
    return DEFAULT_HTTP_PORT
  }

  const port = Number(injected)
  return port >= 1 && port <= 65535 ? port : DEFAULT_HTTP_PORT
}

export const getDefaultHttpEndpoint = (): string => `http://127.0.0.1:${resolvePort()}`

export const getDefaultWebSocketEndpoint = (): string => `ws://127.0.0.1:${resolvePort()}`

// Sentry 链路追踪只对本机后端生效，随端口一起变化
export const getBackendTracePropagationTarget = (): RegExp =>
  new RegExp(`^http://(?:localhost|127\\.0\\.0\\.1):${resolvePort()}/`)
