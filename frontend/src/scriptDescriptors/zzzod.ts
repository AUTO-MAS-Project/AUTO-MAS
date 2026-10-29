import { defineScriptDescriptor } from './contracts'
import { zzzOdIcon } from '@/utils/scriptIconResources'

export const ZZZOD_DESCRIPTOR = defineScriptDescriptor({
  type: 'ZzzOd',
  configType: 'ZzzOdConfig',
  label: 'ZZZ-OD',
  logo: zzzOdIcon,
  card: {
    titleKey: 'core.scripts.type.ZzzOd',
    descriptionKey: 'core.scripts.create.typeDesc.ZzzOd',
    keywords: ['zzz-od', 'zzz', '绝区零', 'zenless', '一条龙'],
    group: 'specialized',
    order: 80,
  },
  routes: {
    suffix: 'zzzod',
    titles: {
      script: '编辑ZZZ-OD脚本',
      userAdd: '添加ZZZ-OD用户',
      userEdit: '编辑ZZZ-OD用户',
    },
    script: () => import('@/views/EditView/Script/ZzzOdScriptEdit.vue'),
    user: () => import('@/views/EditView/User/ZzzOdUserEdit.vue'),
  },
})
