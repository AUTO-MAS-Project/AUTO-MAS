/** 主页中心图标（星核）按压音效：两套内置音效，或用户自己导入的音频文件 */
export type PressSoundPreset = 'duck' | 'fx1' | 'custom'

/** 一次按压的两个阶段：按下与松开 */
export type PressSoundPhase = 'press' | 'release'

/** 内置音效组与它们在 public/sounds/ 下的文件；顺序就是设置页下拉的顺序 */
export const BUILTIN_PRESS_SOUNDS: ReadonlyArray<{
  value: Exclude<PressSoundPreset, 'custom'>
  press: string
  release: string
}> = [
  { value: 'duck', press: 'press-duck.mp3', release: 'press-duck-release.mp3' },
  { value: 'fx1', press: 'press-fx1.mp3', release: 'press-fx1-release.mp3' },
]

/** 新增的设置项不打扰旧用户，默认不响 */
export const DEFAULT_PRESS_SOUND_ENABLED = false
export const DEFAULT_PRESS_SOUND_PRESET: PressSoundPreset = 'duck'
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
