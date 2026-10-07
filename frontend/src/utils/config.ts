import type { AppLocale } from '@/i18n'
import type { ThemeMode, ThemeColor } from '@/composables/useTheme'
import type { CursorEffect } from '@/types/cursorEffect'
import type { HomeLayoutConfig } from '@/types/home'

const logger = window.electronAPI.getLogger('配置管理')

export interface FrontendConfig {
  // 主题设置
  themeMode: ThemeMode
  themeColor: ThemeColor
  /** 当前自定义外观包 ID；为空时使用内置外观模式。 */
  appearanceId?: string | null
  cursorEffect?: CursorEffect
  lowPerformanceMode?: boolean

  // 神秘入口上次解锁的北京时间日期，仅作轻量访问门槛
  mysteryUnlockedDate?: string

  // 界面语言；未设置时跟随系统
  language?: AppLocale

  // 镜像源设置
  selectedGitMirror: string
  selectedPythonMirror: string
  selectedPipMirror: string

  // 首页布局
  homeLayout?: HomeLayoutConfig

  // 首页快速启动最近选择
  homeQuickStartSelectedTaskIds?: string[]

  // 后端全局配置缓存（用于应用启动前读取）
  Function?: {
    IfEnableTelemetry?: boolean
  }
}

const DEFAULT_CONFIG: FrontendConfig = {
  themeMode: 'system',
  themeColor: 'blue',
  cursorEffect: 'none',
  lowPerformanceMode: false,
  selectedGitMirror: 'github',
  selectedPythonMirror: 'tsinghua',
  selectedPipMirror: 'tsinghua',
  Function: {
    IfEnableTelemetry: true,
  },
}

const LEGACY_THEME_COLORS = new Set([
  'blue',
  'purple',
  'cyan',
  'green',
  'magenta',
  'pink',
  'red',
  'orange',
  'yellow',
  'volcano',
  'geekblue',
  'lime',
  'gold',
])

// useTheme 旧版实际写的是这两个独立键；仅在迁移时读取，成功落盘后删除。
function getLegacyThemePatch(): Partial<FrontendConfig> {
  const mode = localStorage.getItem('theme-mode')
  const color = localStorage.getItem('theme-color')
  const patch: Partial<FrontendConfig> = {}
  if (mode === 'system' || mode === 'light' || mode === 'dark') patch.themeMode = mode
  if (color && LEGACY_THEME_COLORS.has(color)) patch.themeColor = color as ThemeColor
  return patch
}

// 保持渲染进程请求顺序；主进程保存时再合并最新文件，避免覆盖窗口等配置。
let configQueue: Promise<void> = Promise.resolve()

function enqueueConfigOperation<T>(operation: () => Promise<T>): Promise<T> {
  const pending = configQueue.then(operation)
  configQueue = pending.then(
    () => undefined,
    () => undefined
  )
  return pending
}

// 读取配置（内部使用，不触发保存）
async function getConfigInternal(): Promise<FrontendConfig> {
  let fileConfig: Awaited<ReturnType<typeof window.electronAPI.loadConfig>>
  try {
    // 优先从文件读取配置；旧 localStorage 仍需参与迁移，不能因为文件已有语言字段就丢掉旧主题。
    fileConfig = await window.electronAPI.loadConfig()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`读取配置失败: ${errorMsg}`)
    return { ...DEFAULT_CONFIG }
  }

  // localStorage 读取故障要继续向上抛出，让启动层保留原有的迁移失败信号；
  // Electron IPC 故障则按上面的兼容路径回落默认配置。
  const localConfig = localStorage.getItem('app-config')
  const themeConfig = localStorage.getItem('theme-settings')
  const legacyThemePatch = getLegacyThemePatch()

  try {
    let config = { ...DEFAULT_CONFIG }

    if (localConfig) {
      const parsed = JSON.parse(localConfig)
      config = { ...config, ...parsed, ...(fileConfig ?? {}) }
      logger.info(`从localStorage迁移配置: ${JSON.stringify(parsed)}`)
    } else if (fileConfig) {
      config = { ...config, ...fileConfig }
      logger.info(`从文件加载配置: 键=${Object.keys(fileConfig).join(',')}`)
    }

    if (themeConfig) {
      const parsed = JSON.parse(themeConfig)
      if (!fileConfig || fileConfig.themeMode === undefined) {
        config.themeMode = parsed.themeMode || 'system'
      }
      if (!fileConfig || fileConfig.themeColor === undefined) {
        config.themeColor = parsed.themeColor || 'blue'
      }
      logger.info(`从localStorage迁移主题配置: ${JSON.stringify(parsed)}`)
    }

    if (!localConfig && !themeConfig && fileConfig) {
      logger.info(`从文件加载配置: 键=${Object.keys(fileConfig).join(',')}`)
    }

    return { ...config, ...legacyThemePatch }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`解析配置失败: ${errorMsg}`)
    return { ...DEFAULT_CONFIG }
  }
}

// 读取配置（公共接口）
export async function getConfig(): Promise<FrontendConfig> {
  return enqueueConfigOperation(async () => {
    const config = await getConfigInternal()

    // 如果是从localStorage迁移的配置，保存到文件并清理localStorage
    const hasLocalStorage =
      localStorage.getItem('app-config') ||
      localStorage.getItem('theme-settings') ||
      localStorage.getItem('theme-mode') ||
      localStorage.getItem('theme-color')
    if (hasLocalStorage) {
      try {
        // 迁移只补齐缺失字段，不能用读取时的快照覆盖主进程的新值。
        await window.electronAPI.saveConfig(getLegacyThemePatch(), config)
        localStorage.removeItem('app-config')
        localStorage.removeItem('theme-settings')
        localStorage.removeItem('theme-mode')
        localStorage.removeItem('theme-color')
        localStorage.removeItem('app-initialized')
        logger.info('配置已从localStorage迁移到文件')
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`迁移配置失败: ${errorMsg}`)
      }
    }

    return config
  })
}

// 保存配置
export async function saveConfig(config: Partial<FrontendConfig>): Promise<void> {
  return enqueueConfigOperation(async () => {
    try {
      logger.info(`开始保存配置: 键=${Object.keys(config).join(',')}`)
      const defaults = await getConfigInternal() // 保留默认值和旧配置迁移
      await window.electronAPI.saveConfig(config, defaults)
      // 迁移曾失败时旧主题键还在；用户已显式保存新值，删掉对应旧键，免得下次迁移把它覆盖回去。
      if (config.themeMode !== undefined) localStorage.removeItem('theme-mode')
      if (config.themeColor !== undefined) localStorage.removeItem('theme-color')
      logger.info('配置保存成功')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存配置失败: ${errorMsg}`)
      throw error
    }
  })
}

// 重置配置
export async function resetConfig(): Promise<void> {
  return enqueueConfigOperation(async () => {
    try {
      await window.electronAPI.resetConfig()
      localStorage.removeItem('app-config')
      localStorage.removeItem('theme-settings')
      localStorage.removeItem('theme-mode')
      localStorage.removeItem('theme-color')
      localStorage.removeItem('app-initialized')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`重置配置失败: ${errorMsg}`)
    }
  })
}
