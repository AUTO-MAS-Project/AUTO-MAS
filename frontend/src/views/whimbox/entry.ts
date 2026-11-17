import type { ScriptFrontendAdapter } from '@/plugins/scriptAdapters'
import whimboxIcon from './whimbox.png'

export default {
  type: 'Whimbox',
  metadata: {
    logo: whimboxIcon,
    label: 'Whimbox',
    typeTagColor: 'pink',
    routeSuffix: 'whimbox',
    routeTitles: {
      script: '编辑奇想盒脚本',
      userAdd: '添加奇想盒用户',
      userEdit: '编辑奇想盒用户',
    },
    createOrder: 12,
    create: {
      titleKey: 'core.scripts.type.Whimbox',
      descriptionKey: 'core.scripts.create.typeDesc.Whimbox',
      keywords: ['whimbox', '奇想盒', '无限暖暖', 'nikki'],
      group: 'specialized',
    },
  },
  editors: {
    script: () => import('./script/WhimboxScriptEdit.vue'),
    user: () => import('./WhimboxUserEdit.vue'),
  },
  routes: [],
} satisfies ScriptFrontendAdapter
