import { defineScriptDescriptor } from './contracts'
import { srcIcon } from '@/utils/scriptIconResources'

export const SRC_DESCRIPTOR = defineScriptDescriptor({
  type: 'SRC',
  configType: 'SrcConfig',
  label: 'SRC',
  logo: srcIcon,
  card: {
    titleKey: 'core.scripts.type.SRC',
    descriptionKey: 'core.scripts.create.typeDesc.SRC',
    keywords: ['src', '星穹铁道'],
    group: 'specialized',
    order: 20,
  },
  routes: {
    suffix: 'src',
    titles: {
      script: '编辑SRC脚本',
      userAdd: '添加SRC用户',
      userEdit: '编辑SRC用户',
    },
    script: () => import('@/views/EditView/Script/SRCScriptEdit.vue'),
    user: () => import('@/views/EditView/User/SRCUserEdit.vue'),
  },
})
