import type { ScriptFrontendAdapter } from '@/plugins/scriptAdapters'
import bettergiIcon from '@/assets/bettergi.ico'

export default {
  type: 'BetterGI',
  pluginId: 'bettergi_adapter',
  metadata: {
    logo: bettergiIcon,
    label: 'BetterGI',
    typeTagColor: 'gold',
    routeSuffix: 'bettergi',
    routeTitles: {
      script: '编辑BetterGI脚本',
      userAdd: '添加BetterGI用户',
      userEdit: '编辑BetterGI用户',
    },
    createOrder: 9,
    create: {
      titleKey: 'core.scripts.type.BetterGI',
      descriptionKey: 'core.scripts.create.typeDesc.BetterGI',
      keywords: ['bettergi', 'better-gi', '原神', 'genshin'],
      group: 'specialized',
    },
  },
  editors: {
    script: () => import('@/views/EditView/Script/BetterGIScriptEdit.vue'),
    user: () => import('@/views/EditView/User/BetterGIUserEdit.vue'),
  },
  routes: [],
} satisfies ScriptFrontendAdapter
