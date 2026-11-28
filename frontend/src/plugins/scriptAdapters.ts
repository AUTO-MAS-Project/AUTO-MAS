import type { PluginAdapterBinding } from '@/views/plugins/pluginCenterModel'
import m9aIcon from '@/assets/M9A.png'
import maafwIcon from '@/assets/maafw.png'
import mssIcon from '@/assets/mss.png'
import bettergiIcon from '@/assets/bettergi.ico'
import maaIcon from '@/assets/MAA.png'
import srcIcon from '@/assets/SRC.png'
import whimboxIcon from '@/assets/whimbox.png'
import zzzOdIcon from '@/assets/zzz-od.ico'

/** 插件中心按所属插件对上托管类型、计划表类型与专项图标。 */
export const SCRIPT_PLUGIN_BINDINGS: PluginAdapterBinding[] = [
  { pluginId: 'maafw_adapter', scriptType: 'MaaFW', logo: maafwIcon },
  { pluginId: 'm9a_adapter', scriptType: 'M9A', logo: m9aIcon },
  { pluginId: 'mss_adapter', scriptType: 'MSS', logo: mssIcon, planConfigType: 'MSSPlanConfig' },
  { pluginId: 'bettergi_adapter', scriptType: 'BetterGI', logo: bettergiIcon },
  { pluginId: 'maa_adapter', scriptType: 'MAA', logo: maaIcon, planConfigType: 'MaaPlanConfig' },
  { pluginId: 'src_adapter', scriptType: 'SRC', logo: srcIcon },
  { pluginId: 'whimbox_adapter', scriptType: 'Whimbox', logo: whimboxIcon },
  { pluginId: 'zzzod_adapter', scriptType: 'ZzzOd', logo: zzzOdIcon },
]
