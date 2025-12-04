import type { ThemeMode, ThemeColor } from '@/composables/useTheme'
import { getLogger } from '@/utils/logger'

const logger = getLogger('配置管理')

export interface FrontendConfig {
  // 基础配置
  isFirstLaunch: boolean
  init: boolean
  lastUpdateCheck?: string

  // 主题设置
  themeMode: ThemeMode
  themeColor: ThemeColor

  // 镜像源设置
  selectedGitMirror: string
  selectedPythonMirror: string
  selectedPipMirror: string

  // 安装状态
  pythonInstalled?: boolean
  gitInstalled?: boolean
  backendExists?: boolean
  dependenciesInstalled?: boolean
}

const DEFAULT_CONFIG: FrontendConfig = {
  isFirstLaunch: true,
  init: false,
  themeMode: 'system',
  themeColor: 'blue',
  selectedGitMirror: 'github',
  selectedPythonMirror: 'tsinghua',
  selectedPipMirror: 'tsinghua',
  pythonInstalled: false,
  gitInstalled: false,
  backendExists: false,
  dependenciesInstalled: false,
}

// 读取配置（内部使用，不触发保存）
async function getConfigInternal(): Promise<FrontendConfig> {
  try {
    // 优先从文件读取配置
    const fileConfig = await window.electronAPI.loadConfig()
    if (fileConfig) {
      logger.info('从文件加载配置:', fileConfig)
      return { ...DEFAULT_CONFIG, ...fileConfig }
    }

    // 如果文件不存在，尝试从localStorage迁移
    const localConfig = localStorage.getItem('app-config')
    const themeConfig = localStorage.getItem('theme-settings')

    let config = { ...DEFAULT_CONFIG }

    if (localConfig) {
      const parsed = JSON.parse(localConfig)
      config = { ...config, ...parsed }
      logger.info('从localStorage迁移配置:', parsed)
    }

    if (themeConfig) {
      const parsed = JSON.parse(themeConfig)
      config.themeMode = parsed.themeMode || 'system'
      config.themeColor = parsed.themeColor || 'blue'
      logger.info('从localStorage迁移主题配置:', parsed)
    }

    return config
  } catch (error) {
    logger.error('读取配置失败:', error)
    return { ...DEFAULT_CONFIG }
  }
}

// 读取配置（公共接口）
export async function getConfig(): Promise<FrontendConfig> {
  const config = await getConfigInternal()

  // 如果是从localStorage迁移的配置，保存到文件并清理localStorage
  const hasLocalStorage =
    localStorage.getItem('app-config') || localStorage.getItem('theme-settings')
  if (hasLocalStorage) {
    try {
      await window.electronAPI.saveConfig(config)
      localStorage.removeItem('app-config')
      localStorage.removeItem('theme-settings')
      localStorage.removeItem('app-initialized')
      logger.info('配置已从localStorage迁移到文件')
    } catch (error) {
      logger.error('迁移配置失败:', error)
    }
  }

  return config
}

// 保存配置
export async function saveConfig(config: Partial<FrontendConfig>): Promise<void> {
  try {
    logger.info('开始保存配置:', config)
    const currentConfig = await getConfigInternal() // 使用内部函数避免递归
    const newConfig = { ...currentConfig, ...config }
    logger.info('合并后的配置:', newConfig)
    await window.electronAPI.saveConfig(newConfig)
    logger.info('配置保存成功')
  } catch (error) {
    logger.error('保存配置失败:', error)
    throw error
  }
}

// 重置配置
export async function resetConfig(): Promise<void> {
  try {
    await window.electronAPI.resetConfig()
    localStorage.removeItem('app-config')
    localStorage.removeItem('theme-settings')
    localStorage.removeItem('app-initialized')
  } catch (error) {
    logger.error('重置配置失败:', error)
  }
}

// 检查是否已初始化
export async function isAppInitialized(): Promise<boolean> {
  const config = await getConfig()
  logger.info('isAppInitialized 检查配置:', config)
  logger.info('init 字段值:', config.init)
  logger.info('init === true:', config.init === true)
  return config.init === true
}

// 检查是否第一次启动
export async function isFirstLaunch(): Promise<boolean> {
  const config = await getConfig()
  return config.isFirstLaunch === true
}

// 设置初始化完成
export async function setInitialized(value: boolean = true): Promise<void> {
  await saveConfig({ init: value, isFirstLaunch: false })
}

// 保存主题设置
export async function saveThemeConfig(themeMode: ThemeMode, themeColor: ThemeColor): Promise<void> {
  await saveConfig({ themeMode, themeColor })
}

// 保存镜像源设置
export async function saveMirrorConfig(
  gitMirror: string,
  pythonMirror?: string,
  pipMirror?: string
): Promise<void> {
  const config: Partial<FrontendConfig> = { selectedGitMirror: gitMirror }
  if (pythonMirror) config.selectedPythonMirror = pythonMirror
  if (pipMirror) config.selectedPipMirror = pipMirror
  await saveConfig(config)
}
