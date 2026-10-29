import { defineScriptDescriptor } from './contracts'
import { generalIcon } from '@/utils/scriptIconResources'

export const GENERAL_DESCRIPTOR = defineScriptDescriptor({
  type: 'General',
  configType: 'GeneralConfig',
  label: 'AUTO-MAS',
  logo: generalIcon,
  card: {
    titleKey: 'core.scripts.type.General',
    descriptionKey: 'core.scripts.create.typeDesc.General',
    keywords: ['general', '通用', '自定义'],
    group: 'general',
    order: 0,
  },
  routes: {
    suffix: 'general',
    titles: {
      script: '编辑通用脚本',
      userAdd: '添加通用用户',
      userEdit: '编辑通用用户',
    },
    script: () => import('@/views/EditView/Script/GeneralScriptEdit.vue'),
    user: () => import('@/views/EditView/User/GeneralUserEdit.vue'),
  },
})
