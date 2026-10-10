import type { OrbitModule } from '@/composables/satellite-config'
import type { SatelliteModuleStatus } from '@/composables/useSatelliteStatus'
import { isMaaFWFamily } from '@/composables/useMaaFWFlavor'
import { SCRIPT_LABELS, SCRIPT_LOGOS } from '@/utils/scriptLogos'
import { ORBIT_RINGS, type OrbitRing } from './config'
import { getSatelliteSlot, type SatelliteSlot } from './motion'

export interface PlanetaryModule extends OrbitModule {
  /** 有父行星的项目绕父行星公转，其余项目绕 MAS 公转 */
  parentKey?: string
}

export interface PlanetarySlot extends SatelliteSlot {
  parentIndex: number | null
  moonRing: OrbitRing | null
  planetRing: OrbitRing | null
}

const MFW_PLANET_KEY = 'MaaFW'
/** 缩短半径后增大倾角，家族中心仍绕开 MAS 星核。 */
const MFW_PLANET_TILT_X = 0.36

/** 为卫星预留主轨道四分之一的范围，镜头和图标尺寸沿用 dev。 */
export const MOON_ORBIT_SCALE = 0.25

/** 家族行星仍在最外圈，主轨道和局部轨道合计不超出原有范围。 */
export function getPlanetaryOrbitRings(
  modules: readonly { parentKey?: string }[]
): readonly OrbitRing[] {
  if (!modules.some(module => module.parentKey)) return ORBIT_RINGS
  return ORBIT_RINGS.map((ring, index) =>
    index === 0
      ? { ...ring, radius: ring.radius * (1 - MOON_ORBIT_SCALE), tiltX: MFW_PLANET_TILT_X }
      : ring
  )
}

/** MFW 家族共用一颗行星，项目图标和脚本状态仍分别归到各自的卫星。 */
export function buildPlanetaryModules(modules: readonly OrbitModule[]): PlanetaryModule[] {
  const family = modules.filter(module => isMaaFWFamily(module.scriptType))
  if (family.length === 0) return [...modules]

  return [
    {
      key: MFW_PLANET_KEY,
      scriptType: 'MaaFW',
      label: SCRIPT_LABELS.MaaFW,
      iconUrl: SCRIPT_LOGOS.MaaFW,
      scriptIds: [],
    },
    ...family.map(module => ({ ...module, parentKey: MFW_PLANET_KEY })),
    ...modules.filter(module => !isMaaFWFamily(module.scriptType)),
  ]
}

/** 先分配行星轨道，再把卫星均分到父行星周围的小轨道。 */
export function getPlanetarySlots(
  modules: readonly { key: string; parentKey?: string }[]
): PlanetarySlot[] {
  const planets = modules.filter(module => !module.parentKey)
  const planetRings = getPlanetaryOrbitRings(modules)
  const hasFamily = modules.some(module => module.parentKey)
  return modules.map(module => {
    if (!module.parentKey) {
      const hasMoons = modules.some(candidate => candidate.parentKey === module.key)
      // MFW 独占最外层，其他专项沿用原有的两条内圈。
      let slot = getSatelliteSlot(planets.indexOf(module), planets.length)
      if (hasFamily) {
        slot = hasMoons
          ? getSatelliteSlot(0, 1)
          : getSatelliteSlot(
              planets.indexOf(module) - 1,
              planets.length - 1,
              ORBIT_RINGS.length - 1
            )
        if (!hasMoons) slot.ring += 1
      }
      const orbit = planetRings[slot.ring]
      return {
        ...slot,
        parentIndex: null,
        moonRing: null,
        planetRing: hasMoons ? orbit : null,
      }
    }

    const siblings = modules.filter(candidate => candidate.parentKey === module.parentKey)
    const slot = getSatelliteSlot(siblings.indexOf(module), siblings.length)
    const orbit = ORBIT_RINGS[slot.ring]
    return {
      ...slot,
      parentIndex: modules.findIndex(candidate => candidate.key === module.parentKey),
      moonRing: {
        ...orbit,
        radius: orbit.radius * MOON_ORBIT_SCALE,
        // 局部轨道倾角随尺度收小，为卫星保留原画幅内的空间。
        tiltX: orbit.tiltX * MOON_ORBIT_SCALE,
      },
      planetRing: null,
    }
  })
}

/** 父行星汇总卫星的运行状态；脚本到项目的映射保持一对一。 */
export function getPlanetaryStatuses(
  modules: readonly PlanetaryModule[],
  statuses: ReadonlyMap<string, SatelliteModuleStatus>
): ReadonlyMap<string, SatelliteModuleStatus> {
  const result = new Map(statuses)
  for (const module of modules) {
    if (!module.parentKey) continue
    const status = statuses.get(module.key)
    if (!status) continue
    const parent = result.get(module.parentKey)
    result.set(module.parentKey, {
      queued: Boolean(parent?.queued || status.queued),
      running: Boolean(parent?.running || status.running),
      lastFailed: Boolean(parent?.lastFailed || status.lastFailed),
    })
  }
  return result
}
