import { defineScriptDescriptor } from './contracts'
import { whimboxIcon } from '@/utils/scriptIconResources'

export const WHIMBOX_DESCRIPTOR = defineScriptDescriptor({
  type: 'Whimbox',
  configType: 'WhimboxConfig',
  label: 'Whimbox',
  logo: whimboxIcon,
  card: {
    titleKey: 'core.scripts.type.Whimbox',
    descriptionKey: 'core.scripts.create.typeDesc.Whimbox',
    keywords: ['whimbox', '奇想盒', '无限暖暖', 'nikki'],
    group: 'specialized',
    order: 100,
  },
  routes: {
    suffix: 'whimbox',
    titles: {
      script: '编辑奇想盒脚本',
      userAdd: '添加奇想盒用户',
      userEdit: '编辑奇想盒用户',
    },
    script: () => import('@/views/EditView/Script/WhimboxScriptEdit.vue'),
    user: () => import('@/views/EditView/User/WhimboxUserEdit.vue'),
  },
})
