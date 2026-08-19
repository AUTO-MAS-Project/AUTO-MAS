import type { ScriptType } from '@/types/script'

export interface SatelliteModule {
  scriptType: ScriptType
  iconUrl: string
  enabled: boolean
}

const iconModules = import.meta.glob<{ default: string }>(
  ['@/assets/satellite-icons/*.png', '@/assets/ok-nte.ico', '@/assets/hsr.png'],
  {
    eager: true,
    query: 'url',
  }
)

function getIconUrl(filename: string): string {
  const key = Object.keys(iconModules).find(k => k.endsWith(`/${filename}`))
  if (!key) return ''
  const mod = iconModules[key]
  return typeof mod === 'string' ? mod : (mod as { default: string }).default
}

const filenameToScriptType: Record<string, ScriptType> = {
  'MAA.png': 'MAA',
  'SRC.png': 'SRC',
  'M9A.png': 'M9A',
  'MaaEnd.png': 'MaaEnd',
  'ok-ww.png': 'Okww',
  'ok-nte.ico': 'OkNte',
  'hsr.png': 'HSR',
  'bettergi.png': 'BetterGI',
}

const iconFilenames: ScriptType[] = ['MAA', 'SRC', 'M9A', 'MaaEnd', 'Okww', 'OkNte', 'HSR', 'BetterGI']

export const satelliteModules: SatelliteModule[] = iconFilenames
  .map(type => {
    const filename = Object.entries(filenameToScriptType).find(([, t]) => t === type)?.[0] ?? ''
    return {
      scriptType: type,
      iconUrl: getIconUrl(filename),
      enabled: true,
    }
  })
  .filter(module => module.iconUrl !== '')

export const centerIconUrl = getIconUrl('AUTO-MAS.png')
