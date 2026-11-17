import type { ScriptType } from '@/types/script'
import generalIcon from '@/assets/AUTO-MAS.ico'
import baahIcon from '@/assets/baah.png'
import bettergiIcon from '@/assets/bettergi.ico'
import hsrIcon from '@/assets/hsr.png'
import { SCRIPT_PLUGIN_METADATA } from '@/plugins/scriptAdapters'
import maaEndIcon from '@/assets/MaaEnd.png'
import m9aIcon from '@/assets/M9A.png'
import okNteIcon from '@/assets/ok-nte.ico'
import okwwIcon from '@/assets/ok-ww.ico'
import srcIcon from '@/assets/SRC.png'
import maafwIcon from '@/assets/maafw.png'
import whimboxIcon from '@/assets/whimbox.png'
import mssIcon from '@/assets/mss.png'
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
  M9A: {
    logo: m9aIcon,
    label: 'M9A',
    typeTagColor: 'cyan',
    routeSuffix: 'm9a',
    routeTitles: {
      script: '编辑M9A脚本',
      userAdd: '添加M9A用户',
      userEdit: '编辑M9A用户',
    },
    createOrder: 5,
    create: {
      titleKey: 'core.scripts.type.M9A',
      descriptionKey: 'core.scripts.create.typeDesc.M9A',
      keywords: ['m9a', '1999', '重返未来'],
      group: 'specialized',
    },
  },
  MAA: SCRIPT_PLUGIN_METADATA.MAA,
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
  MaaFW: {
    logo: maafwIcon,
    label: 'MFW',
    typeTagColor: 'geekblue',
    routeSuffix: 'maafw',
    routeTitles: {
      script: '编辑MFW脚本',
      userAdd: '添加 MFW 用户',
      userEdit: '编辑 MFW 用户',
    },
    createOrder: 1,
    create: {
      titleKey: 'core.scripts.type.MaaFW',
      descriptionKey: 'core.scripts.create.typeDesc.MaaFW',
      keywords: ['maafw', 'maaframework', 'framework', 'mfw', 'interface.json', '通用'],
      group: 'general',
    },
  },
  MSS: {
    logo: mssIcon,
    label: 'MSS',
    typeTagColor: 'orange',
    routeSuffix: 'mss',
    routeTitles: {
      script: '编辑MSS脚本',
      userAdd: '添加MSS用户',
      userEdit: '编辑MSS用户',
    },
    createOrder: 13,
    create: {
      titleKey: 'core.scripts.type.MSS',
      descriptionKey: 'core.scripts.create.typeDesc.MSS',
      keywords: ['mss', 'maastellasora', '星塔旅人', 'stella', 'maaframework'],
      group: 'specialized',
    },
  },
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
  SRC: {
    logo: srcIcon,
    label: 'SRC',
    typeTagColor: 'purple',
    routeSuffix: 'src',
    routeTitles: {
      script: '编辑SRC脚本',
      userAdd: '添加SRC用户',
      userEdit: '编辑SRC用户',
    },
    createOrder: 3,
    create: {
      titleKey: 'core.scripts.type.SRC',
      descriptionKey: 'core.scripts.create.typeDesc.SRC',
      keywords: ['src', '星穹铁道'],
      group: 'specialized',
    },
  },
  Whimbox: {
    logo: whimboxIcon,
    label: 'Whimbox',
    typeTagColor: 'pink',
    routeSuffix: 'whimbox',
    routeTitles: {
      script: '编辑奇想盒脚本',
      userAdd: '添加奇想盒用户',
      userEdit: '编辑奇想盒用户',
    },
    createOrder: 12,
    create: {
      titleKey: 'core.scripts.type.Whimbox',
      descriptionKey: 'core.scripts.create.typeDesc.Whimbox',
      keywords: ['whimbox', '奇想盒', '无限暖暖', 'nikki'],
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
