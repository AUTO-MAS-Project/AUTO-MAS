import { enterApp, retryAppEntry } from '@/utils/appEntry'
import { beginAnalyticsOperation } from '@/utils/analytics'
import { connectionState } from '@/services/websocket/connection'
import type { AnalyticsEventProps } from '@/types/analytics'
import { message } from 'ant-design-vue'
import { t } from '@/i18n'

type Result = AnalyticsEventProps['initialization_finished_v2']

/** 初始化尝试只在词表可用并进入应用后成功；失败留给本地恢复界面。 */
export async function finishInitializationEntry(options: {
  operation: ReturnType<typeof beginAnalyticsOperation<'initialization_finished_v2'>> | null
  flowKind: Result['flow_kind']
  runtimeMode: Result['runtime_mode']
  skipped: boolean
  resourcesOnly: boolean
}): Promise<void> {
  const { operation, flowKind, runtimeMode, skipped, resourcesOnly } = options
  try {
    const success = resourcesOnly ? await retryAppEntry() : await enterApp('初始化完成后进入', true)
    if (success) message.success(t('bootstrap.init.msg.initDone'))
    operation?.finish({
      flow_kind: flowKind,
      runtime_mode: runtimeMode,
      failed_stage: success ? 'none' : 'unknown',
      outcome: !success
        ? 'failure'
        : skipped
          ? 'skipped'
          : connectionState().value === 'open'
            ? 'success'
            : 'unconfirmed',
    })
  } catch {
    operation?.finish({
      flow_kind: flowKind,
      runtime_mode: runtimeMode,
      failed_stage: 'unknown',
      outcome: 'unconfirmed',
    })
  }
}
