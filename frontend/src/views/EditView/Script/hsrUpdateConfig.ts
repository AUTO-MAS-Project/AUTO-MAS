import type { HSRConfig_Update } from '@/api'

type HSRAutoUpdateMode = 'Off' | 'BeforeRun' | 'AfterRun'
type HSRUpdateChannel = 'stable' | 'beta'
type HSRM7ASource = 'GitHub' | 'MirrorChyan'
type HSRSRASource = 'AutoSite' | 'GitHub' | 'MirrorChyan'
export type HSRUpdateConfig = {
  AutoUpdateMode: HSRAutoUpdateMode
  Channel: HSRUpdateChannel
  M7ASource: HSRM7ASource
  SRASource: HSRSRASource
  MirrorChyanCDK: string
}

// 上面几个字面量是手写的（生成类型字段全为 optional | null，做不了非空
// reactive），因此必须钉住它们与 OpenAPI 生成类型一致：后端改了枚举而这里没跟，
// 下面的赋值会直接 typecheck 失败，而不是等用户选中一个后端不认的值才 422。
type _AssertUpdateEnums = {
  mode: HSRAutoUpdateMode extends NonNullable<HSRConfig_Update['AutoUpdateMode']>
    ? NonNullable<HSRConfig_Update['AutoUpdateMode']> extends HSRAutoUpdateMode
      ? true
      : never
    : never
  channel: HSRUpdateChannel extends NonNullable<HSRConfig_Update['Channel']>
    ? NonNullable<HSRConfig_Update['Channel']> extends HSRUpdateChannel
      ? true
      : never
    : never
  m7a: HSRM7ASource extends NonNullable<HSRConfig_Update['M7ASource']>
    ? NonNullable<HSRConfig_Update['M7ASource']> extends HSRM7ASource
      ? true
      : never
    : never
  sra: HSRSRASource extends NonNullable<HSRConfig_Update['SRASource']>
    ? NonNullable<HSRConfig_Update['SRASource']> extends HSRSRASource
      ? true
      : never
    : never
}
const _assertUpdateEnums: _AssertUpdateEnums = {
  mode: true,
  channel: true,
  m7a: true,
  sra: true,
}
void _assertUpdateEnums

const HSR_AUTO_UPDATE_MODES: readonly HSRAutoUpdateMode[] = ['Off', 'BeforeRun', 'AfterRun']
const HSR_UPDATE_CHANNELS: readonly HSRUpdateChannel[] = ['stable', 'beta']
const HSR_M7A_SOURCES: readonly HSRM7ASource[] = ['GitHub', 'MirrorChyan']
const HSR_SRA_SOURCES: readonly HSRSRASource[] = ['AutoSite', 'GitHub', 'MirrorChyan']

export const getDefaultUpdateConfig = (): HSRUpdateConfig => ({
  AutoUpdateMode: 'BeforeRun',
  Channel: 'stable',
  M7ASource: 'GitHub',
  SRASource: 'AutoSite',
  MirrorChyanCDK: '',
})

export const normalizeHSRUpdateConfig = (
  update?: Partial<Record<keyof HSRUpdateConfig, unknown>> | null
): HSRUpdateConfig => {
  const defaults = getDefaultUpdateConfig()
  const pick = <T extends string>(value: unknown, options: readonly T[], fallback: T): T =>
    options.includes(value as T) ? (value as T) : fallback
  return {
    AutoUpdateMode:
      update?.AutoUpdateMode === 'AfterRun'
        ? 'BeforeRun'
        : pick(update?.AutoUpdateMode, HSR_AUTO_UPDATE_MODES, defaults.AutoUpdateMode),
    Channel: pick(update?.Channel, HSR_UPDATE_CHANNELS, defaults.Channel),
    M7ASource: pick(update?.M7ASource, HSR_M7A_SOURCES, defaults.M7ASource),
    SRASource: pick(update?.SRASource, HSR_SRA_SOURCES, defaults.SRASource),
    MirrorChyanCDK: typeof update?.MirrorChyanCDK === 'string' ? update.MirrorChyanCDK : '',
  }
}
