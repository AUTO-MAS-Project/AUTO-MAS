import type { ElectronAPI } from '@/types/electron'
import { getDefaultHttpEndpoint, getDefaultWebSocketEndpoint } from '@/utils/backendEndpoint'

type BrowserDevWindow = Window & { __AUTO_MAS_BROWSER_DEV_MODE__?: boolean }
type Logger = ReturnType<ElectronAPI['getLogger']>

const BACKEND_HTTP_ENDPOINT = getDefaultHttpEndpoint()
const BACKEND_WS_ENDPOINT = getDefaultWebSocketEndpoint()
// 不能叫 app-config：utils/config.ts 把它当旧版 localStorage 配置，读一次就迁移并删除
const CONFIG_KEY = 'auto-mas.browser-dev.config'
const INITIALIZED_VERSION_KEY = 'app-initialized-version'

const readJsonStorage = <T>(key: string): T | null => {
  const raw = localStorage.getItem(key)
  if (!raw) return null

  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

const getLogger = (moduleName: string): Logger => {
  const write =
    (level: 'debug' | 'info' | 'warn' | 'error') =>
    async (...args: unknown[]) => {
      console[level](`[${moduleName}]`, ...args)
    }

  return {
    debug: write('debug'),
    info: write('info'),
    warn: write('warn'),
    error: write('error'),
  }
}

const browserDevElectronAPI = {
  getLogger,
  getApiEndpoint: async (key: string) =>
    key === 'websocket' ? BACKEND_WS_ENDPOINT : BACKEND_HTTP_ENDPOINT,
  openUrl: async (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer')
    return { success: true }
  },
  windowFocus: async () => window.focus(),
  selectFolder: async () => null,
  selectFile: async () => [],
  saveConfig: async (config: Record<string, unknown>, defaults?: Record<string, unknown>) => {
    const current = readJsonStorage<Record<string, unknown>>(CONFIG_KEY)
    localStorage.setItem(CONFIG_KEY, JSON.stringify({ ...defaults, ...current, ...config }))
  },
  loadConfig: async () => readJsonStorage(CONFIG_KEY),
  resetConfig: async () => {
    localStorage.removeItem(CONFIG_KEY)
  },
  getInitializedVersion: async () => localStorage.getItem(INITIALIZED_VERSION_KEY),
  setInitializedVersion: async (version: string) => {
    localStorage.setItem(INITIALIZED_VERSION_KEY, version)
    return true
  },
  fileExists: async () => false,
  readFile: async () => '',
  getAppPath: async () => '',
  listAppearances: async () => [],
  getAppearance: async () => null,
  importAppearance: async () => ({
    success: false,
    code: 'UNSUPPORTED' as const,
    error: '浏览器预览不支持导入外观包，请在桌面应用中操作',
  }),
  removeAppearance: async () => ({ success: false, error: '浏览器预览不支持移除外观包' }),
  clearInvalidAppearance: async () => ({ success: false, error: '浏览器预览不支持清理外观包' }),
  onAppearanceChanged: () => () => undefined,
  onThemeConfigChanged: () => () => undefined,
  backendStatus: async () => ({ isRunning: true, runtimeSupervised: false }),
} as unknown as ElectronAPI

if (import.meta.env.DEV && !window.electronAPI) {
  ;(window as BrowserDevWindow).__AUTO_MAS_BROWSER_DEV_MODE__ = true
  window.electronAPI = browserDevElectronAPI
}
