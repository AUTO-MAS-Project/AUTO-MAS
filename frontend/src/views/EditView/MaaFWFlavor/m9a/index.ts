// M9A（重返未来：1999）特调：差别只在文案与身份——账号绑成切号任务；启动游戏、切换账号、
// 关闭游戏由后端特调全权控制（不能手动加），脚本页多一个「游戏更新」下拉。没有独有区块。
import type { MaaFWFlavor } from '@/composables/maafwFlavorTypes'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'

export const M9A_FLAVOR: MaaFWFlavor = {
  type: 'M9A',
  scriptConfigType: 'M9AConfig',
  userConfigType: 'M9AUserConfig',
  routeSuffix: 'm9a',
  defaultScriptName: '新 M9A 脚本',
  typeTagLabel: 'M9A',
  typeTagColor: 'cyan',
  logo: SCRIPT_LOGOS.M9A,
  docUrl: MAS_DOC_URLS.scriptTypes.M9A,
  createOption: {
    titleKey: 'scripts.type.M9A',
    descriptionKey: 'scripts.create.typeDesc.M9A',
    keywords: ['m9a', '1999', '重返未来'],
    group: 'specialized',
    after: 'MaaEnd',
  },
  scriptTitleKey: 'edit.m9aFlavorScriptTitle',
  sourceDirectoryKey: 'edit.m9aFlavorSourceDirectory',
  sourceHintKey: 'edit.m9aFlavorSourceHint',
  sourcePlaceholderKey: 'edit.m9aFlavorSourcePlaceholder',
  controllerHintKey: null,
  accountPlaceholderKey: 'edit.m9aFlavorAccountPlaceholder',
  accountTooltipKey: 'edit.m9aFlavorAccountTooltip',
  queueHintKey: 'edit.m9aFlavorQueueHint',
  gameUpdateHintKey: 'edit.m9aFlavorGameUpdateHint',
  // 与后端 app/task/M9A/managed.py 的 MANAGED_ENTRIES 同一组
  managedTaskEntries: ['StartUp', 'SwitchAccount', 'Close1999'],
  managedTaskWarningKey: 'edit.m9aFlavorManagedTaskWarning',
  slots: {},
  prepareUserPage: null,
}
