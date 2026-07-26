/**
 * 本机已安装插件版本获取。
 *
 * 市场快照的 installed_map 目前只上报布尔安装位（见 app/plugins/market.py
 * `_build_installed_map`），plugin.installed.sync 亦只带 {package, installed}。
 * 本机真实版本存在于插件网关快照的 plugin_packages 字段
 * （app/plugins/realtime.py / app/api/plugins.py，来自已安装 distribution 的
 * importlib metadata）。这里通过 POST /api/plugins/get 取回并转成
 * 「distribution 名 -> 版本」映射，供市场页补齐「本机版本」显示。
 */
import { OpenAPI } from '@/api'
import { authenticatedApiFetch } from '@/utils/httpSecurity'
import {
  buildInstalledVersionMap,
  type InstalledVersionMap,
  type PluginPackageVersionSource,
} from './marketModel'

interface PluginPackagesResponse {
  code?: number
  status?: string
  message?: string
  plugin_packages?: Record<string, PluginPackageVersionSource>
}

export const fetchInstalledVersionMap = async (): Promise<InstalledVersionMap> => {
  const base = (OpenAPI.BASE || 'http://127.0.0.1:36163').replace(/\/+$/, '')
  const response = await authenticatedApiFetch(`${base}/api/plugins/get`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  const payload = (await response.json()) as PluginPackagesResponse
  if (!response.ok || (payload.code !== undefined && payload.code !== 200)) {
    throw new Error(payload.message || `HTTP ${response.status}`)
  }
  return buildInstalledVersionMap(payload.plugin_packages || {})
}
