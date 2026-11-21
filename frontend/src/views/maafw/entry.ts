import type { ScriptFrontendAdapter } from '@/plugins/scriptAdapters'
import maafwIcon from '@/assets/maafw.png'

/**
 * 通用 MFW：任何带 interface.json 的项目都由它运行，页面只按 interface 渲染。
 * MaaFW 家族的四条路由由 router/maafwRoutes.ts 生成，不在这里声明（routes 为空）。
 */
export default {
  // MFW 不是插件：pluginId 只占位，不进插件中心统计（见 scriptAdapters.ts）
  pluginId: 'maafw_adapter',
  type: 'MaaFW' as const,
  metadata: {
    logo: maafwIcon,
    label: 'MFW',
    typeTagColor: 'geekblue',
    routeSuffix: 'maafw',
    // 沿用改成按注册表生成前手写的标题，一字不差（「添加 MFW 用户」带空格）
    routeTitles: {
      script: '编辑MFW脚本',
      userAdd: '添加 MFW 用户',
      userEdit: '编辑 MFW 用户',
    },
    createOrder: 1,
    create: {
      // MaaFW 是通用引擎，不是专项：任何带 interface.json 的项目都由它运行，和「通用脚本」并列。
      titleKey: 'core.scripts.type.MaaFW',
      descriptionKey: 'core.scripts.create.typeDesc.MaaFW',
      keywords: ['maafw', 'maaframework', 'framework', 'mfw', 'interface.json', '通用'],
      group: 'general',
    },
  },
  editors: {
    script: () => import('@/views/EditView/Script/MaaFWScriptEdit.vue'),
    user: () => import('@/views/EditView/User/MaaFWUserEdit.vue'),
  },
  routes: [],
  maafw: {
    scriptConfigType: 'MaaFWConfig',
    userConfigType: 'MaaFWUserConfig',
    defaultScriptNames: ['新 MFW 托管', '新 MFW 脚本'],
    setupTitle: 'MaaFramework项目引导',
    usesProjectIcon: true,
  },
} satisfies ScriptFrontendAdapter
