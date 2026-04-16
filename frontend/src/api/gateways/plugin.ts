import {
  addPluginInstanceApiPluginsAddPost,
  deletePluginInstanceApiPluginsDeletePost,
  getPluginsApiPluginsGetPost,
  installPluginPackageApiPluginsInstallPackagePost,
  reloadPluginByNameApiPluginsReloadPluginPost,
  reloadPluginInstanceApiPluginsReloadInstancePost,
  reloadPluginsApiPluginsReloadPost,
  uninstallPluginPackageApiPluginsUninstallPackagePost,
  updatePluginInstanceApiPluginsUpdatePost,
} from '../generated/sdk.gen'
import type {
  OutBase,
  PluginAddIn,
  PluginDeleteIn,
  PluginInstanceModel as GeneratedPluginInstance,
  PluginMutationOut as GeneratedPluginMutationOut,
  PluginPackageIn,
  PluginReloadInstanceIn,
  PluginReloadPluginIn,
  PluginRuntimeStateModel as GeneratedPluginRuntimeState,
  PluginUpdateIn,
  PluginsGetOut as GeneratedPluginGetOut,
} from '../generated/types.gen'

export type PluginInstance = GeneratedPluginInstance
export type PluginGetOut = GeneratedPluginGetOut
export type PluginRuntimeState = GeneratedPluginRuntimeState
export type PluginMutationOut = GeneratedPluginMutationOut

export interface PluginSchemaField {
  type: string
  format?: string
  default?: unknown
  required?: boolean
  description?: string
  item_type?: string
  [key: string]: unknown
}

export const pluginApi = {
  get() {
    return getPluginsApiPluginsGetPost()
  },

  add(payload: PluginAddIn) {
    return addPluginInstanceApiPluginsAddPost({ body: payload })
  },

  update(payload: PluginUpdateIn) {
    return updatePluginInstanceApiPluginsUpdatePost({ body: payload })
  },

  remove(payload: PluginDeleteIn) {
    return deletePluginInstanceApiPluginsDeletePost({ body: payload }) as Promise<OutBase>
  },

  reloadAll() {
    return reloadPluginsApiPluginsReloadPost() as Promise<OutBase>
  },

  reloadInstance(payload: PluginReloadInstanceIn) {
    return reloadPluginInstanceApiPluginsReloadInstancePost({
      body: payload,
    }) as Promise<OutBase>
  },

  reloadPlugin(payload: PluginReloadPluginIn) {
    return reloadPluginByNameApiPluginsReloadPluginPost({
      body: payload,
    }) as Promise<OutBase>
  },

  installPackage(payload: PluginPackageIn) {
    return installPluginPackageApiPluginsInstallPackagePost({
      body: payload,
    }) as Promise<OutBase>
  },

  uninstallPackage(payload: PluginPackageIn) {
    return uninstallPluginPackageApiPluginsUninstallPackagePost({
      body: payload,
    }) as Promise<OutBase>
  },
}
