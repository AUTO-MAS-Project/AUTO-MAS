import type { ScriptFrontendAdapter } from '@/plugins/scriptAdapters'
import m9aIcon from '@/assets/M9A.png'

/**
 * M9A（重返未来：1999）：由 MaaFW 引擎运行，脚本页与账号页是本目录的专属页面。
 * MaaFW 家族的四条路由由 router/maafwFlavorRoutes.ts 生成，不在这里声明（routes 为空）。
 */
export default {
  pluginId: 'm9a_adapter',
  type: 'M9A' as const,
  metadata: {
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
  editors: {
    script: () => import('./M9AScriptEdit.vue'),
    user: () => import('./M9AUserEdit.vue'),
  },
  routes: [],
  maafw: {
    scriptConfigType: 'M9AConfig',
    userConfigType: 'M9AUserConfig',
    defaultScriptNames: ['新 M9A 托管', '新 M9A 脚本'],
    setupTitle: 'M9A项目引导',
  },
} satisfies ScriptFrontendAdapter
