import { defineScriptDescriptor } from './contracts'
import { maaIcon } from '@/utils/scriptIconResources'

export const MAA_DESCRIPTOR = defineScriptDescriptor({
  type: 'MAA',
  configType: 'MaaConfig',
  label: 'MAA',
  logo: maaIcon,
  card: {
    titleKey: 'core.scripts.type.MAA',
    descriptionKey: 'core.scripts.create.typeDesc.MAA',
    keywords: ['maa', '明日方舟'],
    group: 'specialized',
    order: 10,
  },
  routes: {
    suffix: 'maa',
    titles: {
      script: '编辑MAA脚本',
      userAdd: '添加MAA用户',
      userEdit: '编辑MAA用户',
    },
    script: () => import('@/views/EditView/Script/MAAScriptEdit.vue'),
    user: () => import('@/views/EditView/User/MAAUserEdit.vue'),
  },
  extraRoutes: [
    {
      path: '/scripts/:scriptId/users/:userId/cultivate/maa',
      name: 'MAACultivate',
      component: () => import('@/views/EditView/User/MAAUserEdit.vue'),
      props: { cultivationPage: true },
      meta: { title: 'MAA 干员养成' },
    },
  ],
})
