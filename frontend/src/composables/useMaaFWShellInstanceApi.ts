import { MaaFwService } from '@/api'
import type { MaaFWShellInstanceImportItem, MaaFWShellInstanceItem } from '@/api'

/**
 * 外壳（MFAAvalonia / MXU）配置实例客户端：新建 MFW 脚本引导的最后一步用它把外壳里配好的
 * 实例导入成用户。业务失败走 `code !== 200` + `message`（HTTP 仍是 200），失败时抛带后端
 * 文案的 Error；逐个实例的成败在导入结果的各项里。
 */
export function useMaaFWShellInstanceApi() {
  /** 项目目录里外壳保存的配置实例（只读扫描）。 */
  const listShellInstances = async (scriptId: string): Promise<MaaFWShellInstanceItem[]> => {
    const response = await MaaFwService.listMaafwShellInstancesApiScriptsMaafwShellInstancesPost({
      scriptId,
    })
    if (response.code !== 200) {
      throw new Error(response.message || '读取外壳配置失败')
    }
    return response.data ?? []
  }

  /** 每个实例建一个用户，结果顺序同请求。 */
  const importShellInstances = async (
    scriptId: string,
    instanceIds: string[]
  ): Promise<MaaFWShellInstanceImportItem[]> => {
    const response =
      await MaaFwService.importMaafwShellInstancesApiScriptsMaafwShellInstancesImportPost({
        scriptId,
        instanceIds,
      })
    if (response.code !== 200) {
      throw new Error(response.message || '导入外壳配置失败')
    }
    return response.data ?? []
  }

  return { listShellInstances, importShellInstances }
}
