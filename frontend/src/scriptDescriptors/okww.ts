import { defineScriptDescriptor } from './contracts'
import { okwwIcon } from '@/utils/scriptIconResources'

export const OKWW_DESCRIPTOR = defineScriptDescriptor({
  type: 'Okww',
  configType: 'OkwwConfig',
  label: 'ok-ww',
  logo: okwwIcon,
  card: {
    titleKey: 'core.scripts.type.Okww',
    descriptionKey: 'core.scripts.create.typeDesc.Okww',
    keywords: ['okww', 'ok-ww', 'ok-script'],
    group: 'specialized',
    order: 40,
  },
  routes: {
    suffix: 'okww',
    titles: {
      script: '编辑ok-ww脚本',
      userAdd: '添加ok-ww用户',
      userEdit: '编辑ok-ww用户',
    },
    script: () => import('@/views/EditView/Script/OkwwScriptEdit.vue'),
    user: () => import('@/views/EditView/User/OkwwUserEdit.vue'),
  },
})
