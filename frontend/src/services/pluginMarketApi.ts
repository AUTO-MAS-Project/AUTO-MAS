import { OpenAPI } from '@/api/core/OpenAPI'
import { request } from '@/api/core/request'

export interface PluginMarketItem {
  package: string
  version: string
  summary: string
  project_url: string
  prefix_tag: string
}

export interface PluginMarketSnapshot {
  schema_version: 1
  prefix_tags: string[]
  fetched_at: string
  items: PluginMarketItem[]
  installed_map: Record<string, boolean>
  total: number
}

export const pluginMarketApi = {
  getSnapshot(perPrefixLimit: number = 60): Promise<PluginMarketSnapshot> {
    return request<PluginMarketSnapshot>(OpenAPI, {
      method: 'GET',
      url: '/api/plugins/market/snapshot',
      query: { per_prefix_limit: perPrefixLimit },
    })
  },
}
