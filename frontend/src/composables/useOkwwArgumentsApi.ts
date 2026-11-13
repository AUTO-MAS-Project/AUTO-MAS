import { Service } from '@/api'

export function useOkwwArgumentsApi() {
  const previewArguments = async (scriptId: string, custom: boolean, argumentsText: string) => {
    const response = await Service.previewOkwwArgumentsApiApiScriptsOkwwStartupArgumentsPost({
      scriptId,
      custom,
      arguments: argumentsText,
    })
    if (response.code !== 200) throw new Error(response.message || '无法读取启动参数')
    return response
  }
  return { previewArguments }
}
