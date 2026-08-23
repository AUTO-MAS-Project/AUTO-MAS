import type { ElectronAPI } from '@/types/electron'

type BrowserDevWindow = Window & { __AUTO_MAS_BROWSER_DEV_MODE__?: boolean }
type Logger = ReturnType<ElectronAPI['getLogger']>

const BACKEND_HTTP_ENDPOINT = 'http://127.0.0.1:36163'
const BACKEND_WS_ENDPOINT = 'ws://127.0.0.1:36163'
const CONFIG_KEY = 'app-config'
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
  getApiEndpoints: async () => ({ local: BACKEND_HTTP_ENDPOINT, websocket: BACKEND_WS_ENDPOINT }),
  openUrl: async (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer')
    return { success: true }
  },
  windowFocus: async () => window.focus(),
  selectFolder: async () => null,
  selectFile: async () => [],
  saveConfig: async (config: unknown) => {
    localStorage.setItem(CONFIG_KEY, JSON.stringify(config))
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
  backendStatus: async () => ({ isRunning: true, wsConnected: false }),
} as unknown as ElectronAPI

if (import.meta.env.DEV && !window.electronAPI) {
  ;(window as BrowserDevWindow).__AUTO_MAS_BROWSER_DEV_MODE__ = true
  window.electronAPI = browserDevElectronAPI
}
