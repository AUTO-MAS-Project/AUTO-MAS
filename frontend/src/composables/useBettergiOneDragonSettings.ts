// BetterGI 一条龙「设置项」读写（右栏按任务分组展示/编辑）
// 通过 OpenAPI 生成的 BetterGiService 类型化调用（后端新增接口后需重新 yarn openapi）。
import { BetterGiService } from '@/api'
import type { BetterGIOneDragonSettingsIn } from '@/api'

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
