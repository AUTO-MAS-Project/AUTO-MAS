/** 主页中心图标（星核）按压音效：四套内置合成音，或用户自己导入的音频文件 */
export type PressSoundPreset = 'soft' | 'crisp' | 'pop' | 'tick' | 'custom'

/** 内置音效与它们在 public/sounds/ 下的文件；顺序就是设置页下拉的顺序 */
export const BUILTIN_PRESS_SOUNDS: ReadonlyArray<{
  value: Exclude<PressSoundPreset, 'custom'>
  file: string
}> = [
  { value: 'soft', file: 'press-soft.wav' },
  { value: 'crisp', file: 'press-crisp.wav' },
  { value: 'pop', file: 'press-pop.wav' },
  { value: 'tick', file: 'press-tick.wav' },
]

/** 新增的设置项不打扰旧用户，默认不响 */
export const DEFAULT_PRESS_SOUND_ENABLED = false
export const DEFAULT_PRESS_SOUND_PRESET: PressSoundPreset = 'soft'
export const DEFAULT_PRESS_SOUND_VOLUME = 0.6

/** 用户导入的音频上限：够放一段短音效，又不至于把配置撑爆 */
export const MAX_PRESS_SOUND_BYTES = 1024 * 1024

export const isBuiltinPressSound = (
  preset: PressSoundPreset
): preset is Exclude<PressSoundPreset, 'custom'> => preset !== 'custom'

export const normalizePressSoundPreset = (value: unknown): PressSoundPreset => {
  if (value === 'custom') {
    return 'custom'
  }

  const builtin = BUILTIN_PRESS_SOUNDS.find(item => item.value === value)
  return builtin ? builtin.value : DEFAULT_PRESS_SOUND_PRESET
}

export const normalizePressSoundVolume = (value: unknown): number => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return DEFAULT_PRESS_SOUND_VOLUME
  }

  return Math.min(1, Math.max(0, parsed))
}
