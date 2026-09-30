import { onScopeDispose, ref, watch } from 'vue'
import { i18n, translate } from '@/i18n'
import { createEmptySraActivityOverview } from '@/types/home'
import type { SraActivityItem, SraActivityOverview } from '@/types/home'

const logger = window.electronAPI.getLogger('活动数据')

/** 与后端现有活动服务一致的请求超时与失败重试节奏 */
const FETCH_TIMEOUT_MS = 20_000
const RETRY_DELAY_MS = 30_000
const MAX_RETRIES = 8

/** SRA 公开接口直连返回的数据（缺后端 SWR 包装的三个元数据） */
interface SraSourceData {
  version: string
  versionName: string
  startTime: string
  endTime: string
  cover?: string
  activities: SraActivityItem[]
}

const SOURCE_BASE = 'https://starrailassistant.top/api/v1/activity'

/** SRA 默认语言数据即中文（不带语言标识的 {game}.json），对应界面语言 zh-CN。 */
const DEFAULT_LOCALE = 'zh-CN'

/**
 * 按界面语言生成候选地址（SRA 公开 API：/{game}-{locale}.json，缺档时回退）。
 * zh-CN 直接用无语言标识的默认数据；其它语言先取对应语言档，
 * SRA 未提供该语言（如 ja-JP）时回退到无语言标识的默认地址。
 */
const sourceUrls = (game: string, locale: string): string[] => {
  const defaultUrl = SOURCE_BASE + '/' + game + '.json'
  if (locale === DEFAULT_LOCALE || !locale) return [defaultUrl]
  return [SOURCE_BASE + '/' + game + '-' + locale + '.json', defaultUrl]
}

/** 快照按语言隔离，切语言后不会把上一语言的数据当成新语言的缓存。 */
const snapshotKey = (game: string, locale: string) =>
  'auto-mas.home.sra-snapshot.' + game + '.' + locale

/**
 * 单游戏活动数据的直连数据源（首页全前端化第一步）。
 *
 * 职责与后端 SraActivityService 对齐：按当前界面语言请求 SRA 公开接口
 * （缺档回退无语言标识的默认数据），带超时、失败退避重试、本地快照
 * （stale-while-revalidate）与独立失败态——任一源异常只影响本卡片，
 * 不阻塞其它卡片。
 *
 * @param nameKey 游戏名的 i18n key（如 home.game.starrail）。失败文案在
 * 出错时按当前语言现取，不缓存初始化时的译文，切语言后不会显示旧语言文案。
 */
export const useSraActivitySource = (game: string, nameKey: string) => {
  const overview = ref<SraActivityOverview>(createEmptySraActivityOverview())
  const loading = ref(false)
  const hasData = ref(false)
  let retryTimer: number | null = null
  let retryCount = 0
  let disposed = false

  const currentLocale = () => i18n.global.locale.value

  // 启动先用上次快照填卡片，不等网络
  const restoreSnapshot = () => {
    try {
      const raw = localStorage.getItem(snapshotKey(game, currentLocale()))
      if (raw) {
        const cached = JSON.parse(raw) as SraSourceData
        overview.value = { Available: true, Stale: false, Message: '', ...cached }
        hasData.value = true
        return true
      }
    } catch {
      // 快照损坏按无缓存处理
    }
    return false
  }

  restoreSnapshot()
  if (!hasData.value) {
    loading.value = true
  }

  const load = async () => {
    if (disposed) return
    const locale = currentLocale()
    try {
      const controller = new AbortController()
      const timer = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
      let data: SraSourceData | null = null
      let lastError = ''
      try {
        // 语言档 404 等单档失败时依次尝试下一候选，最终回退无语言标识默认档
        for (const url of sourceUrls(game, locale)) {
          try {
            const response = await fetch(url, {
              signal: controller.signal,
              headers: { Accept: 'application/json' },
            })
            if (!response.ok) {
              lastError = 'HTTP ' + response.status
              continue
            }
            data = (await response.json()) as SraSourceData
            break
          } catch (fetchError) {
            lastError = fetchError instanceof Error ? fetchError.message : String(fetchError)
            if (controller.signal.aborted) break
          }
        }
      } finally {
        window.clearTimeout(timer)
      }
      if (!data) throw new Error(lastError || 'empty response')
      // 请求期间切换了语言：丢弃过期响应，交给语言切换的重取
      if (disposed || locale !== currentLocale()) return
      overview.value = { Available: true, Stale: false, Message: '', ...data }
      hasData.value = true
      retryCount = 0
      try {
        localStorage.setItem(snapshotKey(game, locale), JSON.stringify(data))
      } catch {
        // 本地存储不可用时仅跳过快照缓存
      }
    } catch (requestError) {
      if (disposed || locale !== currentLocale()) return
      const errorMessage =
        requestError instanceof Error ? requestError.message : String(requestError)
      const name = translate(nameKey)
      logger.warn('获取' + name + '活动数据失败: ' + errorMessage)
      if (hasData.value) {
        overview.value = {
          ...overview.value,
          Stale: true,
          Message: translate('home.sra.staleMessage'),
        }
      } else {
        overview.value = createEmptySraActivityOverview(
          translate('home.sra.unavailable', { name })
        )
      }
      if (retryCount < MAX_RETRIES) {
        retryCount += 1
        if (active) {
          scheduleRetry()
        } else {
          // 模块隐藏期间不重试，重新可见时补一次
          retryPending = true
        }
      }
    } finally {
      // 语言已切换时不关新语言的加载态，交给新一轮请求收尾
      if (!disposed && locale === currentLocale()) {
        loading.value = false
      }
    }
  }

  // 模块可见时才发请求；隐藏时停掉重试定时器，重新可见时把攒下的重试补上
  let active = false
  let started = false
  let retryPending = false

  const scheduleRetry = () => {
    retryTimer = window.setTimeout(() => {
      retryTimer = null
      void load()
    }, RETRY_DELAY_MS)
  }

  const start = () => {
    if (disposed) return
    active = true
    if (!started) {
      started = true
      void load()
    } else if (retryPending) {
      retryPending = false
      void load()
    }
  }

  const stop = () => {
    active = false
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
      retryPending = true
    }
  }

  // 界面语言切换：换用新语言的快照（没有则清空待重取），可见时立即按新语言重取
  watch(i18n.global.locale, () => {
    if (disposed) return
    retryCount = 0
    // 丢弃旧语言排队中的重试：留着它会在新请求之后再打一次，
    // 同一语言出现重复请求，还可能并存多个重试定时器。
    // 补不补重试交给下面的可见性分支：可见即发新请求，隐藏才挂起
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
    if (restoreSnapshot()) {
      loading.value = false
    } else {
      // 上一语言的数据对新语言无意义，宁可回到加载态也不展示错语言内容
      overview.value = createEmptySraActivityOverview()
      hasData.value = false
      loading.value = true
    }
    if (!started) return
    if (active) {
      void load()
    } else {
      retryPending = true
    }
  })

  onScopeDispose(() => {
    disposed = true
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
  })

  return {
    overview,
    loading,
    start,
    stop,
    refresh: () => {
      retryCount = 0
      void load()
    },
  }
}
