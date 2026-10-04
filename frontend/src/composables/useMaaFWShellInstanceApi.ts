import { MaaFwService } from '@/api'
import type { MaaFWShellInstanceImportItem, MaaFWShellInstanceItem } from '@/api'
import { t } from '@/i18n'

/**
 * 外壳（MFAAvalonia / MXU / MFW-PyQt6）配置实例客户端：新建 MFW 脚本引导的最后一步用它把外壳里配好的
 * 实例导入成用户。业务失败走 `code !== 200` + `message`（HTTP 仍是 200），失败时抛带后端
 * 文案的 Error；逐个实例的成败在导入结果的各项里。
 */
export function useMaaFWShellInstanceApi() {
  /**
   * 项目目录里外壳保存的配置实例（只读扫描）。给了 `path` 就只扫那个目录（键位弹窗「选择其他目录」），
   * 否则先扫导入时记下的来源目录、再扫内嵌副本。
   */
  const listShellInstances = async (
    scriptId: string,
    path?: string
  ): Promise<MaaFWShellInstanceItem[]> => {
    const response = await MaaFwService.listMaafwShellInstancesApiScriptsMaafwShellInstancesPost({
      scriptId,
      ...(path ? { path } : {}),
    })
    if (response.code !== 200) {
      throw new Error(response.message || '读取外壳配置失败')
    }
    return response.data ?? []
  }

  /**
   * 「选择其他目录」：弹系统选目录框，只扫选中的那个目录（不写回脚本配置）。键位弹窗与用户页
   * 「配置导入」共用。取消选择返回 null；没有选目录能力（浏览器里）或扫描失败时抛带文案的 Error。
   */
  const pickShellInstanceDirectory = async (
    scriptId: string
  ): Promise<{ dir: string; instances: MaaFWShellInstanceItem[] } | null> => {
    if (!window.electronAPI?.selectFolder) {
      throw new Error(t('edit.filePickingUnavailableRun'))
    }
    const dir = await window.electronAPI.selectFolder()
    if (!dir) return null
    return { dir, instances: await listShellInstances(scriptId, dir) }
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

  /**
   * 把一份外壳实例的任务队列与选项覆盖到**已有**的某个用户：脚本建好之后又在外壳里调过队列时，
   * 用它再同步一次。换算与「导入成用户」同一条，所以对不上的任务 / 选项同样在结果的 `skipped` 里；
   * 一起回来的 `snapshot` 是实际写进用户配置的队列（原始 JSON，形状由调用方按自己的快照类型规整），
   * `info` 是写入时特调一并改掉的用户信息字段（如 M9A 的账号）。
   *
   * `path` 与列出这份实例时传的一致：实例 ID 只是外壳里的文件名，不带目录就会回默认目录按 ID 找。
   */
  const applyShellInstanceToUser = async (
    scriptId: string,
    userId: string,
    instanceId: string,
    path?: string
  ): Promise<{
    result: MaaFWShellInstanceImportItem
    snapshot: Record<string, unknown> | null
    info: Record<string, unknown>
  }> => {
    const response =
      await MaaFwService.applyMaafwShellInstanceApiScriptsMaafwShellInstancesApplyPost({
        scriptId,
        userId,
        instanceId,
        ...(path ? { path } : {}),
      })
    if (response.code !== 200) {
      throw new Error(response.message || '导入外壳配置失败')
    }
    const result = response.data?.result
    // 单项的失败（换算不了、用户配置写不进去）走 HTTP 200 + error 字段，这里当失败抛出去
    if (!result || result.error) {
      throw new Error(result?.error || '导入外壳配置失败')
    }
    return {
      result,
      snapshot: (response.data?.snapshot as Record<string, unknown> | null) ?? null,
      info: response.data?.info ?? {},
    }
  }

  return {
    listShellInstances,
    pickShellInstanceDirectory,
    importShellInstances,
    applyShellInstanceToUser,
  }
}
