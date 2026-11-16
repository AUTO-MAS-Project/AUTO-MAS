// Electron 独立编译，不能依赖 renderer 生成客户端的运行时模块。
interface LogBundleResponse {
  code: number
  message: string
  directories: string[]
  needsDirectory: boolean
  incompleteCount: number
}

interface LogBundleActions {
  selectDirectory: () => Promise<string | null>
  openDirectory: (directory: string) => Promise<string>
}

/** 自动保存已有结果时直接打开；其余安装通过同一后端导出器保存。 */
export async function openMaaEndLogBundles(apiEndpoint: string, actions: LogBundleActions) {
  const resolve = async (outputDirectory?: string): Promise<LogBundleResponse> => {
    const response = await fetch(`${apiEndpoint}/api/scripts/maaend/log-bundle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ outputDirectory }),
    })
    if (!response.ok) throw new Error(`MaaEnd 日志请求失败: ${response.status}`)
    const result: LogBundleResponse = await response.json()
    if (result.code !== 200) throw new Error(result.message)
    return result
  }

  let result = await resolve()
  const reusedArchive = (result.directories?.length ?? 0) > 0
  if (result.needsDirectory) {
    const directory = await actions.selectDirectory()
    if (!directory) return { success: false, error: '用户取消' }
    result = await resolve(directory)
  }
  for (const directory of result.directories ?? []) {
    const error = await actions.openDirectory(directory)
    if (error) throw new Error(error)
  }
  return {
    success: true,
    directoryPaths: result.directories,
    incompleteCount: result.incompleteCount || (reusedArchive ? undefined : 0),
  }
}
