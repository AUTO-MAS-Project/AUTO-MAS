import { beginMainFeature } from './featureAnalytics'

/** 删除以资源服务的实际同步返回为准；不传资源 ID、名字或路径。 */
export function observePackageRemoval<T extends { success: boolean }>(
  package_kind: 'theme' | 'mascot',
  run: () => T
): T {
  const operation = beginMainFeature('appearance_package_finished')
  try {
    const result = run()
    operation.finish({
      package_kind,
      action: 'delete',
      outcome: result.success ? 'success' : 'failure',
    })
    return result
  } catch (error) {
    operation.finish({ package_kind, action: 'delete', outcome: 'unknown' })
    throw error
  }
}
