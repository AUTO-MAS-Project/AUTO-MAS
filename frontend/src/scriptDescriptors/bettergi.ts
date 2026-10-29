import { defineScriptDescriptor } from './contracts'
import { bettergiIcon } from '@/utils/scriptIconResources'

export const BETTERGI_DESCRIPTOR = defineScriptDescriptor({
  type: 'BetterGI',
  configType: 'BetterGIConfig',
  label: 'BetterGI',
  logo: bettergiIcon,
  card: {
    titleKey: 'core.scripts.type.BetterGI',
    descriptionKey: 'core.scripts.create.typeDesc.BetterGI',
    keywords: ['bettergi', 'better-gi', '原神', 'genshin'],
    group: 'specialized',
    order: 70,
  },
  routes: {
    suffix: 'bettergi',
    titles: {
      script: '编辑BetterGI脚本',
      userAdd: '添加BetterGI用户',
      userEdit: '编辑BetterGI用户',
    },
    script: () => import('@/views/EditView/Script/BetterGIScriptEdit.vue'),
    user: () => import('@/views/EditView/User/BetterGIUserEdit.vue'),
  },
})
