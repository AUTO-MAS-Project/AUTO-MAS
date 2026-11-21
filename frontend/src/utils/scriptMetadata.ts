import type { ScriptType } from '@/types/script'
import generalIcon from '@/assets/AUTO-MAS.ico'
import baahIcon from '@/assets/baah.png'
import bettergiIcon from '@/assets/bettergi.ico'
import hsrIcon from '@/assets/hsr.png'
import { SCRIPT_ADAPTER_METADATA } from '@/plugins/scriptAdapters'
import maaEndIcon from '@/assets/MaaEnd.png'
import okNteIcon from '@/assets/ok-nte.ico'
import okwwIcon from '@/assets/ok-ww.ico'
import zzzOdIcon from '@/assets/zzz-od.ico'

export interface ScriptMetadata {
  logo: string
  /** 图片 alt 与页头展示名；列表中的专项文案仍由所属模块决定。 */
  label: string
  typeTagColor: string
  routeSuffix: string
  routeTitles: Record<'script' | 'userAdd' | 'userEdit', string>
  createOrder: number
  create: {
    titleKey: string
    descriptionKey: string
    /** 保留中文搜索别名，不能随界面语言翻译。 */
    keywords: string[]
    group: 'general' | 'specialized'
  }
}

// 这里只放静态资料，不引入 flavor 或页面，供它们共同读取而不形成依赖环。
// 枚举顺序沿用原图标表；新建卡片按 createOrder 排列，MFW 特调仍由 flavor 的 after 插入。
// 已登记为适配条目（plugins/scriptAdapters.ts，含 MaaFW、M9A、MSS）的类型从条目取。
export const SCRIPT_METADATA = {
  BAAH: {
    logo: baahIcon,
    label: 'BAAH',
    typeTagColor: 'magenta',
    routeSuffix: 'baah',
    routeTitles: {
      script: '编辑BAAH脚本',
      userAdd: '添加BAAH用户',
      userEdit: '编辑BAAH用户',
    },
    createOrder: 11,
    create: {
      titleKey: 'core.scripts.type.BAAH',
      descriptionKey: 'core.scripts.create.typeDesc.BAAH',
      keywords: ['baah', '碧蓝档案', '蔚蓝档案', 'bluearchive', '爱丽丝助手'],
      group: 'specialized',
    },
  },
  BetterGI: {
    logo: bettergiIcon,
    label: 'BetterGI',
    typeTagColor: 'gold',
    routeSuffix: 'bettergi',
    routeTitles: {
      script: '编辑BetterGI脚本',
      userAdd: '添加BetterGI用户',
      userEdit: '编辑BetterGI用户',
    },
    createOrder: 9,
    create: {
      titleKey: 'core.scripts.type.BetterGI',
      descriptionKey: 'core.scripts.create.typeDesc.BetterGI',
      keywords: ['bettergi', 'better-gi', '原神', 'genshin'],
      group: 'specialized',
    },
  },
  General: {
    logo: generalIcon,
    label: 'AUTO-MAS',
    typeTagColor: 'green',
    routeSuffix: 'general',
    routeTitles: {
      script: '编辑通用脚本',
      userAdd: '添加通用用户',
      userEdit: '编辑通用用户',
    },
    createOrder: 0,
    create: {
      titleKey: 'core.scripts.type.General',
      descriptionKey: 'core.scripts.create.typeDesc.General',
      keywords: ['general', '通用', '自定义'],
      group: 'general',
    },
  },
  HSR: {
    logo: hsrIcon,
    label: 'HSR',
    typeTagColor: 'purple',
    routeSuffix: 'hsr',
    routeTitles: {
      script: '编辑HSR脚本',
      userAdd: '添加HSR用户',
      userEdit: '编辑HSR用户',
    },
    createOrder: 8,
    create: {
      titleKey: 'core.scripts.type.HSR',
      descriptionKey: 'core.scripts.create.typeDesc.HSR',
      keywords: ['hsr', '三月七', 'sra'],
      group: 'specialized',
    },
  },
  M9A: SCRIPT_ADAPTER_METADATA.M9A,
  MAA: SCRIPT_ADAPTER_METADATA.MAA,
  SRC: SCRIPT_ADAPTER_METADATA.SRC,
  Whimbox: SCRIPT_ADAPTER_METADATA.Whimbox,
  MaaEnd: {
    logo: maaEndIcon,
    label: 'MaaEnd',
    typeTagColor: 'blue',
    routeSuffix: 'maaend',
    routeTitles: {
      script: '编辑MaaEnd脚本',
      userAdd: '添加MaaEnd用户',
      userEdit: '编辑MaaEnd用户',
    },
    createOrder: 4,
    create: {
      titleKey: 'core.scripts.type.MaaEnd',
      descriptionKey: 'core.scripts.create.typeDesc.MaaEnd',
      keywords: ['maaend', 'maaframework', '终末地', 'endfield'],
      group: 'specialized',
    },
  },
  MaaFW: SCRIPT_ADAPTER_METADATA.MaaFW,
  MSS: SCRIPT_ADAPTER_METADATA.MSS,
  OkNte: {
    logo: okNteIcon,
    label: 'OK-NTE',
    typeTagColor: 'blue',
    routeSuffix: 'oknte',
    routeTitles: {
      script: '编辑ok-nte脚本',
      userAdd: '添加ok-nte用户',
      userEdit: '编辑ok-nte用户',
    },
    createOrder: 7,
    create: {
      titleKey: 'core.scripts.type.OkNte',
      descriptionKey: 'core.scripts.create.typeDesc.OkNte',
      keywords: ['oknte', 'ok-nte', '异环', 'ok-script'],
      group: 'specialized',
    },
  },
  Okww: {
    logo: okwwIcon,
    label: 'ok-ww',
    typeTagColor: 'blue',
    routeSuffix: 'okww',
    routeTitles: {
      script: '编辑ok-ww脚本',
      userAdd: '添加ok-ww用户',
      userEdit: '编辑ok-ww用户',
    },
    createOrder: 6,
    create: {
      titleKey: 'core.scripts.type.Okww',
      descriptionKey: 'core.scripts.create.typeDesc.Okww',
      keywords: ['okww', 'ok-ww', 'ok-script'],
      group: 'specialized',
    },
  },
  ZzzOd: {
    logo: zzzOdIcon,
    label: 'ZZZ-OD',
    typeTagColor: 'volcano',
    routeSuffix: 'zzzod',
    routeTitles: {
      script: '编辑ZZZ-OD脚本',
      userAdd: '添加ZZZ-OD用户',
      userEdit: '编辑ZZZ-OD用户',
    },
    createOrder: 10,
    create: {
      titleKey: 'core.scripts.type.ZzzOd',
      descriptionKey: 'core.scripts.create.typeDesc.ZzzOd',
      keywords: ['zzz-od', 'zzz', '绝区零', 'zenless', '一条龙'],
      group: 'specialized',
    },
  },
} satisfies Record<ScriptType, ScriptMetadata>
