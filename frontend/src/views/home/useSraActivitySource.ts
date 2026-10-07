import { ref, watch } from 'vue'
import { i18n, translate } from '@/i18n'
import { createEmptySraActivityOverview } from '@/types/home'
import type { SraActivityItem, SraActivityOverview } from '@/types/home'
import { useHomeActivitySource } from './useHomeActivitySource'

/** 与后端现有活动服务一致的请求超时 */
const FETCH_TIMEOUT_MS = 20_000

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
 * 不阻塞其它卡片。取数与失败态在此实现，重试与快照调度交给公共骨架。
 *
 * @param nameKey 游戏名的 i18n key（如 home.game.starrail）。失败文案在
 * 出错时按当前语言现取，不缓存初始化时的译文，切语言后不会显示旧语言文案。
 */
export const useSraActivitySource = (game: string, nameKey: string) => {
  const overview = ref<SraActivityOverview>(createEmptySraActivityOverview())

  const currentLocale = () => i18n.global.locale.value

  const source = useHomeActivitySource<SraSourceData>({
    label: () => translate(nameKey),
    timeoutMs: FETCH_TIMEOUT_MS,
    requestTag: () => currentLocale(),
    isObsolete: tag => tag !== currentLocale(),
    restoreSnapshot: () => {
      try {
        const raw = localStorage.getItem(snapshotKey(game, currentLocale()))
        if (!raw) return false
        const cached = JSON.parse(raw) as SraSourceData
        overview.value = { Available: true, Stale: false, Message: '', ...cached }
        return true
      } catch {
        // 快照损坏按无缓存处理
        return false
      }
    },
    saveSnapshot: data => {
      try {
        localStorage.setItem(snapshotKey(game, currentLocale()), JSON.stringify(data))
      } catch {
        // 本地存储不可用时仅跳过快照缓存
      }
    },
    fetchData: async signal => {
      let lastError = ''
      // 语言档 404 等单档失败时依次尝试下一候选，最终回退无语言标识默认档
      for (const url of sourceUrls(game, currentLocale())) {
        try {
          const response = await fetch(url, {
            signal,
            headers: { Accept: 'application/json' },
          })
          if (!response.ok) {
            lastError = 'HTTP ' + response.status
            continue
          }
          return (await response.json()) as SraSourceData
        } catch (fetchError) {
          lastError = fetchError instanceof Error ? fetchError.message : String(fetchError)
          if (signal.aborted) break
        }
      }
      throw new Error(lastError || 'empty response')
    },
    applyData: data => {
      overview.value = { Available: true, Stale: false, Message: '', ...data }
    },
    markStale: () => {
      overview.value = {
        ...overview.value,
        Stale: true,
        Message: translate('home.sra.staleMessage'),
      }
    },
    markUnavailable: label => {
      overview.value = createEmptySraActivityOverview(
        translate('home.sra.unavailable', { name: label })
      )
    },
  })

  // 界面语言切换：换用新语言的快照（没有则清空待重取），可见时立即按新语言重取
  watch(i18n.global.locale, () => {
    source.resetRetry()
    if (source.restore()) {
      source.loading.value = false
    } else {
      // 上一语言的数据对新语言无意义，宁可回到加载态也不展示错语言内容
      overview.value = createEmptySraActivityOverview()
      source.hasData.value = false
      source.loading.value = true
    }
    source.resume()
  })

  return {
    overview,
    loading: source.loading,
    start: source.start,
    stop: source.stop,
    refresh: source.refresh,
  }
}
