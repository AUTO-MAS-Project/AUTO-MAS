import { beginMainFeature } from './featureAnalytics'
export interface VirtualDisplayDetachResult {
  code?: number
  status?: string
  message?: string
  detached?: boolean
}

/** HTTP 返回前后端可能已经关掉询问窗，主进程独立持有这一结果。 */
export async function detachPromptVirtualDisplay(
  endpoint: string
): Promise<VirtualDisplayDetachResult> {
  const operation = beginMainFeature('virtual_display_action_finished')
  try {
    const response = await fetch(`${endpoint}/api/setting/virtual-display/detach`, {
      method: 'POST',
    })
    if (!response.ok) throw new Error(response.statusText)
    const result = (await response.json()) as VirtualDisplayDetachResult
    operation.finish({
      action: 'remove',
      outcome: result.code !== 200 ? 'failure' : result.detached ? 'success' : 'skipped',
    })
    return result
  } catch (error) {
    operation.finish({ action: 'remove', outcome: 'unknown' })
    throw error
  }
}
