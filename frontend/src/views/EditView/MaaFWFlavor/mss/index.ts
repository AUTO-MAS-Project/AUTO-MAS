// MSS（星塔旅人 / MaaStellaSora）特调：只适配桌面端，用户可引用计划表、可关掉活动期自动加入活动任务。
// 脚本页与用户页是 MSS 的专属页面（views/mss/，含控制方式提示、计划表下拉 + 空队列提示、活动自动加入开关），
// 这里只登记整页、文案与计划表选项的预取。
import { defineMaaFWLazyComponent } from '@/composables/maafwFlavorTypes'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'
import { defineMaaFWFlavor } from '../defineFlavor'

const metadata = SCRIPT_METADATA.MSS

export const MSS_FLAVOR = defineMaaFWFlavor({
  type: 'MSS',
  scriptConfigType: 'MSSConfig',
  userConfigType: 'MSSUserConfig',
  defaultScriptName: '新 MSS 托管',
  typeTagLabel: metadata.label,
  typeTagColor: metadata.typeTagColor,
  logo: metadata.logo,
  docUrl: MAS_DOC_URLS.scripts,
  routes: { suffix: metadata.routeSuffix, titles: metadata.routeTitles },
  create: {
    card: {
      ...metadata.create,
      after: null,
    },
  },
  scriptPage: {
    // 标题、目录标签与占位沿用通用 MFW，只在目录问号里点出是 MaaStellaSora 项目
    text: { sourceHintKey: 'core.edit.mssFlavorSourceHint' },
    page: defineMaaFWLazyComponent(() => import('@/views/mss/MSSScriptEdit.vue')),
  },
  userPage: {
    text: { queueHintKey: 'core.edit.mssFlavorQueueHint' },
    page: defineMaaFWLazyComponent(() => import('@/views/mss/MSSUserEdit.vue')),
    // 计划表选项的取数逻辑和页面一样按需加载：注册表会被脚本列表、路由等处引入，不带上 API 依赖
    prepare: async () => {
      const { loadMSSPlanComboxItems } = await import('@/views/mss/planModeOptions')
      await loadMSSPlanComboxItems()
    },
  },
})
