// BetterGI 一条龙「设置项」读写（右栏按任务分组展示/编辑）
// 通过 OpenAPI 生成的 BetterGiService 类型化调用（后端新增接口后需重新 yarn openapi）。
import { BetterGiService } from '@/api'
import type {
  BetterGIDomainCatalogItem,
  BetterGIGlobalDomainSettingsIn,
  BetterGIGlobalStygianSettingsIn,
  BetterGIOneDragonSettingsIn,
} from '@/api'

const logger = window.electronAPI.getLogger('BetterGI一条龙设置')

/**
 * 读取某用户一条龙配置的设置项（per-user 副本 → BGI 实配 → 内置模板的种子顺序）。
 */
export const fetchOneDragonSettings = async (
  scriptId: string,
  userId: string,
  configName: string
): Promise<Record<string, unknown>> => {
  const resp = await BetterGiService.getBettergiOneDragonSettingsApiApiScriptsBettergiOneDragonSettingsGet(
    scriptId,
    userId,
    configName
  )
  if (resp.code !== 200) {
    throw new Error(resp.message || 'BetterGI 一条龙设置请求失败')
  }
  return (resp.data || {}) as Record<string, unknown>
}

/**
 * 把右栏编辑的设置项写回该用户一条龙配置副本（不触碰 BGI 同名实配）。
 * 返回是否成功；失败时抛错由调用方提示。
 */
export const saveOneDragonSettings = async (
  scriptId: string,
  userId: string,
  configName: string,
  settings: Record<string, unknown>
): Promise<void> => {
  const body: BetterGIOneDragonSettingsIn = { scriptId, userId, configName, settings }
  try {
    const resp =
      await BetterGiService.saveBettergiOneDragonSettingsApiApiScriptsBettergiOneDragonSettingsPost(
        body
      )
    if (resp.code !== 200) {
      throw new Error(resp.message || 'BetterGI 一条龙设置保存失败')
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    throw e instanceof Error ? e : new Error(String(e))
  }
}

/**
 * 读取秘境刷取配置（领奖树脂/分解圣遗物/奖励识别）。
 * userId 非空时读该用户 per-user 副本（副本缺失回退 BGI 全局实配），空时读 BGI 全局 config.json。
 */
export const fetchGlobalDomainSettings = async (
  scriptId: string,
  userId?: string
): Promise<Record<string, unknown>> => {
  const resp = await BetterGiService.getBettergiGlobalDomainSettingsApiApiScriptsBettergiGlobalDomainSettingsGet(
    scriptId,
    userId || undefined
  )
  if (resp.code !== 200) {
    throw new Error(resp.message || 'BetterGI 秘境刷取配置请求失败')
  }
  return (resp.data || {}) as Record<string, unknown>
}

/**
 * 读取自动幽境危战设置（刷取战场/战斗队伍/战斗策略/次数与树脂）。
 * userId 非空时读该用户 per-user 副本（副本缺失回退 BGI 全局实配），空时读 BGI 全局 config.json。
 */
export const fetchGlobalStygianSettings = async (
  scriptId: string,
  userId?: string
): Promise<Record<string, unknown>> => {
  const resp = await BetterGiService.getBettergiGlobalStygianSettingsApiApiScriptsBettergiGlobalStygianSettingsGet(
    scriptId,
    userId || undefined
  )
  if (resp.code !== 200) {
    throw new Error(resp.message || 'BetterGI 幽境危战设置请求失败')
  }
  return (resp.data || {}) as Record<string, unknown>
}

/**
 * 把右栏自动幽境危战设置写回 per-user 副本；userId 为空（直控模式）写 BGI 全局 config.json。
 */
export const saveGlobalStygianSettings = async (
  scriptId: string,
  userId: string | undefined,
  settings: Record<string, unknown>
): Promise<void> => {
  const body: BetterGIGlobalStygianSettingsIn = {
    scriptId,
    userId: userId || '',
    settings,
  }
  try {
    const resp =
      await BetterGiService.saveBettergiGlobalStygianSettingsApiApiScriptsBettergiGlobalStygianSettingsPost(
        body
      )
    if (resp.code !== 200) {
      throw new Error(resp.message || 'BetterGI 幽境危战设置保存失败')
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    throw e instanceof Error ? e : new Error(String(e))
  }
}

/**
 * 读取 BetterGI 每周秘境秘境候选目录（官方 tp.json 扫描，含每秘境三档奖励物）。
 * 失败时返回空数组并由调用方决定降级行为（表格仍可手动填写秘境名）。
 */
export const fetchDomainCatalog = async (
  scriptId: string
): Promise<BetterGIDomainCatalogItem[]> => {
  try {
    const resp =
      await BetterGiService.getBettergiDomainCatalogApiApiScriptsBettergiDomainCatalogGet(
        scriptId
      )
    if (resp.code !== 200) {
      logger.warn(resp.message || 'BetterGI 秘境目录请求失败')
      return []
    }
    return Array.isArray(resp.data) ? resp.data : []
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    return []
  }
}

/**
 * 把右栏秘境刷取配置写回 per-user 副本；userId 为空（直控模式）写 BGI 全局 config.json。
 */
export const saveGlobalDomainSettings = async (
  scriptId: string,
  userId: string | undefined,
  settings: Record<string, unknown>
): Promise<void> => {
  const body: BetterGIGlobalDomainSettingsIn = {
    scriptId,
    userId: userId || '',
    settings,
  }
  try {
    const resp =
      await BetterGiService.saveBettergiGlobalDomainSettingsApiApiScriptsBettergiGlobalDomainSettingsPost(
        body
      )
    if (resp.code !== 200) {
      throw new Error(resp.message || 'BetterGI 秘境刷取配置保存失败')
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    throw e instanceof Error ? e : new Error(String(e))
  }
}
