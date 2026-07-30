import hsrIcon from '@/assets/hsr.png'
import { OpenAPI } from '@/api/core/OpenAPI'

export interface SatelliteModule {
  typeKey: string
  displayName: string
  iconUrl: string
  instanceCount: number
}

export interface SatelliteModuleDiscovery {
  modules: SatelliteModule[]
  hasSpecializedInstances: boolean
}

export interface SatelliteScriptTypeDescriptor {
  type_key: string
  display_name: string
  icon_url?: string | null
  create_group?: string | null
  create_group_declared?: boolean
  available?: boolean
}

export interface SatelliteScriptRecord {
  type: string
}

const iconModules = import.meta.glob<{ default: string }>('@/assets/satellite-icons/*.png', {
  eager: true,
  query: 'url',
})

const localIconFilenames: Readonly<Record<string, string>> = {
  MAA: 'MAA.png',
  SRC: 'SRC.png',
  MaaEnd: 'MaaEnd.png',
  M9A: 'M9A.png',
  Okww: 'ok-ww.png',
}

function getLocalIconUrl(filename: string): string | null {
  const key = Object.keys(iconModules).find(path => path.endsWith(`/${filename}`))
  if (!key) return null

  const module = iconModules[key]
  return typeof module === 'string' ? module : module.default
}

function resolveDeclaredIconUrl(iconUrl: string): string {
  if (!iconUrl.startsWith('/')) return iconUrl

  const base = (OpenAPI.BASE || 'http://localhost:36163').replace(/\/+$/, '')
  return `${base}${iconUrl}`
}

export function resolveSatelliteIconUrl(
  typeKey: string,
  declaredIconUrl?: string | null
): string | null {
  const normalizedIconUrl = declaredIconUrl?.trim()
  if (normalizedIconUrl) {
    return resolveDeclaredIconUrl(normalizedIconUrl)
  }

  if (typeKey === 'HSR') return hsrIcon

  const filename = localIconFilenames[typeKey]
  return filename ? getLocalIconUrl(filename) : null
}

export function buildSatelliteModules(
  descriptors: readonly SatelliteScriptTypeDescriptor[],
  records: readonly SatelliteScriptRecord[]
): SatelliteModuleDiscovery {
  const instanceCounts = records.reduce<Map<string, number>>((counts, record) => {
    counts.set(record.type, (counts.get(record.type) ?? 0) + 1)
    return counts
  }, new Map())
  const includedTypes = new Set<string>()

  let hasSpecializedInstances = false
  const modules = descriptors.flatMap(descriptor => {
    const typeKey = descriptor.type_key
    const instanceCount = instanceCounts.get(typeKey) ?? 0
    if (
      descriptor.create_group_declared !== true ||
      descriptor.create_group !== 'specialized' ||
      descriptor.available !== true ||
      instanceCount === 0 ||
      includedTypes.has(typeKey)
    ) {
      return []
    }

    hasSpecializedInstances = true
    const iconUrl = resolveSatelliteIconUrl(typeKey, descriptor.icon_url)
    if (!iconUrl) return []

    includedTypes.add(typeKey)
    return [
      {
        typeKey,
        displayName: descriptor.display_name.trim() || typeKey,
        iconUrl,
        instanceCount,
      },
    ]
  })

  return { modules, hasSpecializedInstances }
}

export async function getSatelliteModules(): Promise<SatelliteModuleDiscovery> {
  const { useScriptRegistryApi } = await import('@/composables/useScriptRegistryApi')
  const { getScriptTypes, getScripts } = useScriptRegistryApi()
  const [descriptors, records] = await Promise.all([getScriptTypes(), getScripts()])
  return buildSatelliteModules(descriptors, records)
}
