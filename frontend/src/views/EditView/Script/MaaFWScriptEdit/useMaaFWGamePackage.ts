import { MaaFwService } from '@/api'
import type { MaaFWScriptConfig } from '@/types/script'
import type { MaaFWScriptChangeHandler } from './useMaaFWScriptDraft'

interface MaaFWGamePackageOptions {
  scriptId: string
  maafwConfig: MaaFWScriptConfig
  handleChange: MaaFWScriptChangeHandler
  resolveResourceName: (resourceName?: string) => string
  handleResourceChange: () => Promise<void>
}

/**
 * 游戏包名：按所选 resource 的 pipeline 推断，推出来就直接填进表单并落盘。
 * 首次读到 interface 时只补空的；切换 resource 时覆盖——包名本来就跟服务器走
 * （官服 / B 服不是一个包）。推不出或多个候选就不动，占位符继续写「留空则自动识别」。
 */
export function useMaaFWGamePackage({
  scriptId,
  maafwConfig,
  handleChange,
  resolveResourceName,
  handleResourceChange,
}: MaaFWGamePackageOptions) {
  const logger = window.electronAPI.getLogger('MaaFW 脚本编辑')

  const syncGamePackageName = async (overwrite: boolean) => {
    const path = maafwConfig.Info.Path.trim()
    const resource = resolveResourceName(maafwConfig.Info.Resource)
    if (!path || !resource) return
    if (!overwrite && maafwConfig.Game.PackageName.trim()) return
    try {
      // 带 scriptId：内嵌脚本按副本推断，来源目录不在了也照常。
      const response = await MaaFwService.resolveMaafwGamePackageApiScriptsMaafwGamePackagePost({
        path,
        resource,
        scriptId,
      })
      const resolved = response.code === 200 && response.data?.reason === 'resolved'
      const packageName = resolved ? (response.data?.package ?? '').trim() : ''
      if (!packageName || packageName === maafwConfig.Game.PackageName) return
      maafwConfig.Game.PackageName = packageName
      await handleChange('Game', 'PackageName', packageName)
    } catch (error) {
      logger.warn(`推断游戏包名失败: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const handleResourceChangeWithPackage = async () => {
    await handleResourceChange()
    await syncGamePackageName(true)
  }

  return { syncGamePackageName, handleResourceChangeWithPackage }
}
