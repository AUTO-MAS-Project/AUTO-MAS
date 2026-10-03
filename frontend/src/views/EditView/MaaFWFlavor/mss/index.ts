// MSS（星塔旅人 / MaaStellaSora）特调：只适配部分控制方式，用户可引用计划表、可关掉活动优先。
// 独有区块（脚本页控制方式提示、计划表下拉 + 空队列提示、活动优先开关）都在本目录，按需加载。
import { defineMaaFWLazyComponent } from '@/composables/maafwFlavorTypes'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'
import { defineMaaFWFlavor } from '../defineFlavor'

export const MSS_FLAVOR = defineMaaFWFlavor({
  type: 'MSS',
  scriptConfigType: 'MSSConfig',
  userConfigType: 'MSSUserConfig',
  defaultScriptName: '新 MSS 脚本',
  typeTagLabel: 'MSS',
  typeTagColor: 'orange',
  logo: SCRIPT_LOGOS.MSS,
  docUrl: MAS_DOC_URLS.scripts,
  routes: { suffix: 'mss' },
  create: {
    card: {
      titleKey: 'scripts.type.MSS',
      descriptionKey: 'scripts.create.typeDesc.MSS',
      keywords: ['mss', 'maastellasora', '星塔旅人', 'stella', 'maaframework'],
      group: 'specialized',
      after: null,
    },
  },
  scriptPage: {
    text: {
      titleKey: 'edit.mssFlavorScriptTitle',
      sourceDirectoryKey: 'edit.mssFlavorSourceDirectory',
      sourceHintKey: 'edit.mssFlavorSourceHint',
      sourcePlaceholderKey: 'edit.mssFlavorSourcePlaceholder',
    },
    slots: {
      beforeControl: [defineMaaFWLazyComponent(() => import('./MSSControllerHint.vue'))],
    },
  },
  userPage: {
    text: { queueHintKey: 'edit.mssFlavorQueueHint' },
    slots: {
      beforeTaskQueue: [
        defineMaaFWLazyComponent(() => import('./MSSPlanModeField.vue')),
        defineMaaFWLazyComponent(() => import('./MSSActivityFirstField.vue')),
        defineMaaFWLazyComponent(() => import('./MSSDefenseField.vue')),
      ],
    },
    // 计划表选项的取数逻辑和组件一样按需加载：注册表会被脚本列表、路由等处引入，不带上 API 依赖
    prepare: async () => {
      const { loadMSSPlanComboxItems } = await import('./planModeOptions')
      await loadMSSPlanComboxItems()
    },
  },
})
