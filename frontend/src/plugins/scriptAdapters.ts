import type { Component } from 'vue'
import type { RouteRecordRaw } from 'vue-router'
import type { ScriptMetadata } from '@/utils/scriptMetadata'
import type { PluginAdapterBinding } from '@/views/plugins/pluginCenterModel'
import maa from '@/views/maa/entry'
import src from '@/views/src/entry'
import whimbox from '@/views/whimbox/entry'

type LazyPage = Extract<RouteRecordRaw, { component: unknown }>['component']

/** 暂随主程序编译的专项页面声明，动态页面上线后移交对应插件。 */
export interface ScriptFrontendAdapter {
  /** 所属插件标识（plugin_name）；注册表补上「提供的类型」前，插件中心据此统计托管与取图标。 */
  pluginId: string
  metadata: ScriptMetadata
  type: string
  editors: { script: LazyPage; user: LazyPage }
  routes: RouteRecordRaw[]
  plan?: {
    configType: string
    displayNameKey: string
    defaultName: string
    selectorTag: string
    reloadAfterSave: boolean
    supportsSimpleView: boolean
    tableComponent: Component
  }
}

const adapters: ScriptFrontendAdapter[] = [maa, whimbox, src]

export const SCRIPT_PLUGIN_EDITORS = Object.fromEntries(
  adapters.map(adapter => [adapter.type, adapter.editors])
)
export const SCRIPT_PLUGIN_ROUTES = adapters.flatMap(adapter => adapter.routes)
export const SCRIPT_PLUGIN_PLANS = Object.fromEntries(
  adapters.flatMap(adapter =>
    adapter.plan
      ? [[adapter.plan.configType, { ...adapter.plan, createType: adapter.plan.configType }]]
      : []
  )
)

export const SCRIPT_PLUGIN_METADATA = Object.fromEntries(
  adapters.map(adapter => [adapter.type, adapter.metadata])
)

/** 插件中心按所属插件对上托管类型、计划表类型与专项图标。 */
export const SCRIPT_PLUGIN_BINDINGS: PluginAdapterBinding[] = adapters.map(adapter => ({
  pluginId: adapter.pluginId,
  scriptType: adapter.type,
  logo: adapter.metadata.logo,
  planConfigType: adapter.plan?.configType,
}))
