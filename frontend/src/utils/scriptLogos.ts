import type { ScriptType } from '@/types/script'
import generalIcon from '@/assets/AUTO-MAS.ico'
import hsrIcon from '@/assets/hsr.png'
import maaIcon from '@/assets/MAA.png'
import maaEndIcon from '@/assets/MaaEnd.png'
import m9aIcon from '@/assets/M9A.png'
import okNteIcon from '@/assets/ok-nte.ico'
import okwwIcon from '@/assets/ok-ww.ico'
import srcIcon from '@/assets/SRC.png'
import maafwIcon from '@/assets/maafw.png'

/** 脚本类型 → 图标资源，Vite 处理后的 URL */
export const SCRIPT_LOGOS: Record<ScriptType, string> = {
  General: generalIcon,
  HSR: hsrIcon,
  M9A: m9aIcon,
  MAA: maaIcon,
  MaaEnd: maaEndIcon,
  MaaFW: maafwIcon,
  OkNte: okNteIcon,
  Okww: okwwIcon,
  SRC: srcIcon,
}

/** 脚本类型 → 展示名，用于图片 alt 与标签文案 */
export const SCRIPT_LABELS: Record<ScriptType, string> = {
  General: 'AUTO-MAS',
  HSR: 'HSR',
  M9A: 'M9A',
  MAA: 'MAA',
  MaaEnd: 'MaaEnd',
  MaaFW: 'MFW',
  OkNte: 'OK-NTE',
  Okww: 'ok-ww',
  SRC: 'SRC',
}
