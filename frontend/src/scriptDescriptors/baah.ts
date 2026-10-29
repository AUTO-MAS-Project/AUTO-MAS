import { defineScriptDescriptor } from './contracts'
import { baahIcon } from '@/utils/scriptIconResources'

export const BAAH_DESCRIPTOR = defineScriptDescriptor({
  type: 'BAAH',
  configType: 'BAAHConfig',
  label: 'BAAH',
  logo: baahIcon,
  card: {
    titleKey: 'core.scripts.type.BAAH',
    descriptionKey: 'core.scripts.create.typeDesc.BAAH',
    keywords: ['baah', '碧蓝档案', '蔚蓝档案', 'bluearchive', '爱丽丝助手'],
    group: 'specialized',
    order: 90,
  },
  routes: {
    suffix: 'baah',
    titles: {
      script: '编辑BAAH脚本',
      userAdd: '添加BAAH用户',
      userEdit: '编辑BAAH用户',
    },
    script: () => import('@/views/EditView/Script/BAAHScriptEdit.vue'),
    user: () => import('@/views/EditView/User/BAAHUserEdit.vue'),
  },
})
