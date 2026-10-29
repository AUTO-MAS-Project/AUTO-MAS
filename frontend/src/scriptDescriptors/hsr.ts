import { defineScriptDescriptor } from './contracts'
import { hsrIcon } from '@/utils/scriptIconResources'

export const HSR_DESCRIPTOR = defineScriptDescriptor({
  type: 'HSR',
  configType: 'HSRConfig',
  label: 'HSR',
  logo: hsrIcon,
  card: {
    titleKey: 'core.scripts.type.HSR',
    descriptionKey: 'core.scripts.create.typeDesc.HSR',
    keywords: ['hsr', '三月七', 'sra'],
    group: 'specialized',
    order: 60,
  },
  routes: {
    suffix: 'hsr',
    titles: {
      script: '编辑HSR脚本',
      userAdd: '添加HSR用户',
      userEdit: '编辑HSR用户',
    },
    script: () => import('@/views/EditView/Script/HSRScriptEdit.vue'),
    user: () => import('@/views/EditView/User/HSRUserEdit.vue'),
  },
})
