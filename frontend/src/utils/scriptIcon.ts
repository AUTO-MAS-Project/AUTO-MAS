import type { ScriptType } from '@/types/script'
import generalIcon from '@/assets/AUTO-MAS.ico'
import maafwIcon from '@/assets/maafw.png'
import hsrIcon from '@/assets/hsr.png'
import maaIcon from '@/assets/MAA.png'
import maaEndIcon from '@/assets/MaaEnd.png'
import m9aIcon from '@/assets/M9A.png'
import okNteIcon from '@/assets/ok-nte.ico'
import okwwIcon from '@/assets/ok-ww.ico'
import srcIcon from '@/assets/SRC.png'

const SCRIPT_ICON_BY_TYPE: Record<ScriptType, string> = {
  MAA: maaIcon,
  General: generalIcon,
  Okww: okwwIcon,
  OkNte: okNteIcon,
  SRC: srcIcon,
  MaaEnd: maaEndIcon,
  M9A: m9aIcon,
  MaaFW: maafwIcon,
  HSR: hsrIcon,
}

/** Return the host-owned icon for current and legacy persisted script types. */
export const getScriptIcon = (value: unknown, preferredIcon?: string | null): string => {
  if (preferredIcon && preferredIcon.trim()) return preferredIcon
  const normalized = String(value || '')
  if (normalized === 'MaaFWConfig' || normalized === 'MaaFWManaged') {
    return maafwIcon
  }
  if (normalized in SCRIPT_ICON_BY_TYPE) {
    return SCRIPT_ICON_BY_TYPE[normalized as ScriptType]
  }
  return generalIcon
}

export const handleScriptIconError = (event: Event, value: unknown): void => {
  const image = event.currentTarget as HTMLImageElement | null
  if (!image || image.dataset.scriptIconFallbackApplied === 'true') return
  image.dataset.scriptIconFallbackApplied = 'true'
  image.src = getScriptIcon(value)
}

export const maafwScriptIcon = maafwIcon
