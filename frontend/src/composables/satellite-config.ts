import centerIcon from '@/assets/AUTO-MAS.ico'
import type { ScriptType } from '@/types/script'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'

interface SatelliteModule {
  scriptType: ScriptType
  iconUrl: string
  enabled: boolean
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
