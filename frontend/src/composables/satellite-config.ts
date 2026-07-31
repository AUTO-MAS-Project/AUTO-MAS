import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { OpenAPI } from '@/api/core/OpenAPI'
import type { ScriptTypeDescriptor } from '@/types/scriptRegistry'

export interface SatelliteModule {
  scriptType: string
  displayName: string
  iconUrl: string
  instanceCount: number
}

const iconModules = import.meta.glob<{ default: string }>('@/assets/satellite-icons/*.png', {
  eager: true,
  query: 'url',
})

const builtinIconFiles: Record<string, string> = {
  MAA: 'MAA.png',
  SRC: 'SRC.png',
  MaaEnd: 'MaaEnd.png',
  Okww: 'ok-ww.png',
}

function getLocalIconUrl(filename: string): string {
  const key = Object.keys(iconModules).find(path => path.endsWith(`/${filename}`))
  if (!key) return ''
  const iconModule = iconModules[key]
  return typeof iconModule === 'string' ? iconModule : (iconModule as { default: string }).default
}

function getDeclaredIconUrl(descriptor: ScriptTypeDescriptor): string {
  const iconUrl = descriptor.icon_url?.trim()
  if (iconUrl) {
    if (iconUrl.startsWith('/')) {
      const apiBase = (OpenAPI.BASE || 'http://localhost:36163').replace(/\/+$/, '')
      return `${apiBase}${iconUrl}`
    }
    return iconUrl
  }
  return getLocalIconUrl(builtinIconFiles[descriptor.type_key] ?? '')
}

export async function getSatelliteModules(): Promise<SatelliteModule[]> {
  const registryApi = useScriptRegistryApi()
  const [descriptors, scripts] = await Promise.all([
    registryApi.getScriptTypes(),
    registryApi.getScripts(),
  ])

  const instanceCountByType = new Map<string, number>()
  scripts.forEach(script => {
    if (script.available === false) return
    instanceCountByType.set(script.type, (instanceCountByType.get(script.type) ?? 0) + 1)
  })

  return descriptors
    .filter(
      descriptor =>
        descriptor.available !== false &&
        descriptor.create_group === 'specialized' &&
        (instanceCountByType.get(descriptor.type_key) ?? 0) > 0
    )
    .map(descriptor => ({
      scriptType: descriptor.type_key,
      displayName: descriptor.display_name,
      iconUrl: getDeclaredIconUrl(descriptor),
      instanceCount: instanceCountByType.get(descriptor.type_key) ?? 0,
    }))
    .filter(module => module.iconUrl !== '')
}

export const centerIconUrl = getLocalIconUrl('AUTO-MAS.png')
