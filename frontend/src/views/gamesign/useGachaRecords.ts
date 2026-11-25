import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import {
  SignflowError,
  signflowApi,
  type SignflowGachaPool,
  type SignflowGachaRecord,
} from '@/services/signflowApi'

/**
 * 抽卡记录页的状态与请求。
 *
 * 插件路由由宿主运行期挂载：未启用时网关给 404「插件未挂载接口」，
 * 服务缺失时插件自己给 400「……插件未启用」。这两种都要落到「插件未启用」提示，
 * 而不是当成读取失败，否则用户会以为凭据或网络坏了。
 */
const isPluginUnavailable = (error: unknown): boolean =>
  error instanceof SignflowError &&
  (error.code === 404 || (error.code === 400 && error.message.includes('未启用')))

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

  const query = async (filter: GachaQueryFilter): Promise<void> => {
    await probe()
    if (unavailable.value) return
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
      records.value = result.data
      pools.value = Array.isArray(result.pools) ? result.pools : []
      total.value = result.total
    } catch (error) {
      if (isPluginUnavailable(error)) {
        unavailable.value = t('core.gamesign.gacha.pluginMissing')
        return
      }
      errorMessage.value = errorText(error)
      records.value = []
      total.value = 0
    } finally {
      querying.value = false
    }
  }

  /** 只在用户点「获取记录」时调一次；插件端不排定时任务 */
  const fetchRecords = async (target: GachaFetchTarget): Promise<void> => {
    await probe()
    if (unavailable.value) return
    fetching.value = true
    errorMessage.value = ''
    try {
      const result = await signflowApi.fetchGacha({
        game: target.game,
        accountUid: target.accountUid,
        playerUid: target.playerUid,
      })
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
      if (isPluginUnavailable(error)) {
        unavailable.value = t('core.gamesign.gacha.pluginMissing')
        return
      }
      errorMessage.value = errorText(error)
    } finally {
      fetching.value = false
    }
  }

  /** 切帐号或改角色 UID 时要清掉上一份结果，避免把别人的记录当成当前角色的 */
  const reset = () => {
    records.value = []
    pools.value = []
    total.value = 0
    page.value = 1
    errorMessage.value = ''
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
