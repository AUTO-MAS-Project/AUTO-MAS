import {
  Service,
  type PluginRegistryUpdateIn,
  type PluginCatalogUpdateIn,
  type PluginConfigUpdateIn,
} from '@/api'
import { translate as t } from '@/i18n'
import { requestApi } from '@/utils/apiResult'

export function usePluginApi() {
  return {
    getRegistry: (recordId: string | null = null) =>
      requestApi(
        () => Service.getPluginRegistryApiPluginRegistryGetPost({ recordId }),
        t('plugins.loadFailed')
      ),
    getRuntime: () =>
      requestApi(() => Service.listPluginsApiPluginListPost(), t('plugins.loadFailed')),
    updateRegistry: (body: PluginRegistryUpdateIn) =>
      requestApi(
        () => Service.updatePluginRegistryApiPluginRegistryUpdatePost(body),
        t('plugins.actionFailed')
      ),
    getCatalog: () =>
      requestApi(
        () => Service.getPluginCatalogApiPluginCatalogGetPost({}),
        t('plugins.marketLoadFailed')
      ),
    refreshCatalog: () =>
      requestApi(
        () => Service.refreshPluginCatalogApiPluginCatalogRefreshPost({}),
        t('plugins.marketRefreshFailed')
      ),
    updateCatalog: (body: PluginCatalogUpdateIn) =>
      requestApi(
        () => Service.updatePluginCatalogApiPluginCatalogUpdatePost(body),
        t('plugins.installFailed')
      ),
    getConfig: (recordId: string) =>
      requestApi(
        () => Service.getPluginConfigApiPluginConfigGetPost({ recordId }),
        t('plugins.settingsLoadFailed')
      ),
    updateConfig: (body: PluginConfigUpdateIn) =>
      requestApi(
        () => Service.updatePluginConfigApiPluginConfigUpdatePost(body),
        t('plugins.saveFailed')
      ),
  }
}
