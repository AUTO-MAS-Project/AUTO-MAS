export interface MarketItem {
  package: string
  version: string
  summary: string
  project_url: string
  prefix_tag: string
}

export type InstalledMapValue =
  | boolean
  | string
  | {
      installed?: boolean
      version?: string
    }

export interface MarketSnapshot {
  schema_version: number
  prefix_tags: string[]
  fetched_at: string
  items: MarketItem[]
  installed_map: Record<string, InstalledMapValue>
  total: number
}

export interface InstalledPackageState {
  installed: boolean
  version: string
}

/** normalize 后的 distribution 名 -> 本机已安装版本 */
export type InstalledVersionMap = Record<string, string>

/** 插件网关 plugin_packages 字段的最小结构（plugins.get / plugin.snapshot.updated） */
export interface PluginPackageVersionSource {
  package?: string | null
  version?: string | null
}

export type InstallFilter = 'all' | 'installed' | 'available'

export const normalizePackageName = (name: string) =>
  String(name || '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_')

const normalizeInstalledValue = (value: InstalledMapValue): InstalledPackageState => {
  if (typeof value === 'string') {
    return { installed: true, version: value.trim() }
  }
  if (typeof value === 'object' && value !== null) {
    return {
      installed: value.installed !== false,
      version: String(value.version || '').trim(),
    }
  }
  return { installed: Boolean(value), version: '' }
}

export const buildInstalledState = (
  installedMap: MarketSnapshot['installed_map'] = {}
): Record<string, InstalledPackageState> =>
  Object.fromEntries(
    Object.entries(installedMap).map(([packageName, value]) => [
      normalizePackageName(packageName),
      normalizeInstalledValue(value),
    ])
  )

/**
 * 从插件网关的 plugin_packages（plugin 名 -> {package, version}）提取
 * 「distribution 名 -> 本机真实版本」映射。
 * 市场快照的 installed_map 目前只有布尔值，本机版本需从这里补齐。
 */
export const buildInstalledVersionMap = (
  pluginPackages: Record<string, PluginPackageVersionSource> = {}
): InstalledVersionMap => {
  const result: InstalledVersionMap = {}
  for (const info of Object.values(pluginPackages)) {
    const packageName = normalizePackageName(String(info?.package || ''))
    const version = String(info?.version || '').trim()
    if (!packageName || !version) continue
    result[packageName] = version
  }
  return result
}

/**
 * 用插件网关上报的本机版本补齐 installed_map 缺失的 version 字段。
 * 只补「已安装且版本为空」的条目；快照自带版本时以快照为准。
 */
export const mergeInstalledVersions = (
  installedState: Record<string, InstalledPackageState>,
  versionMap: InstalledVersionMap
): Record<string, InstalledPackageState> =>
  Object.fromEntries(
    Object.entries(installedState).map(([packageName, state]) => [
      packageName,
      state.installed && !state.version && versionMap[packageName]
        ? { ...state, version: versionMap[packageName] }
        : state,
    ])
  )

const normalizeVersionText = (value: string) =>
  String(value || '')
    .trim()
    .replace(/^[vV]/, '')

/** 本机版本与市场最新版本是否一致（两侧都非空才可能判定为一致） */
export const isSameVersion = (localVersion: string, latestVersion: string): boolean => {
  const local = normalizeVersionText(localVersion)
  const latest = normalizeVersionText(latestVersion)
  return local !== '' && latest !== '' && local === latest
}

export const filterMarketItems = (
  items: MarketItem[],
  installedState: Record<string, InstalledPackageState>,
  keyword: string,
  installFilter: InstallFilter,
  prefixFilter: string
): MarketItem[] => {
  const query = keyword.trim().toLowerCase()
  return items.filter(item => {
    const installed = Boolean(installedState[normalizePackageName(item.package)]?.installed)
    if (installFilter === 'installed' && !installed) return false
    if (installFilter === 'available' && installed) return false
    if (prefixFilter && item.prefix_tag !== prefixFilter) return false
    if (!query) return true

    return [item.package, item.summary, item.version, item.prefix_tag].some(value =>
      String(value || '')
        .toLowerCase()
        .includes(query)
    )
  })
}
