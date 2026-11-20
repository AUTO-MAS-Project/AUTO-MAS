import { useQueryClient } from '@tanstack/vue-query'
import { Service, type ActiveTriggerField } from '@/api'
import { beginAnalyticsOperation } from '@/utils/analytics'
import type { AnalyticsEventProps } from '@/types/analytics'
import type { GameRow } from '@/types/games'
import { ACTIVE_TRIGGERS_QUERY_KEY } from './useActiveTriggers'
import { checkedGameResponse, gameAdapter, GAMES_QUERY_KEY } from './useGamesApi'

type Operation = AnalyticsEventProps['game_operation_result']['operation']
const knownOperations = new Set<string>([
  'open',
  'close',
  'show',
  'hide',
  'minimize',
  'maximize',
  'refresh',
  'create_instance',
  'delete_instance',
  'install_app',
  'open_store',
  'check_components',
  'check_update',
  'update',
])

/** 提交配置触发器命令并观察后端记录的终态。 */
export function useGameTriggers() {
  const client = useQueryClient()
  const refresh = () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ACTIVE_TRIGGERS_QUERY_KEY }),
      client.invalidateQueries({ queryKey: GAMES_QUERY_KEY }),
    ])
  async function run(row: GameRow, uid: string, field: string): Promise<void> {
    const adapter = gameAdapter(row.type.type)
    const operation = (knownOperations.has(field) ? field : 'unknown') as Operation
    const accepted = beginAnalyticsOperation('game_operation_result')
    const observed = beginAnalyticsOperation('game_operation_observed_finished')
    try {
      const response = await Service.writeConfigTriggerApiConfigTriggersWritePost({
        configUid: uid,
        group: 'action',
        field,
        value: true,
      })
      accepted.finish({
        adapter,
        operation,
        outcome: response.code === 200 ? 'accepted' : 'rejected',
      })
      checkedGameResponse(response)
      if (!response.data) throw new Error('Operation record is missing')
      const taskId = response.data
      void refresh()
      while (true) {
        const result = checkedGameResponse(
          await Service.getConfigTriggerResultApiConfigTriggersResultPost({ taskId })
        ).data
        if (!result) throw new Error('Trigger result is unavailable')
        const { state, errorCode } = result
        if (state !== 'running' && state !== 'cancelling') {
          observed.finish({
            adapter,
            operation,
            outcome:
              state === 'succeeded' ? 'success' : state === 'cancelled' ? 'cancelled' : 'failure',
          })
          if (state === 'failed' || state === 'timed_out')
            throw new Error(errorCode || 'Trigger failed')
          return
        }
        await new Promise(resolve => setTimeout(resolve, 600))
      }
    } catch (error) {
      accepted.finish({ adapter, operation, outcome: 'unknown' })
      observed.finish({ adapter, operation, outcome: 'unknown' })
      throw error
    } finally {
      await refresh()
    }
  }
  return {
    run,
    async cancel({ configUid, group, field }: ActiveTriggerField) {
      try {
        checkedGameResponse(
          await Service.writeConfigTriggerApiConfigTriggersWritePost({
            configUid,
            group,
            field,
            value: false,
          })
        )
      } finally {
        await refresh()
      }
    },
  }
}
