import { defineAsyncComponent } from 'vue'
import type { ScriptFrontendAdapter } from '@/plugins/scriptAdapters'
import mssIcon from '@/assets/mss.png'

/**
 * MSS（星塔旅人 / MaaStellaSora）：由 MaaFW 引擎运行，脚本页、账号页与计划表页是本目录的专属页面。
 * MaaFW 家族的四条路由由 router/maafwRoutes.ts 生成，不在这里声明（routes 为空）。
 */
export default {
  pluginId: 'mss_adapter',
  type: 'MSS' as const,
  metadata: {
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
  editors: {
    script: () => import('./MSSScriptEdit.vue'),
    user: () => import('./MSSUserEdit.vue'),
  },
  routes: [],
  maafw: {
    scriptConfigType: 'MSSConfig',
    userConfigType: 'MSSUserConfig',
    defaultScriptNames: ['新 MSS 托管', '新 MSS 脚本'],
    setupTitle: 'MSS项目引导',
  },
  plan: {
    configType: 'MSSPlanConfig',
    createType: 'MSSPlan',
    displayNameKey: 'core.plan.type.mss',
    // defaultName 会写进计划名，并被 plan/index.vue 拿来判断“还是默认名”，保持中文
    defaultName: '新 MSS 计划表',
    selectorTag: 'MSS',
    reloadAfterSave: false,
    supportsSimpleView: true,
    tableComponent: defineAsyncComponent(() => import('./MSSPlanTable.vue')),
  },
} satisfies ScriptFrontendAdapter
