// M9A（重返未来：1999）特调：账号绑成切号任务；启动游戏、切换账号、关闭游戏由后端特调全权控制
// （不能手动加）。脚本页与用户页是 M9A 的专属页面（views/m9a/），这里只登记整页、文案与受管任务。
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'
import { defineMaaFWLazyComponent } from '@/composables/maafwFlavorTypes'
import { defineMaaFWFlavor } from '../defineFlavor'

const metadata = SCRIPT_METADATA.M9A

export const M9A_FLAVOR = defineMaaFWFlavor({
  type: 'M9A',
  scriptConfigType: 'M9AConfig',
  userConfigType: 'M9AUserConfig',
  defaultScriptName: '新 M9A 托管',
  typeTagLabel: metadata.label,
  typeTagColor: metadata.typeTagColor,
  logo: metadata.logo,
  docUrl: MAS_DOC_URLS.scriptTypes.M9A,
  routes: { suffix: metadata.routeSuffix, titles: metadata.routeTitles },
  create: {
    card: {
      ...metadata.create,
      after: 'MaaEnd',
    },
  },
  scriptPage: {
    // 标题、目录标签与占位沿用通用 MFW，只在目录问号里点出是 M9A 项目
    text: { sourceHintKey: 'core.edit.m9aFlavorSourceHint' },
    // 专属脚本页：控制方式里多「登录方式」「游戏更新」两格（只有 M9A 的后端特调有这两个钩子）
    page: defineMaaFWLazyComponent(() => import('@/views/m9a/M9AScriptEdit.vue')),
  },
  userPage: {
    page: defineMaaFWLazyComponent(() => import('@/views/m9a/M9AUserEdit.vue')),
    text: {
      accountPlaceholderKey: 'core.edit.m9aFlavorAccountPlaceholder',
      accountTooltipKey: 'core.edit.m9aFlavorAccountTooltip',
    },
    managed: {
      // 与后端 app/task/M9A/managed.py 的 MANAGED_ENTRIES 同一组
      entries: ['StartUp', 'SwitchAccount', 'Close1999'],
      // 与 managed.py 同一判据：官服、有效切号 ≥ 2 才要拆用户（MAS 登录模式下切号不下发，由用户页按配置关掉）
      accountTask: { entry: 'SwitchAccount', resources: ['官服'] },
      warningKey: 'core.edit.m9aFlavorManagedTaskWarning',
      noticeKey: 'core.edit.m9aFlavorManagedTaskNotice',
    },
  },
})
