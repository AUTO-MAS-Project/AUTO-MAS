import type { Component } from 'vue'
import type { RouteRecordRaw } from 'vue-router'
import type { ScriptType } from '@/types/script'
import type { ScriptMetadata } from '@/utils/scriptMetadata'
import type { PluginAdapterBinding } from '@/views/plugins/pluginCenterModel'
import bettergi from '@/views/bettergi/entry'
import maa from '@/views/maa/entry'
import m9a from '@/views/m9a/entry'
import maafw from '@/views/maafw/entry'
import mss from '@/views/mss/entry'
import src from '@/views/src/entry'
import whimbox from '@/views/whimbox/entry'

type LazyPage = Extract<RouteRecordRaw, { component: unknown }>['component']

/**
 * MaaFW 家族（通用 MFW 与 M9A、MSS）的标记：由 MaaFW 引擎运行，页面走 MFW 自己的四条路由
 * （编辑 / 引导 / 加用户 / 编辑用户），不按普通专项生成路由；插件中心照常统计。
 */
export interface MaaFWAdapterProfile {
  /** 后端脚本配置类名（脚本索引里的 type） */
  scriptConfigType: string
  /** 后端用户配置类名（用户索引里的 type） */
  userConfigType: string
  /**
   * 后端新建托管时给的默认名：[当前默认名, 旧默认名]（与后端配置类 Info.Name 的默认值一致，
   * 改一边要改另一边）。还是其中之一时，导入后自动改成项目名
   */
  defaultScriptNames: readonly string[]
  /** 引导路由的标题（route.meta.title） */
  setupTitle: string
  /** 头像用项目自己的图标（interface 顶层 icon），取不到回退到 logo；只有通用 MFW 为 true */
  usesProjectIcon?: boolean
}

/** 暂随主程序编译的专项页面声明，动态页面上线后移交对应插件。 */
export interface ScriptFrontendAdapter {
  /** 所属插件标识（plugin_name）；注册表补上「提供的类型」前，插件中心据此统计托管与取图标。 */
  pluginId: string
  metadata: ScriptMetadata
  type: string
  editors: { script: LazyPage; user: LazyPage }
  routes: RouteRecordRaw[]
  /** MaaFW 家族的标记；普通专项不写 */
  maafw?: MaaFWAdapterProfile
  plan?: {
    configType: string
    /** 新建计划表时的类型；不写与 configType 相同 */
    createType?: string
    displayNameKey: string
    defaultName: string
    selectorTag: string
    reloadAfterSave: boolean
    supportsSimpleView: boolean
    tableComponent: Component
  }
}

/** 普通专项：按 editors 生成路由，进插件中心统计 */
const pluginAdapters: ScriptFrontendAdapter[] = [maa, whimbox, src, bettergi]

/**
 * MaaFW 家族，顺序固定为 MaaFW、M9A、MSS。路由名与普通专项同形（`${type}ScriptEdit` 等），
 * 所以不能进 SCRIPT_PLUGIN_EDITORS；三者都是插件，进 SCRIPT_PLUGIN_BINDINGS。
 */
const maafwAdapters = [maafw, m9a, mss] satisfies ScriptFrontendAdapter[]

/** 由 MaaFW 引擎运行的脚本类型：从 MaaFW 家族的适配条目推出（新增一类在 maafwAdapters 里登记） */
export type MaaFWFamilyType = Extract<ScriptType, (typeof maafwAdapters)[number]['type']>

const toPlanEntries = (adapters: readonly ScriptFrontendAdapter[]) =>
  Object.fromEntries(
    adapters.flatMap(adapter =>
      adapter.plan
        ? [
            [
              adapter.plan.configType,
              { ...adapter.plan, createType: adapter.plan.createType ?? adapter.plan.configType },
            ],
          ]
        : []
    )
  )

export const SCRIPT_PLUGIN_EDITORS = Object.fromEntries(
  pluginAdapters.map(adapter => [adapter.type, adapter.editors])
)
export const SCRIPT_PLUGIN_ROUTES = pluginAdapters.flatMap(adapter => adapter.routes)
export const SCRIPT_PLUGIN_PLANS = toPlanEntries(pluginAdapters)

/** MaaFW 家族的计划表类型（MSS）；计划表注册表把它们排在最后 */
export const SCRIPT_BUILTIN_PLANS = toPlanEntries(maafwAdapters)

/** 全部适配条目的静态资料（utils/scriptMetadata.ts 引用） */
export const SCRIPT_ADAPTER_METADATA = Object.fromEntries(
  [...pluginAdapters, ...maafwAdapters].map(adapter => [adapter.type, adapter.metadata])
)

/** MaaFW 家族的适配条目，顺序固定为 MaaFW、M9A、MSS */
export const MAAFW_FAMILY_ADAPTERS: readonly ScriptFrontendAdapter[] = maafwAdapters

/** 插件中心按所属插件对上托管类型、计划表类型与专项图标。 */
export const SCRIPT_PLUGIN_BINDINGS: PluginAdapterBinding[] = [
  ...pluginAdapters,
  ...MAAFW_FAMILY_ADAPTERS,
].map(adapter => ({
  pluginId: adapter.pluginId,
  scriptType: adapter.type,
  logo: adapter.metadata.logo,
  planConfigType: adapter.plan?.configType,
}))
