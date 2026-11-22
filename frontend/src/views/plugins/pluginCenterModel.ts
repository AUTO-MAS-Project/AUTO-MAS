import type {
  PluginReleaseNote,
  PluginCatalogDocument,
  PluginCatalogGetOut,
  PluginConfigUi,
  PluginRegistryDocument,
  PluginRegistryGetOut,
} from '@/api'
import { pluginActionHint, pluginToggleChecked } from './configActions'

/**
 * 插件中心的视图模型与缺声明回落。
 *
 * 插件作者可能什么都不声明（没有显示名、描述、作者、许可证、链接、标签，也没有前端入口），
 * 各页签一律经这里整理后再展示，不各写各的回落。本模块只做纯计算，不读 i18n 实例、不发请求。
 */

export type PluginCategory = 'core' | 'specialized' | 'extension' | 'local'
const PLUGIN_CATEGORY_ORDER: readonly PluginCategory[] = [
  'core',
  'specialized',
  'extension',
  'local',
]
export type InstalledFilter = 'all' | 'official' | 'update' | 'fault'
export const INSTALLED_FILTERS: readonly InstalledFilter[] = ['all', 'official', 'update', 'fault']
export type MarketFilter = 'all' | 'specialized' | 'extension'
export const MARKET_FILTERS: readonly MarketFilter[] = ['all', 'specialized', 'extension']
export type DisableScope = 'scripts' | 'games' | 'plans'
export type LifecycleAction = 'enable' | 'disable' | 'reload' | 'uninstall'

/** 启停、重载、卸载的按钮文案键。写成字面量而不是拼接，词条审计才查得出失效的 core.plugins.* 键。 */
export const LIFECYCLE_LABEL_KEYS: Record<LifecycleAction, string> = {
  enable: 'core.plugins.enable',
  disable: 'core.plugins.disable',
  reload: 'core.plugins.reload',
  uninstall: 'core.plugins.uninstall',
}

/** 官方发行包名；只对非本地来源生效，核心插件另按 is_core 判官方。 */
const OFFICIAL_PACKAGE_NAMES: ReadonlySet<string> = new Set([
  'auto-mas-maa-adapter',
  'auto-mas-whimbox-adapter',
  'auto-mas-maafw-adapter',
  'auto-mas-m9a-adapter',
  'auto-mas-mss-adapter',
  'auto-mas-maafw-agent-env',
  'auto-mas-maafw-project-update',
  'auto-mas-maafw-runner',
])

/** 专项前端入口声明的所属插件，用来对上托管类型、计划表类型与图标。 */
export interface PluginAdapterBinding {
  pluginId: string
  scriptType: string
  logo: string
  planConfigType?: string
}

/** 插件自带词条 `plugins.<pluginId>.<field>`；没有词条时返回 undefined。 */
export interface PluginTextSource {
  text(pluginId: string, field: 'display_name' | 'description'): string | undefined
  tags(pluginId: string): string[] | undefined
}

export interface PluginModelContext {
  bindings: readonly PluginAdapterBinding[]
  /** 核心插件使用的应用图标地址。 */
  appIcon: string
  texts: PluginTextSource
}

export const PLUGIN_ICON_TONES = ['primary', 'success', 'warning', 'neutral'] as const
export type PluginIconTone = (typeof PLUGIN_ICON_TONES)[number]
export type PluginIcon =
  | { kind: 'image'; src: string }
  | { kind: 'initial'; text: string; tone: PluginIconTone }
  | { kind: 'generic'; tone: PluginIconTone }

export type PluginStatusTone = 'success' | 'processing' | 'warning' | 'error' | 'default'
/** labelKey 为 null 时显示 raw（后端给了不认识的状态值）。 */
export interface PluginStatus {
  labelKey: string | null
  raw: string
  tone: PluginStatusTone
}

export type PluginLinkKind = 'docs' | 'homepage' | 'repository'
export interface PluginLink {
  kind: PluginLinkKind
  href: string
}
export type PluginPublisher = 'official' | 'local' | 'thirdParty'
export type PluginCodeDriftState = 'needs_reload' | 'package_removed' | null
export interface PluginDiagnostic {
  labelKey: string
  value: string
}

interface PluginCommonView {
  releaseNotes: PluginReleaseNote[]
  /** 条目 uid：已安装为注册表 uid，市场为目录 uid；命令目标即此 uid。 */
  uid: string
  /** 插件标识（plugin_name），缺失时为 null。 */
  pluginId: string | null
  name: string
  description: string | null
  version: string | null
  author: string | null
  license: string | null
  tags: string[]
  packageName: string | null
  links: PluginLink[]
  /** 注册表或目录里的 requires_dist 原文。 */
  dependencies: string[]
  official: boolean
  publisher: PluginPublisher | null
  category: PluginCategory
  icon: PluginIcon
  binding: PluginAdapterBinding | null
  ui: PluginConfigUi | undefined
}

export interface MarketEntryView extends PluginCommonView {
  kind: 'market'
  updateNotes: PluginReleaseNote[]
  installedNotes: PluginReleaseNote[]
  /** 已安装版本；缺失按未安装处理。 */
  installedVersion: string | null
  installed: boolean
  /** 只取后端 update_available === true，前端不比较版本号。 */
  updateAvailable: boolean
  document: PluginCatalogDocument
}

export interface InstalledPluginView extends PluginCommonView {
  kind: 'installed'
  core: boolean
  local: boolean
  /** 注册表 source 原值；为空时不判官方、不显示来源。 */
  source: string | null
  enabled: boolean
  state: string
  status: PluginStatus
  fault: boolean
  error: string | null
  drift: PluginCodeDriftState
  disableImpact: DisableScope[]
  diagnostics: PluginDiagnostic[]
  /** 市场里同插件标识且后端判可更新的条目。 */
  upgrade: MarketEntryView | null
  document: PluginRegistryDocument
}

export type PluginView = InstalledPluginView | MarketEntryView

// ---------- 基础回落 ----------

/** 取第一个去空白后非空的字符串。 */
export function firstText(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value !== 'string') continue
    const text = value.trim()
    if (text) return text
  }
  return null
}

const textList = (value: unknown): string[] =>
  Array.isArray(value) ? value.flatMap(item => firstText(item) ?? []) : []

/** 副标题只拼有值的部分，不出现开头、结尾或连续的分隔符。 */
export function joinSegments(parts: readonly unknown[], separator = ' · '): string {
  return parts.flatMap(part => firstText(part) ?? []).join(separator)
}

/** 只认 http / https 绝对地址，其余当作没有。 */
function safeHttpUrl(value: unknown): string | null {
  const text = firstText(value)
  if (!text) return null
  try {
    const url = new URL(text)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

function pluginLinks(info: {
  docs_url?: string | null
  homepage?: string | null
  repository?: string | null
}): PluginLink[] {
  const links: Array<[PluginLinkKind, unknown]> = [
    ['docs', info.docs_url],
    ['homepage', info.homepage],
    ['repository', info.repository],
  ]
  return links.flatMap(([kind, value]) => {
    const href = safeHttpUrl(value)
    return href ? [{ kind, href }] : []
  })
}

/**
 * 名称依次取插件词条、注册表显示名、市场目录里同一插件的名称、插件标识、条目 uid。
 * 目录名称只给已安装条目兜底：装着的旧版本没声明显示名、目录里的新版本声明了。
 */
function resolvePluginName(
  uid: string,
  info: { plugin_name?: string | null; display_name?: string | null },
  texts: PluginTextSource,
  catalogName?: string | null
): string {
  const pluginId = firstText(info.plugin_name)
  // 没声明显示名时后端拿插件标识顶上，这种不算显示名，让给后面的兜底。
  const declared = (value: unknown) => {
    const text = firstText(value)
    return text && text !== pluginId ? text : undefined
  }
  return (
    firstText(
      declared(pluginId ? texts.text(pluginId, 'display_name') : undefined),
      declared(info.display_name),
      catalogName
    ) ??
    pluginId ??
    uid
  )
}

function resolveDescription(
  info: { plugin_name?: string | null; description?: string | null },
  texts: PluginTextSource
): string | null {
  const pluginId = firstText(info.plugin_name)
  return firstText(pluginId ? texts.text(pluginId, 'description') : undefined, info.description)
}

function resolveTags(
  info: { plugin_name?: string | null; tags?: readonly string[] | null },
  texts: PluginTextSource
): string[] {
  const pluginId = firstText(info.plugin_name)
  const localized = pluginId ? texts.tags(pluginId) : undefined
  return localized ? textList(localized) : textList(info.tags)
}

/** 同一个标识每次落到同一种颜色（FNV-1a）。 */
function pluginIconTone(key: string): PluginIconTone {
  let hash = 0x811c9dc5
  for (let index = 0; index < key.length; index += 1) {
    hash ^= key.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return PLUGIN_ICON_TONES[hash % PLUGIN_ICON_TONES.length]
}

/** 首字母取显示名第一个字符（英文转大写），显示名为空取插件标识首字符。 */
function pluginInitial(displayName: unknown, pluginId: unknown): string | null {
  const source = firstText(displayName) ?? firstText(pluginId)
  if (!source) return null
  return Array.from(source)[0].toUpperCase()
}

/** 图标依次取专项入口 logo、核心插件应用图标、首字母色块、通用插件图标。 */
export function resolvePluginIcon(input: {
  uid: string
  pluginId: string | null
  displayName: string | null
  core: boolean
  binding: PluginAdapterBinding | null
  appIcon: string
}): PluginIcon {
  const logo = firstText(input.binding?.logo)
  if (logo) return { kind: 'image', src: logo }
  if (input.core && firstText(input.appIcon)) return { kind: 'image', src: input.appIcon }
  const tone = pluginIconTone(input.pluginId ?? input.uid)
  const text = pluginInitial(input.displayName, input.pluginId)
  return text ? { kind: 'initial', text, tone } : { kind: 'generic', tone }
}

const KNOWN_TRANSITIONS = new Set(['loading', 'enabling', 'reloading', 'disabling', 'unloading'])

/** 状态不认识时显示原值、用中性颜色；缺失按未加载。 */
export function pluginStatus(state: unknown, drift: PluginCodeDriftState = null): PluginStatus {
  const raw = firstText(state) ?? 'unloaded'
  if (raw === 'fault_load' || raw === 'fault_runtime')
    return { labelKey: 'core.plugins.status.fault', raw, tone: 'error' }
  if (KNOWN_TRANSITIONS.has(raw))
    return { labelKey: `core.plugins.state.${raw}`, raw, tone: 'processing' }
  if (raw === 'enabled')
    return drift === 'needs_reload'
      ? { labelKey: 'core.plugins.status.needsReload', raw, tone: 'warning' }
      : { labelKey: 'core.plugins.status.enabled', raw, tone: 'success' }
  if (raw === 'disabled') return { labelKey: 'core.plugins.status.disabled', raw, tone: 'default' }
  if (raw === 'unloaded') return { labelKey: 'core.plugins.status.unloaded', raw, tone: 'default' }
  return { labelKey: null, raw, tone: 'default' }
}

function codeDrift(value: unknown): PluginCodeDriftState {
  return value === 'needs_reload' || value === 'package_removed' ? value : null
}

/** 已知来源给词条键；不认识的来源返回 null，由调用方显示原值；来源为空时整段不显示。 */
export function sourceLabelKey(source: string | null): string | null {
  return source && ['local', 'installed', 'market', 'package'].includes(source)
    ? `core.plugins.source.${source}`
    : null
}

function isOfficialPackage(packageName: unknown): boolean {
  const name = firstText(packageName)
  return name !== null && OFFICIAL_PACKAGE_NAMES.has(name)
}

/** PyPI 将大小写及连续的点、下划线、连字符视为同一发行包名。 */
function packageKey(name: string | null) {
  return name?.toLowerCase().replace(/[-_.]+/g, '-')
}

function findBinding(
  pluginId: string | null,
  bindings: readonly PluginAdapterBinding[]
): PluginAdapterBinding | null {
  return (pluginId && bindings.find(binding => binding.pluginId === pluginId)) || null
}

const disableScopes = (value: unknown): DisableScope[] =>
  Array.isArray(value)
    ? value.filter(
        (scope): scope is DisableScope =>
          scope === 'scripts' || scope === 'games' || scope === 'plans'
      )
    : []

// ---------- 条目整理 ----------

function documentsOf<T>(
  result: { order?: Array<{ uid: string }>; data?: Record<string, T> } | null | undefined
): Array<[string, T | undefined]> {
  const data = result?.data ?? {}
  const uids = result?.order?.length ? result.order.map(item => item.uid) : Object.keys(data)
  return uids.map(uid => [uid, data[uid]])
}

export function toMarketViews(
  catalog: PluginCatalogGetOut | null | undefined,
  registry: PluginRegistryGetOut | null | undefined,
  context: PluginModelContext
): MarketEntryView[] {
  const impactById = new Map<string, number>()
  for (const [, document] of documentsOf(registry)) {
    const id = firstText(document?.info?.plugin_name)
    if (id) impactById.set(id, disableScopes(document?.disableImpact).length)
  }
  return documentsOf(catalog).map(([uid, document]) => {
    const info = document?.info ?? {}
    const pluginId = firstText(info.plugin_name)
    const binding = findBinding(pluginId, context.bindings)
    const packageName = firstText(info.package_name)
    const official = isOfficialPackage(packageName)
    const installedVersion = firstText(info.installed_version)
    return {
      kind: 'market',
      releaseNotes: (info.changelog ?? []).filter(
        note => note.version === info.changelog_versions?.target
      ),
      installedNotes: (info.changelog ?? []).filter(
        note => note.version === info.changelog_versions?.installed
      ),
      updateNotes: (info.changelog ?? []).filter(note =>
        info.changelog_versions?.updates?.includes(note.version)
      ),
      uid,
      pluginId,
      name: resolvePluginName(uid, info, context.texts),
      description: resolveDescription(info, context.texts),
      version: firstText(info.version),
      author: firstText(info.author),
      license: firstText(info.license),
      tags: resolveTags(info, context.texts),
      packageName,
      links: pluginLinks(info),
      dependencies: textList(info.requires_dist),
      official,
      publisher: official ? 'official' : 'thirdParty',
      category:
        binding || (pluginId && (impactById.get(pluginId) ?? 0) > 0) ? 'specialized' : 'extension',
      icon: resolvePluginIcon({
        uid,
        pluginId,
        displayName: firstText(
          pluginId ? context.texts.text(pluginId, 'display_name') : undefined,
          info.display_name
        ),
        core: false,
        binding,
        appIcon: context.appIcon,
      }),
      binding,
      ui: document?.ui,
      installedVersion,
      installed: installedVersion !== null,
      updateAvailable: info.update_available === true,
      document: document ?? { uid, ui: {} },
    }
  })
}

function diagnosticsOf(info: NonNullable<PluginRegistryDocument['info']>): PluginDiagnostic[] {
  const items: Array<[string, unknown]> = [
    ['core.plugins.attribute.importName', info.import_name],
    ['core.plugins.attribute.lifecycle', info.lifecycle_context],
    ['core.plugins.attribute.codeDrift', info.code_drift],
    ['core.plugins.attribute.requires', textList(info.requires).join(', ')],
    ['core.plugins.attribute.wants', textList(info.wants).join(', ')],
    ['core.plugins.attribute.error', info.last_error],
  ]
  return items.flatMap(([labelKey, value]) => {
    const text = firstText(value)
    return text ? [{ labelKey, value: text }] : []
  })
}

export function toInstalledViews(
  registry: PluginRegistryGetOut | null | undefined,
  market: readonly MarketEntryView[],
  context: PluginModelContext
): InstalledPluginView[] {
  return documentsOf(registry).map(([uid, document]) => {
    const info = document?.info ?? {}
    const pluginId = firstText(info.plugin_name)
    const binding = findBinding(pluginId, context.bindings)
    const core = info.is_core === true
    const source = firstText(info.source)
    const local = info.is_local === true || source === 'local'
    const packageName = firstText(info.package_name)
    const disableImpact = disableScopes(document?.disableImpact)
    const publisher: PluginPublisher | null = core
      ? 'official'
      : local
        ? 'local'
        : !source
          ? null
          : isOfficialPackage(packageName)
            ? 'official'
            : 'thirdParty'
    const drift = codeDrift(info.code_drift)
    const status = pluginStatus(info.state, drift)
    const catalogEntry = pluginId ? market.find(entry => entry.pluginId === pluginId) : undefined
    // 目录条目自己也没有名称时它的 name 就是插件标识，不算兜底。
    const catalogName = catalogEntry && catalogEntry.name !== pluginId ? catalogEntry.name : null
    const name = resolvePluginName(uid, info, context.texts, catalogName)
    return {
      kind: 'installed',
      // 两份查询可独立刷新，只有目录中记录的安装身份仍匹配时才回看该版。
      releaseNotes:
        source === 'installed' &&
        !local &&
        !core &&
        packageName &&
        catalogEntry &&
        packageKey(packageName) === packageKey(catalogEntry.packageName) &&
        info.version === catalogEntry.installedVersion &&
        drift !== 'package_removed'
          ? catalogEntry.installedNotes
          : [],
      uid,
      pluginId,
      name,
      description: resolveDescription(info, context.texts),
      version: firstText(info.version),
      author: firstText(info.author),
      license: firstText(info.license),
      tags: resolveTags(info, context.texts),
      packageName,
      links: pluginLinks(info),
      dependencies: textList(info.requires_dist),
      official: publisher === 'official',
      publisher,
      category: core
        ? 'core'
        : local
          ? 'local'
          : binding || disableImpact.length
            ? 'specialized'
            : 'extension',
      icon: resolvePluginIcon({
        uid,
        pluginId,
        displayName: name === pluginId || name === uid ? null : name,
        core,
        binding,
        appIcon: context.appIcon,
      }),
      binding,
      ui: document?.ui,
      core,
      local,
      source,
      enabled: info.enabled === true,
      state: status.raw,
      status,
      fault: status.tone === 'error',
      error: firstText(info.last_error),
      drift,
      disableImpact,
      diagnostics: diagnosticsOf(info),
      upgrade:
        (pluginId && market.find(entry => entry.pluginId === pluginId && entry.updateAvailable)) ||
        null,
      document: document ?? { uid, ui: {} },
    }
  })
}

// ---------- 详情字段 ----------

export type DetailFieldKey =
  | 'author'
  | 'license'
  | 'publisher'
  | 'source'
  | 'packageName'
  | 'tags'
  | 'dependencies'

/**
 * 详情里有值的字段，缺哪项不显示哪项。已安装有来源时把包名并进「来源」；
 * 市场条目、或已安装但来源为空时单列「包名」，不因来源缺失把包名一起丢掉。
 */
export function detailFieldKeys(view: PluginView): DetailFieldKey[] {
  const source = view.kind === 'installed' && view.source !== null
  const present: Record<DetailFieldKey, boolean> = {
    author: view.author !== null,
    license: view.license !== null,
    publisher: view.publisher !== null,
    source,
    packageName: !source && view.packageName !== null,
    tags: view.tags.length > 0,
    dependencies: view.dependencies.length > 0,
  }
  return (Object.keys(present) as DetailFieldKey[]).filter(key => present[key])
}

// ---------- 用量与停用拦截 ----------

export interface UsageScript {
  uid: string
  name: string
  scriptType: string
  /** 账号数；读不到时为 null。 */
  accounts: number | null
}

export interface PluginUsageSource {
  state: 'loading' | 'error' | 'ready'
  scripts: readonly UsageScript[]
  /** 计划表按配置类型计数；读不到时为 null。 */
  planCounts: Readonly<Record<string, number>> | null
}

/**
 * 用量来源状态。current 表示本次进入插件中心后已成功取到过托管列表；
 * 跨页缓存里的旧数据不算，一律按加载中处理，不能据此放行停用与卸载。
 */
export function usageSourceState(input: {
  failed: boolean
  current: boolean
}): PluginUsageSource['state'] {
  if (input.failed) return 'error'
  return input.current ? 'ready' : 'loading'
}

export type PluginUsage =
  /** 不带数据的普通插件。 */
  | { kind: 'none' }
  /** 能对上托管类型，但托管列表还没加载完。 */
  | { kind: 'pending' }
  /** 能对上托管类型，但托管列表加载失败。 */
  | { kind: 'failed' }
  /** 对不上托管类型，后端说停用有数据影响（第三方专项）。 */
  | { kind: 'impactOnly'; scopes: DisableScope[] }
  | {
      kind: 'counted'
      scripts: UsageScript[]
      scriptCount: number
      accountCount: number | null
      planCount: number | null
    }

export function pluginUsage(
  view: Pick<InstalledPluginView, 'binding' | 'disableImpact'>,
  source: PluginUsageSource
): PluginUsage {
  const binding = view.binding
  if (!binding)
    return view.disableImpact.length
      ? { kind: 'impactOnly', scopes: [...view.disableImpact] }
      : { kind: 'none' }
  if (source.state === 'loading') return { kind: 'pending' }
  if (source.state === 'error') return { kind: 'failed' }
  const scripts = source.scripts.filter(script => script.scriptType === binding.scriptType)
  const accounts = scripts.map(script => script.accounts)
  return {
    kind: 'counted',
    scripts,
    scriptCount: scripts.length,
    accountCount: accounts.every(count => count !== null)
      ? accounts.reduce<number>((sum, count) => sum + (count ?? 0), 0)
      : null,
    planCount:
      binding.planConfigType && source.planCounts
        ? (source.planCounts[binding.planConfigType] ?? 0)
        : null,
  }
}

export type UsageSegmentKey =
  | 'core.plugins.usage.scripts'
  | 'core.plugins.usage.accounts'
  | 'core.plugins.usage.plans'
export interface UsageSegment {
  key: UsageSegmentKey
  count: number
}

/** 只有确定的正数才显示，拿不到或为 0 的段不显示。 */
export function usageSegments(usage: PluginUsage): UsageSegment[] {
  if (usage.kind !== 'counted') return []
  const segments: Array<[UsageSegmentKey, number | null]> = [
    ['core.plugins.usage.scripts', usage.scriptCount],
    ['core.plugins.usage.accounts', usage.accountCount],
    ['core.plugins.usage.plans', usage.planCount],
  ]
  return segments.flatMap(([key, count]) => (count ? [{ key, count }] : []))
}

export type LifecycleDecision =
  /** 有托管在用，前端拦住，列出在用托管。 */
  | { kind: 'blockedInUse'; scripts: UsageScript[] }
  /** 用量还不知道，先拦住并提示重试，不当成没有托管。 */
  | { kind: 'blockedUnknown'; reason: 'loading' | 'failed' }
  /** 照现有流程确认后执行；scopes 为后端给的影响范围（可能为空）。 */
  | { kind: 'confirm'; scopes: DisableScope[] }
  | { kind: 'direct' }

/** 停用与卸载的拦截判断；按钮能否点仍由界面提示决定，见 actionHint。 */
export function lifecycleDecision(
  action: 'disable' | 'uninstall',
  view: Pick<InstalledPluginView, 'disableImpact'>,
  usage: PluginUsage
): LifecycleDecision {
  if (usage.kind === 'pending') return { kind: 'blockedUnknown', reason: 'loading' }
  if (usage.kind === 'failed') return { kind: 'blockedUnknown', reason: 'failed' }
  if (usage.kind === 'counted' && usage.scriptCount > 0)
    return { kind: 'blockedInUse', scripts: usage.scripts }
  if (action === 'uninstall') return { kind: 'confirm', scopes: [...view.disableImpact] }
  return view.disableImpact.length
    ? { kind: 'confirm', scopes: [...view.disableImpact] }
    : { kind: 'direct' }
}

/** 停用或卸载时后端会一并拆掉的下游插件（disableCascade / uninstallCascade）。 */
export function lifecycleCascade(
  action: 'disable' | 'uninstall',
  view: Pick<InstalledPluginView, 'document'>
): string[] {
  const names = action === 'disable' ? view.document.disableCascade : view.document.uninstallCascade
  return [...(names ?? [])]
}

/** 停用或卸载会一并删除的托管（名称）与计划表（张数）：本插件及连带范围里各专项名下的。 */
export function lifecycleAffected(
  action: 'disable' | 'uninstall',
  view: Pick<InstalledPluginView, 'pluginId' | 'document'>,
  installed: readonly InstalledPluginView[],
  usageOf: (view: InstalledPluginView) => PluginUsage
): { scripts: string[]; plans: number } {
  const names = new Set([view.pluginId, ...lifecycleCascade(action, view)])
  const scripts: string[] = []
  let plans = 0
  for (const item of installed) {
    if (!item.binding || !names.has(item.pluginId)) continue
    const usage = usageOf(item)
    if (usage.kind !== 'counted') continue
    scripts.push(...usage.scripts.map(script => script.name))
    plans += usage.planCount ?? 0
  }
  return { scripts, plans }
}

// ---------- 操作可见性（只读后端界面提示） ----------

export function actionHint(view: Pick<PluginView, 'ui'>, action: LifecycleAction | 'install') {
  return pluginActionHint(view.ui, 'info', action)
}
export const actionVisible = (view: Pick<PluginView, 'ui'>, action: LifecycleAction | 'install') =>
  actionHint(view, action) !== undefined
export const actionEditable = (view: Pick<PluginView, 'ui'>, action: LifecycleAction | 'install') =>
  actionHint(view, action)?.editable === true

/** 不带数据的普通插件用行内开关启停；带数据的走「更多」菜单。 */
export function usesInlineToggle(view: Pick<InstalledPluginView, 'binding' | 'disableImpact'>) {
  return view.binding === null && view.disableImpact.length === 0
}

export interface ToggleState {
  visible: boolean
  checked: boolean
  /** 切换时要提交的命令。 */
  action: 'enable' | 'disable'
  editable: boolean
}

export function toggleState(view: Pick<InstalledPluginView, 'ui' | 'enabled'>): ToggleState {
  const checked = pluginToggleChecked(view.ui, view.enabled)
  const action = checked ? 'disable' : 'enable'
  return {
    visible: actionVisible(view, 'enable') || actionVisible(view, 'disable'),
    checked,
    action,
    editable: actionEditable(view, action),
  }
}

/** 「更新至 x」按钮文案；目录条目没有版本号时回落为「升级」。 */
export function updateActionLabel(version: string | null): {
  key: 'core.plugins.updateTo' | 'core.plugins.upgrade'
  params: { version?: string }
} {
  return version
    ? { key: 'core.plugins.updateTo', params: { version } }
    : { key: 'core.plugins.upgrade', params: {} }
}

export type MarketAction = 'update' | 'install' | 'installed'
/** 市场按钮：可更新 → 更新至；已安装 → 已安装；否则安装。 */
export function marketAction(
  entry: Pick<MarketEntryView, 'installed' | 'updateAvailable'>
): MarketAction {
  if (entry.updateAvailable) return 'update'
  return entry.installed ? 'installed' : 'install'
}

// ---------- 搜索、筛选、分组 ----------

/** 不区分大小写，匹配名称、插件标识、包名、作者与标签；空查询全部通过。 */
export function matchesSearch(view: PluginView, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return [view.name, view.pluginId, view.packageName, view.author, ...view.tags]
    .flatMap(value => firstText(value) ?? [])
    .some(value => value.toLowerCase().includes(needle))
}

export function matchesInstalledFilter(view: InstalledPluginView, filter: InstalledFilter) {
  if (filter === 'official') return view.official
  if (filter === 'update') return view.upgrade !== null
  if (filter === 'fault') return view.fault
  return true
}

export function matchesMarketFilter(view: MarketEntryView, filter: MarketFilter) {
  if (filter === 'specialized') return view.category === 'specialized'
  if (filter === 'extension') return view.category !== 'specialized'
  return true
}

export interface PluginGroup {
  category: PluginCategory
  views: InstalledPluginView[]
}

/** 按核心、专项适配、扩展、本地源码分组，组内保持注册表顺序，空组不出现。 */
export function groupInstalled(views: readonly InstalledPluginView[]): PluginGroup[] {
  return PLUGIN_CATEGORY_ORDER.map(category => ({
    category,
    views: views.filter(view => view.category === category),
  })).filter(group => group.views.length > 0)
}

// ---------- 市场栅格 ----------

export const MARKET_CARD_MIN_WIDTH = 300
export const MARKET_CARD_GAP = 16

/**
 * 取容器能放下的最大列数；末行只剩一张时，取不少于 2 列、末行不再只剩一张的最大列数，
 * 找不到就保持最大列数，不退成单列。
 */
export function marketColumnCount(
  containerWidth: number,
  cardCount: number,
  minCardWidth = MARKET_CARD_MIN_WIDTH,
  gap = MARKET_CARD_GAP
): number {
  const width = Number.isFinite(containerWidth) ? Math.max(containerWidth, 0) : 0
  const max = Math.max(1, Math.floor((width + gap) / (minCardWidth + gap)))
  for (let columns = max; columns >= 2; columns -= 1) {
    if (cardCount <= columns || cardCount % columns !== 1) return columns
  }
  return max
}

// ---------- 更新 ----------

export interface PluginUpdateView {
  /** 市场条目，安装命令提交它的 uid。 */
  entry: MarketEntryView
  installed: InstalledPluginView | null
  /** 现版本；拿不到时为 null，不显示。 */
  fromVersion: string | null
  toVersion: string | null
}

/** 可更新列表只看后端给的 update_available，按目录顺序。 */
export function updatableEntries(
  market: readonly MarketEntryView[],
  installed: readonly InstalledPluginView[]
): PluginUpdateView[] {
  return market
    .filter(entry => entry.updateAvailable)
    .map(entry => {
      const record =
        (entry.pluginId && installed.find(view => view.pluginId === entry.pluginId)) || null
      return {
        entry,
        installed: record,
        fromVersion: entry.installedVersion ?? record?.version ?? null,
        toVersion: entry.version,
      }
    })
}

// ---------- 设置入口 ----------

export type SettingsVisibility = 'visible' | 'hidden' | 'unknown' | 'loading'
export interface PluginSettingsGroup<THint = unknown> {
  name: string
  hints: THint[]
}

/** 插件自有配置里有提示项的分组；与设置页使用同一判据。 */
export function pluginSettingsGroups<THint = unknown>(
  config: unknown
): PluginSettingsGroup<THint>[] {
  if (!config || typeof config !== 'object') return []
  const ui = (config as Record<string, unknown>).ui
  const hints = ui && typeof ui === 'object' ? (ui as Record<string, unknown>).hints : null
  if (!hints || typeof hints !== 'object') return []
  return Object.entries(hints as Record<string, unknown>).flatMap(([name, value]) =>
    Array.isArray(value) && value.length ? [{ name, hints: value as THint[] }] : []
  )
}

/** 确定没有可见设置才隐藏；读失败时仍给入口，由设置页显示失败与重试。 */
export const showSettingsEntry = (visibility: SettingsVisibility) =>
  visibility === 'visible' || visibility === 'unknown'

// ---------- 安装阶段 ----------

export type InstallPhase =
  | 'queued'
  | 'running'
  | 'waiting'
  | 'restarting'
  | 'recovering'
  | 'succeeded'
  | 'failed'

export const isInstallPhaseActive = (phase: InstallPhase | null | undefined) =>
  phase === 'queued' ||
  phase === 'running' ||
  phase === 'waiting' ||
  phase === 'restarting' ||
  phase === 'recovering'

/** 需要重启后端的阶段：等待当前任务结束、重启中、恢复原环境。 */
export const isInstallRestartPhase = (phase: InstallPhase | null | undefined) =>
  phase === 'waiting' || phase === 'restarting' || phase === 'recovering'

export function installPhaseLabelKey(phase: InstallPhase, upgrade: boolean): string {
  // 前缀写全：只拼到 `core.plugins.` 的话，词条审计会把整个 core.plugins.* 都当成在用。
  if (isInstallRestartPhase(phase))
    return upgrade
      ? `core.plugins.upgradeProgress.${phase}`
      : `core.plugins.installProgress.${phase}`
  if (phase === 'running')
    return `core.plugins.installPhase.${upgrade ? 'upgrading' : 'installing'}`
  return `core.plugins.installPhase.${phase}`
}
