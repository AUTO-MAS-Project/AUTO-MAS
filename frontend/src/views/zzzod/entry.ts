import zzzOdIcon from '@/assets/zzz-od.ico'
import type { ScriptFrontendAdapter } from '@/plugins/scriptAdapters'

/** 绝区零一条龙页面随主程序编译，使用插件提供的专项接口。 */
export default {
  pluginId: 'zzzod_adapter',
  type: 'ZzzOd',
  metadata: {
    logo: zzzOdIcon,
    label: 'ZZZ-OD',
    typeTagColor: 'volcano',
    routeSuffix: 'zzzod',
    routeTitles: {
      script: '编辑ZZZ-OD脚本',
      userAdd: '添加ZZZ-OD用户',
      userEdit: '编辑ZZZ-OD用户',
    },
    createOrder: 10,
    create: {
      titleKey: 'core.scripts.type.ZzzOd',
      descriptionKey: 'core.scripts.create.typeDesc.ZzzOd',
      keywords: ['zzz-od', 'zzz', '绝区零', 'zenless', '一条龙'],
      group: 'specialized',
    },
  },
  editors: {
    script: () => import('@/views/EditView/Script/ZzzOdScriptEdit.vue'),
    user: () => import('@/views/EditView/User/ZzzOdUserEdit.vue'),
  },
  routes: [],
} satisfies ScriptFrontendAdapter
