// M9A（重返未来：1999）特调：账号绑成切号任务；启动游戏、切换账号、关闭游戏由后端特调全权控制
// （不能手动加）；脚本页控制方式里多一个「游戏更新」下拉（本目录 M9AGameUpdateField，按需加载）。
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'
import { defineMaaFWLazyComponent } from '@/composables/maafwFlavorTypes'
import { defineMaaFWFlavor } from '../defineFlavor'

export const M9A_FLAVOR = defineMaaFWFlavor({
  type: 'M9A',
  scriptConfigType: 'M9AConfig',
  userConfigType: 'M9AUserConfig',
  defaultScriptName: '新 M9A 脚本',
  typeTagLabel: 'M9A',
  typeTagColor: 'cyan',
  logo: SCRIPT_LOGOS.M9A,
  docUrl: MAS_DOC_URLS.scriptTypes.M9A,
  routes: { suffix: 'm9a' },
  create: {
    card: {
      titleKey: 'scripts.type.M9A',
      descriptionKey: 'scripts.create.typeDesc.M9A',
      keywords: ['m9a', '1999', '重返未来'],
      group: 'specialized',
      after: 'MaaEnd',
    },
  },
  scriptPage: {
    text: {
      titleKey: 'edit.m9aFlavorScriptTitle',
      sourceDirectoryKey: 'edit.m9aFlavorSourceDirectory',
      sourceHintKey: 'edit.m9aFlavorSourceHint',
      sourcePlaceholderKey: 'edit.m9aFlavorSourcePlaceholder',
    },
    // 游戏更新下拉：只有 M9A 的后端特调有游戏客户端更新钩子，与游戏包名并排
    slots: {
      besidePackageName: [defineMaaFWLazyComponent(() => import('./M9AGameUpdateField.vue'))],
    },
  },
  userPage: {
    text: {
      accountPlaceholderKey: 'edit.m9aFlavorAccountPlaceholder',
      accountTooltipKey: 'edit.m9aFlavorAccountTooltip',
      queueHintKey: 'edit.m9aFlavorQueueHint',
    },
    managed: {
      // 与后端 app/task/M9A/managed.py 的 MANAGED_ENTRIES 同一组
      entries: ['StartUp', 'SwitchAccount', 'Close1999'],
      // 与 managed.py 同一判据：官服、有效切号 ≥ 2 才要拆用户
      accountTask: { entry: 'SwitchAccount', resources: ['官服'] },
      warningKey: 'edit.m9aFlavorManagedTaskWarning',
      noticeKey: 'edit.m9aFlavorManagedTaskNotice',
    },
  },
})
