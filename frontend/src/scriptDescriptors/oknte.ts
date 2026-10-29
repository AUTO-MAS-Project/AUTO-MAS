import { defineScriptDescriptor } from './contracts'
import { okNteIcon } from '@/utils/scriptIconResources'

export const OKNTE_DESCRIPTOR = defineScriptDescriptor({
  type: 'OkNte',
  configType: 'OkNteConfig',
  label: 'OK-NTE',
  logo: okNteIcon,
  card: {
    titleKey: 'core.scripts.type.OkNte',
    descriptionKey: 'core.scripts.create.typeDesc.OkNte',
    keywords: ['oknte', 'ok-nte', '异环', 'ok-script'],
    group: 'specialized',
    order: 50,
  },
  routes: {
    suffix: 'oknte',
    titles: {
      script: '编辑ok-nte脚本',
      userAdd: '添加ok-nte用户',
      userEdit: '编辑ok-nte用户',
    },
    script: () => import('@/views/EditView/Script/OkNteScriptEdit.vue'),
    user: () => import('@/views/EditView/User/OkNteUserEdit.vue'),
  },
})
