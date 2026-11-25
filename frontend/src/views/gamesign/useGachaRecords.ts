import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { beginAnalyticsOperation } from '@/utils/analytics'
import {
  isPluginUnavailable,
  signflowApi,
  type SignflowGachaPool,
  type SignflowGachaRecord,
} from '@/services/signflowApi'

/**
 * 抽卡记录页的状态与请求。
 *
 * 「插件未启用」的判定收在 `services/signflowApi.ts` 一处：
 * 网关 404、宿主密封 503、插件自己回的 400 都要落到同一句提示，
 * 否则用户会以为凭据或网络坏了。
 */

const errorText = (error: unknown): string =>
  error instanceof Error ? error.message : String(error)

/** 记录行的时间是后端已格式化的字符串，个别游戏会给 ISO 的 T 分隔 */
export const formatRecordTime = (time: string): string => time.replace('T', ' ')

export interface GachaQueryFilter {
  game: string
  playerUid: string
  pool: string
}

export interface GachaFetchTarget {
  game: string
  accountUid: string
  playerUid: string
}

/** 抽卡两类操作共用一个事件，靠 action 区分；终态口径与宿主其它请求一致 */
type SignflowAction = 'gacha_query' | 'gacha_fetch'
type SignflowOutcome = 'success' | 'failure' | 'cancelled' | 'unsupported'

export function useGachaRecords() {
  const records = ref<SignflowGachaRecord[]>([])
  const pools = ref<SignflowGachaPool[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  const querying = ref(false)
  const fetching = ref(false)
  const errorMessage = ref('')
  /** 插件报告可查的游戏；探测失败时保持空数组，界面据此禁用筛选 */
  const games = ref<string[]>([])
  /** 插件未启用时的一次性说明；为空表示插件可用 */
  const unavailable = ref('')
  /** 插件首启只探测一次：未启用时每次切筛选都重试只会反复闪同一条提示 */
  let probed = false
  /** 查询代次：连点或翻页时后到的旧响应不能覆盖新结果 */
  let queryToken = 0
  /** 读取代次与查询分开：读取成功后还要再查一次，共用计数器会把读取的收尾判成过期 */
  let fetchToken = 0

  const probe = async (): Promise<void> => {
    if (probed) return
    probed = true
    try {
      const result = await signflowApi.gachaGames()
      games.value = Array.isArray(result.games) ? result.games : []
    } catch (error) {
      if (isPluginUnavailable(error)) {
        unavailable.value = t('core.gamesign.gacha.pluginMissing')
        return
      }
      // 后端还没起来之类的临时故障不算「插件未启用」，允许下次重试
      probed = false
      errorMessage.value = errorText(error)
    }
  }

  /**
   * 一次插件调用的旁观者。
   *
   * 早退分支也必须消费终态：代次过期说明结果已不属于当前筛选，记 cancelled；
   * 插件未启用是能力缺失而非故障，记 unsupported，两者都不该混进失败率。
   */
  const observeSignflow = (action: SignflowAction) => {
    const operation = beginAnalyticsOperation('signflow_requested')
    return (outcome: SignflowOutcome) => operation.finish({ action, outcome })
  }

  const query = async (filter: GachaQueryFilter): Promise<void> => {
    const finish = observeSignflow('gacha_query')
    await probe()
    if (unavailable.value) {
      finish('unsupported')
      return
    }
    const token = ++queryToken
    querying.value = true
    errorMessage.value = ''
    try {
      const result = await signflowApi.queryGacha({
        game: filter.game,
        playerUid: filter.playerUid,
        pool: filter.pool,
        page: page.value,
        pageSize: pageSize.value,
      })
      // 连点「查询」或快速翻页时，只让最后一次请求落地
      if (token !== queryToken) {
        finish('cancelled')
        return
      }
      records.value = result.data
      pools.value = Array.isArray(result.pools) ? result.pools : []
      total.value = result.total
      finish('success')
    } catch (error) {
      if (token !== queryToken) {
        finish('cancelled')
        return
      }
      if (isPluginUnavailable(error)) {
        unavailable.value = t('core.gamesign.gacha.pluginMissing')
        finish('unsupported')
        return
      }
      errorMessage.value = errorText(error)
      records.value = []
      total.value = 0
      finish('failure')
    } finally {
      if (token === queryToken) querying.value = false
    }
  }

  /** 只在用户点「获取记录」时调一次；插件端不排定时任务 */
  const fetchRecords = async (target: GachaFetchTarget): Promise<void> => {
    const finish = observeSignflow('gacha_fetch')
    await probe()
    if (unavailable.value) {
      finish('unsupported')
      return
    }
    const token = ++fetchToken
    fetching.value = true
    errorMessage.value = ''
    try {
      const result = await signflowApi.fetchGacha({
        game: target.game,
        accountUid: target.accountUid,
        playerUid: target.playerUid,
      })
      // 读取期间换了帐号或角色：这条结果已不属于当前筛选，别再按旧目标补一次查询
      if (token !== fetchToken) {
        finish('cancelled')
        return
      }
      // 读取成败只看插件有没有把记录取回来；warnings 里的部分失败仍算成功，
      // 因为记录确实落库了，把它记成 failure 会让成功率凭空下降
      finish('success')
      const warnings = Array.isArray(result.warnings) ? result.warnings : []
      if (warnings.length) {
        message.warning(t('core.gamesign.gacha.fetchWarnings', { warnings: warnings.join('；') }))
      } else {
        message.success(
          t('core.gamesign.gacha.fetchDone', { added: result.added, fetched: result.fetched })
        )
      }
      // 读取完成后回到第一页，让新记录立刻可见
      page.value = 1
      await query({ game: target.game, playerUid: target.playerUid, pool: '' })
    } catch (error) {
      if (token !== fetchToken) {
        finish('cancelled')
        return
      }
      if (isPluginUnavailable(error)) {
        unavailable.value = t('core.gamesign.gacha.pluginMissing')
        finish('unsupported')
        return
      }
      errorMessage.value = errorText(error)
      finish('failure')
    } finally {
      if (token === fetchToken) fetching.value = false
    }
  }

  /** 切帐号或改角色 UID 时要清掉上一份结果，避免把别人的记录当成当前角色的 */
  const reset = () => {
    // 换帐号或换角色后，在途的旧查询与读取结果都不再属于当前筛选
    queryToken += 1
    fetchToken += 1
    records.value = []
    pools.value = []
    total.value = 0
    page.value = 1
    errorMessage.value = ''
    // 作废旧请求编号后它们不会再清自己的加载态，这里必须一并收回，否则按钮会一直转圈
    querying.value = false
    fetching.value = false
  }

  /** 页面首屏只需要游戏清单，不必先查一次记录 */
  const loadGames = (): Promise<void> => probe()

  return {
    records,
    pools,
    games,
    loadGames,
    total,
    page,
    pageSize,
    querying,
    fetching,
    errorMessage,
    unavailable,
    query,
    fetchRecords,
    reset,
  }
}
