// MSS（星塔旅人 / MaaStellaSora）特调：只适配部分控制方式，用户可引用计划表、可关掉活动优先。
// 独有区块（计划表下拉 + 空队列提示、活动优先开关）都在本目录，按需加载。
import { defineMaaFWFlavorSlotComponent, type MaaFWFlavor } from '@/composables/maafwFlavorTypes'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'

export const MSS_FLAVOR: MaaFWFlavor = {
  type: 'MSS',
  scriptConfigType: 'MSSConfig',
  userConfigType: 'MSSUserConfig',
  routeSuffix: 'mss',
  defaultScriptName: '新 MSS 脚本',
  typeTagLabel: 'MSS',
  typeTagColor: 'orange',
  logo: SCRIPT_LOGOS.MSS,
  docUrl: MAS_DOC_URLS.scripts,
  createOption: {
    titleKey: 'scripts.type.MSS',
    descriptionKey: 'scripts.create.typeDesc.MSS',
    keywords: ['mss', 'maastellasora', '星塔旅人', 'stella', 'maaframework'],
    group: 'specialized',
    after: null,
  },
  scriptTitleKey: 'edit.mssFlavorScriptTitle',
  sourceDirectoryKey: 'edit.mssFlavorSourceDirectory',
  sourceHintKey: 'edit.mssFlavorSourceHint',
  sourcePlaceholderKey: 'edit.mssFlavorSourcePlaceholder',
  controllerHintKey: 'edit.mssFlavorControllerHint',
  accountPlaceholderKey: 'edit.localNoteOnly',
  accountTooltipKey: 'edit.maafwAccountRecordTooltip',
  queueHintKey: 'edit.mssFlavorQueueHint',
  gameUpdateHintKey: null,
  slots: {
    userBeforeTaskQueue: [
      defineMaaFWFlavorSlotComponent(() => import('./MSSPlanModeField.vue')),
      defineMaaFWFlavorSlotComponent(() => import('./MSSActivityFirstField.vue')),
    ],
  },
  // 计划表选项的取数逻辑和组件一样按需加载：注册表会被脚本列表、路由等处引入，不带上 API 依赖
  prepareUserPage: async () => {
    const { loadMSSPlanComboxItems } = await import('./planModeOptions')
    await loadMSSPlanComboxItems()
  },
}
