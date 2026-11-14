import { defineAsyncComponent } from 'vue'
import maaIcon from './MAA.png'
import type { ScriptFrontendAdapter } from '@/plugins/scriptAdapters'

/** MAA 编辑、干员养成及计划表入口与插件业务一起维护，保留原有路由身份。 */
export default {
  type: 'MAA',
  metadata: {
    logo: maaIcon,
    label: 'MAA',
    typeTagColor: 'blue',
    routeSuffix: 'maa',
    routeTitles: {
      script: '编辑MAA脚本',
      userAdd: '添加MAA用户',
      userEdit: '编辑MAA用户',
    },
    createOrder: 2,
    create: {
      titleKey: 'core.scripts.type.MAA',
      descriptionKey: 'plugins.maa_adapter.scripts.create.typeDesc.MAA',
      keywords: ['maa', '明日方舟'],
      group: 'specialized',
    },
  },
  editors: {
    script: () => import('./script/MAAScriptEdit.vue'),
    user: () => import('./MAAUserEdit.vue'),
  },
  routes: [
    {
      path: '/scripts/:scriptId/users/:userId/cultivate/maa',
      name: 'MAACultivate',
      component: () => import('./MAAUserEdit.vue'),
      props: { cultivationPage: true },
      meta: { title: 'MAA 干员养成' },
    },
  ],
  plan: {
    configType: 'MaaPlanConfig',
    displayNameKey: 'plugins.maa_adapter.plan.type.maa',
    defaultName: '新 MAA 计划表',
    selectorTag: 'MAA',
    reloadAfterSave: true,
    supportsSimpleView: true,
    tableComponent: defineAsyncComponent(() => import('./MaaPlanTable.vue')),
  },
} satisfies ScriptFrontendAdapter
