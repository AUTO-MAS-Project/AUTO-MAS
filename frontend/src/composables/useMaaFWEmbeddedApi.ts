import { MaaFwService } from '@/api'
import type { MaaFWEmbeddedStatusData, MaaFWEmbeddedStatusOut } from '@/api'

/**
 * MFW 内嵌副本客户端。MFW 脚本一律在副本上跑：选目录就是导入（`reimportEmbedded`），
 * 之后换目录、手动更新过来源都走同一条。
 *
 * 两条路由都返回 `MaaFWEmbeddedStatusOut`：业务失败走 `code !== 200` + `message`
 * （HTTP 仍是 200），所以直接用生成的 `MaaFwService` 即可，不需要像项目更新那样
 * 从 AxiosError 里捞文案。成功时返回最新状态，失败时抛带后端文案的 Error。
 */
export type MaaFWEmbeddedStatus = Required<
  Pick<
    MaaFWEmbeddedStatusData,
    'copyPath' | 'copyHealthy' | 'sourcePath' | 'sourceExists' | 'sourceVersion' | 'importedAt'
  >
> & { report: MaaFWEmbeddedStatusData['report'] }

export const EMPTY_EMBEDDED_STATUS: MaaFWEmbeddedStatus = {
  copyPath: '',
  copyHealthy: false,
  sourcePath: '',
  sourceExists: false,
  sourceVersion: '',
  importedAt: '',
  report: null,
}

const unwrap = (response: MaaFWEmbeddedStatusOut, fallback: string) => {
  if (response.code !== 200) {
    throw new Error(response.message || fallback)
  }
  const data = response.data ?? {}
  return {
    status: {
      ...EMPTY_EMBEDDED_STATUS,
      ...data,
      report: data.report ?? null,
    } satisfies MaaFWEmbeddedStatus,
    message: response.message ?? '',
  }
}

export function useMaaFWEmbeddedApi() {
  const getEmbeddedStatus = async (scriptId: string) =>
    unwrap(
      await MaaFwService.getMaafwEmbeddedStatusApiScriptsMaafwEmbeddedStatusPost({ scriptId }),
      '读取内嵌状态失败'
    )

  /** 按来源目录导入副本：第一次是导入，之后是换来源或按当前来源重导。 */
  const reimportEmbedded = async (scriptId: string, sourcePath: string) =>
    unwrap(
      await MaaFwService.reimportMaafwEmbeddedApiScriptsMaafwEmbeddedReimportPost({
        scriptId,
        sourcePath,
      }),
      '导入失败'
    )

  return { getEmbeddedStatus, reimportEmbedded }
}

/** 把字节数变成给人看的 MB / GB；报告里的数值都是整数字节。 */
export const formatEmbeddedBytes = (bytes: number | undefined | null): string => {
  const value = Number(bytes ?? 0)
  if (!Number.isFinite(value) || value <= 0) return '0 MB'
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(2)} GB`
  return `${(value / 1024 ** 2).toFixed(1)} MB`
}
