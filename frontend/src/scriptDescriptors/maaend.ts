import { defineScriptDescriptor } from './contracts'
import { maaEndIcon } from '@/utils/scriptIconResources'

export const MAAEND_DESCRIPTOR = defineScriptDescriptor({
  type: 'MaaEnd',
  configType: 'MaaEndConfig',
  label: 'MaaEnd',
  logo: maaEndIcon,
  card: {
    titleKey: 'core.scripts.type.MaaEnd',
    descriptionKey: 'core.scripts.create.typeDesc.MaaEnd',
    keywords: ['maaend', 'maaframework', '终末地', 'endfield'],
    group: 'specialized',
    order: 30,
  },
  routes: {
    suffix: 'maaend',
    titles: {
      script: '编辑MaaEnd脚本',
      userAdd: '添加MaaEnd用户',
      userEdit: '编辑MaaEnd用户',
    },
    script: () => import('@/views/EditView/Script/MaaEndScriptEdit.vue'),
    user: () => import('@/views/EditView/User/MaaEndUserEdit.vue'),
  },
})
