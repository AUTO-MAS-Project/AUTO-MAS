import type { ScriptFrontendAdapter } from '@/plugins/scriptAdapters'
import srcIcon from '@/assets/SRC.png'

export default {
  type: 'SRC',
  pluginId: 'src_adapter',
  metadata: {
    logo: srcIcon,
    label: 'SRC',
    typeTagColor: 'purple',
    routeSuffix: 'src',
    routeTitles: {
      script: '编辑SRC脚本',
      userAdd: '添加SRC用户',
      userEdit: '编辑SRC用户',
    },
    createOrder: 3,
    create: {
      titleKey: 'core.scripts.type.SRC',
      descriptionKey: 'core.scripts.create.typeDesc.SRC',
      keywords: ['src', '星穹铁道'],
      group: 'specialized',
    },
  },
  editors: {
    script: () => import('./SRCScriptEdit.vue'),
    user: () => import('./SRCUserEdit.vue'),
  },
  routes: [],
} satisfies ScriptFrontendAdapter
