import type { Component } from 'vue'
import type { RouteRecordRaw } from 'vue-router'
import type { ScriptMetadata } from '@/utils/scriptMetadata'

type LazyPage = Extract<RouteRecordRaw, { component: unknown }>['component']

/** 编译时收集插件自带的编辑入口；业务组件、计划表和专项路由由所属插件维护。 */
export interface ScriptFrontendAdapter {
  metadata: ScriptMetadata
  type: string
  editors: { script: LazyPage; user: LazyPage }
  routes: RouteRecordRaw[]
  plan: {
    configType: string
    displayNameKey: string
    defaultName: string
    selectorTag: string
    reloadAfterSave: boolean
    supportsSimpleView: boolean
    tableComponent: Component
  }
}

const modules = import.meta.glob<{ default: ScriptFrontendAdapter }>(
  '../../../plugins/*/frontend/entry.ts',
  { eager: true }
)
const adapters = Object.values(modules).map(module => module.default)

export const SCRIPT_PLUGIN_EDITORS = Object.fromEntries(
  adapters.map(adapter => [adapter.type, adapter.editors])
)
export const SCRIPT_PLUGIN_ROUTES = adapters.flatMap(adapter => adapter.routes)
export const SCRIPT_PLUGIN_PLANS = Object.fromEntries(
  adapters.map(adapter => [
    adapter.plan.configType,
    { ...adapter.plan, createType: adapter.plan.configType },
  ])
)

export const SCRIPT_PLUGIN_METADATA = Object.fromEntries(
  adapters.map(adapter => [adapter.type, adapter.metadata])
)
