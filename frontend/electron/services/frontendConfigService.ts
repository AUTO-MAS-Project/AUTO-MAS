import * as fs from 'fs'
import * as path from 'path'

export interface FrontendUpdateConfig {
  IfAutoUpdate: boolean
  Source?: string
  Channel?: string
  MirrorChyanCDK?: string
  [key: string]: any
}

export interface FrontendAppConfig {
  UI: {
    IfShowTray: boolean
    IfToTray: boolean
    location: string
    maximized: boolean
    size: string
    [key: string]: any
  }
  Start: {
    IfMinimizeDirectly: boolean
    IfSelfStart: boolean
    [key: string]: any
  }
  Update: FrontendUpdateConfig
  [key: string]: any
}

export interface BackendConfigLike {
  Update?: Record<string, any>
  [key: string]: any
}

export const defaultFrontendConfig: FrontendAppConfig = {
  UI: {
    IfShowTray: false,
    IfToTray: false,
    location: '100,100',
    maximized: false,
    size: '1600,1000',
  },
  Start: {
    IfMinimizeDirectly: false,
    IfSelfStart: false,
  },
  Update: {
    IfAutoUpdate: false,
  },
}

function readJsonFile<T>(filePath: string): T | null {
  if (!fs.existsSync(filePath)) {
    return null
  }

  return JSON.parse(fs.readFileSync(filePath, 'utf8')) as T
}

function mergeSection<T extends Record<string, any>>(
  base: T,
  incoming?: Record<string, any> | null
): T {
  return {
    ...base,
    ...(incoming || {}),
  }
}

export function mergeFrontendConfig(
  frontendConfig?: Partial<FrontendAppConfig> | null,
  backendConfig?: BackendConfigLike | null
): FrontendAppConfig {
  const merged: FrontendAppConfig = {
    ...defaultFrontendConfig,
    ...(frontendConfig || {}),
    UI: mergeSection(defaultFrontendConfig.UI, frontendConfig?.UI),
    Start: mergeSection(defaultFrontendConfig.Start, frontendConfig?.Start),
    Update: mergeSection(defaultFrontendConfig.Update, frontendConfig?.Update),
  }

  if (backendConfig?.Update) {
    merged.Update = mergeSection(merged.Update, backendConfig.Update)
  }

  return merged
}

export function getConfigPaths(appRoot: string) {
  const configDir = path.join(appRoot, 'config')
  return {
    configDir,
    frontendConfigPath: path.join(configDir, 'frontend_config.json'),
    backendConfigPath: path.join(configDir, 'Config.json'),
  }
}

export function saveFrontendConfig(appRoot: string, config: FrontendAppConfig) {
  const { configDir, frontendConfigPath } = getConfigPaths(appRoot)

  if (!fs.existsSync(configDir)) {
    fs.mkdirSync(configDir, { recursive: true })
  }

  fs.writeFileSync(frontendConfigPath, JSON.stringify(config, null, 2), 'utf8')
}

export function loadFrontendConfigFile(
  appRoot: string
): Partial<FrontendAppConfig> | null {
  const { frontendConfigPath } = getConfigPaths(appRoot)
  return readJsonFile<Partial<FrontendAppConfig>>(frontendConfigPath)
}

export function loadBackendConfigFile(appRoot: string): BackendConfigLike | null {
  const { backendConfigPath } = getConfigPaths(appRoot)
  return readJsonFile<BackendConfigLike>(backendConfigPath)
}

export function loadEffectiveFrontendConfig(appRoot: string): FrontendAppConfig {
  const frontendConfig = loadFrontendConfigFile(appRoot)
  const backendConfig = loadBackendConfigFile(appRoot)
  const mergedConfig = mergeFrontendConfig(frontendConfig, backendConfig)

  const frontendJson = JSON.stringify(frontendConfig || null)
  const mergedJson = JSON.stringify(mergedConfig)
  if (frontendJson !== mergedJson) {
    saveFrontendConfig(appRoot, mergedConfig)
  }

  return mergedConfig
}
