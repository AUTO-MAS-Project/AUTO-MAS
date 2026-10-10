import centerIcon from '@/assets/AUTO-MAS.ico'
import type { ScriptType } from '@/types/script'
import { buildMaaFWScriptIconUrl } from '@/utils/maafwProjectIcon'
import { SCRIPT_LABELS, SCRIPT_LOGOS } from '@/utils/scriptLogos'

interface SatelliteModule {
  scriptType: ScriptType
  iconUrl: string
  enabled: boolean
}

/** 上轨道的一颗卫星 */
export interface OrbitModule {
  /** 卫星键：一般就是脚本类型；通用 MFW 每个项目一颗，键带上项目 */
  key: string
  scriptType: ScriptType
  /** 悬停标签和「××，启动！」里的名字 */
  label: string
  iconUrl: string
  /** iconUrl 加载不出来时换用的图标 */
  fallbackIconUrl?: string
  /** 归到这颗卫星的脚本 */
  scriptIds: string[]
}

/** 建卫星用到的脚本字段（脚本列表接口的一项） */
export interface OrbitScript {
  uid: string
  type: string
  config?: unknown
}

/**
 * 不上轨道的脚本类型。
 *
 * 通用脚本在 SCRIPT_LOGOS 里用的就是 AUTO-MAS 自己的图标，也就是这圈卫星的中心图标，
 * 放上去会出现一颗和中心一模一样的卫星。
 */
const EXCLUDED_FROM_ORBIT: readonly ScriptType[] = ['General']

/**
 * 卫星在轨道上的排列顺序。
 *
 * 只影响观感，不是白名单：没列进来的脚本类型排在后面，所以新增脚本类型时不用动这里也
 * 会自动出现在主页上。图标来源统一走 SCRIPT_LOGOS —— 它声明成 `Record<ScriptType, string>`，
 * 新增脚本类型时不补图标会当场 typecheck 报错，不会像以前那样悄悄漏掉。
 */
const ORBIT_ORDER: readonly ScriptType[] = [
  'MAA',
  'SRC',
  'M9A',
  'MaaEnd',
  'Okww',
  'OkNte',
  'HSR',
  'MaaFW',
  'BetterGI',
  'ZzzOd',
  'MSS',
]

function orbitRank(type: ScriptType): number {
  const index = ORBIT_ORDER.indexOf(type)
  return index === -1 ? ORBIT_ORDER.length : index
}

export const satelliteModules: SatelliteModule[] = (Object.keys(SCRIPT_LOGOS) as ScriptType[])
  .filter(type => !EXCLUDED_FROM_ORBIT.includes(type))
  .sort((left, right) => orbitRank(left) - orbitRank(right))
  .map(type => ({
    scriptType: type,
    iconUrl: SCRIPT_LOGOS[type],
    enabled: true,
  }))

export const centerIconUrl = centerIcon

function readMaaFWInfo(config: unknown): { label: string; path: string; name: string } {
  const info =
    typeof config === 'object' && config !== null
      ? (config as { Info?: Record<string, unknown> }).Info
      : undefined
  const text = (value: unknown) => (typeof value === 'string' ? value.trim() : '')
  return { label: text(info?.ProjectLabel), path: text(info?.Path), name: text(info?.Name) }
}

/**
 * 通用 MFW 跑的项目各不相同，每个项目一颗卫星，用项目自己的图标（取不到回退 MaaFW 图标）。
 * 同一个项目建了几个脚本也只出一颗：按项目名（引导页读到 interface 时记下的 ProjectLabel）
 * 归并，没记过项目名的按项目目录，目录也没有的各算各的。
 */
function maafwProjectModules(scripts: readonly OrbitScript[]): OrbitModule[] {
  const byKey = new Map<string, OrbitModule>()
  for (const script of scripts) {
    const { label, path, name } = readMaaFWInfo(script.config)
    const key = `MaaFW:${label ? `project:${label}` : path ? `path:${path}` : `id:${script.uid}`}`
    const existing = byKey.get(key)
    if (existing) {
      existing.scriptIds.push(script.uid)
      continue
    }
    byKey.set(key, {
      key,
      scriptType: 'MaaFW',
      label: label || name || SCRIPT_LABELS.MaaFW,
      iconUrl: buildMaaFWScriptIconUrl(script.uid),
      fallbackIconUrl: SCRIPT_LOGOS.MaaFW,
      scriptIds: [script.uid],
    })
  }
  return [...byKey.values()]
}

/** 用户建过的脚本 → 上轨道的卫星：每种脚本类型一颗，通用 MFW 每个项目一颗 */
export function buildOrbitModules(scripts: readonly OrbitScript[]): OrbitModule[] {
  const modules: OrbitModule[] = []
  for (const { scriptType, iconUrl, enabled } of satelliteModules) {
    if (!enabled) continue
    const ofType = scripts.filter(script => script.type === scriptType)
    if (ofType.length === 0) continue

    if (scriptType === 'MaaFW') {
      modules.push(...maafwProjectModules(ofType))
      continue
    }
    modules.push({
      key: scriptType,
      scriptType,
      label: SCRIPT_LABELS[scriptType],
      iconUrl,
      scriptIds: ofType.map(script => script.uid),
    })
  }
  return modules
}

/** 脚本 ID → 卫星键，运行状态按它汇总到各颗卫星 */
export function orbitKeysByScriptId(modules: readonly OrbitModule[]): Map<string, string> {
  const keys = new Map<string, string>()
  for (const module of modules) {
    for (const scriptId of module.scriptIds) keys.set(scriptId, module.key)
  }
  return keys
}
