import { computed, onScopeDispose, ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { GameCalendarActivityCompletionIn } from '@/api'
import { useActivityCompletionApi } from '@/composables/useActivityCompletionApi'
import { createEmptySraActivityOverview } from '@/types/home'
import type { HomeActivityPanel, HomeModuleKey, ResourceItem } from '@/types/home'
import {
  endfieldActivityBanner,
  getActivityAccent,
  sraActivityBanner,
  stellaActivityBanner,
} from './activityBanner'
import {
  sraActivitySections,
  resourceActivitySection,
  isStarRailPermanentActivity,
} from './activitySections'
import { endfieldActivitySections } from './endfieldActivitySections'
import { withActivityCompletion } from './activityCompletion'
import { blueArchivePresentation } from './blueArchivePresentation'
import { useSraActivitySource } from './useSraActivitySource'
import { useReverse1999ActivitySource } from './useReverse1999ActivitySource'
import { useBlueArchiveActivitySource } from './useBlueArchiveActivitySource'
import { useArknightsActivitySource } from './useArknightsActivitySource'
import { useEndfieldActivitySource } from './useEndfieldActivitySource'
import { useStellaActivitySource } from './useStellaActivitySource'

/** 首页负责模块可见性；此处衔接活动数据源、展示适配与业务交互。 */
export const useHomeActivities = ({
  visibleKeys,
  resources,
  resourceError,
}: {
  visibleKeys: Ref<HomeModuleKey[]>
  resources: Ref<ResourceItem[]>
  resourceError: Ref<string>
}) => {
  const { t } = useI18n()
  // 失败文案由数据源按当前语言现取，不缓存初始化时的译文。
  const sraSources = {
    starrail: useSraActivitySource('sr', 'home.game.starrail'),
    genshin: useSraActivitySource('ys', 'home.game.genshin'),
    zenless: useSraActivitySource('zzz', 'home.game.zenless'),
    wutheringwaves: useSraActivitySource('ww', 'home.game.wutheringwaves'),
    nte: useSraActivitySource('nte', 'home.game.nte'),
    infinitynikki: useSraActivitySource('infinitynikki', 'home.game.infinitynikki'),
    reverse1999: useReverse1999ActivitySource(),
    arknights: useArknightsActivitySource(),
    stellasora: useStellaActivitySource(),
  }
  const blueArchiveSource = useBlueArchiveActivitySource()
  const endfieldSource = useEndfieldActivitySource()
  const completions = new Map<string, ReturnType<typeof useActivityCompletionApi>>()
  for (const game of Object.values(GameCalendarActivityCompletionIn.game)) {
    const servers =
      game === GameCalendarActivityCompletionIn.game.BLUEARCHIVE
        ? Object.values(GameCalendarActivityCompletionIn.server)
        : [GameCalendarActivityCompletionIn.server.CN]
    for (const server of servers) {
      completions.set(`${game}:${server}`, useActivityCompletionApi({ game, server }))
    }
  }
  const completionFor = (
    key: HomeModuleKey,
    server = key === 'bluearchive' ? blueArchiveSource.selectedServer.value : 'cn'
  ) => completions.get(`${key}:${server}`)!
  const now = ref(Date.now())
  // 活动状态与进度按分钟更新；倒计时跨过边界时另由 refresh 立即更新。
  const clock = window.setInterval(() => {
    now.value = Date.now()
  }, 60_000)
  onScopeDispose(() => window.clearInterval(clock))

  const sources = new Map<
    HomeModuleKey,
    { start: () => void; stop: () => void; refresh: () => void }
  >([
    ...Object.entries(sraSources).map(([key, source]) => [key as HomeModuleKey, source] as const),
    ['bluearchive', blueArchiveSource],
    ['endfield', endfieldSource],
  ])
  for (const [key, source] of sources) {
    sources.set(key, {
      ...source,
      start: () => {
        source.start()
        if (key === 'bluearchive') {
          for (const server of blueArchiveSource.servers.value)
            void completionFor(key, server.key).load()
        } else void completionFor(key).load()
      },
    })
  }

  const sourcePanels = computed<HomeActivityPanel[]>(() =>
    visibleKeys.value.map(key => {
      const base = { key, title: t(`home.game.${key}`), accent: getActivityAccent(key) }
      if (key === 'endfield') {
        return {
          ...base,
          ...endfieldActivityBanner(endfieldSource.overview.value),
          loading: endfieldSource.loading.value,
          ...endfieldActivitySections({
            overview: endfieldSource.overview.value,
            loading: endfieldSource.loading.value,
            now: now.value,
            t,
          }),
        }
      }
      if (key === 'bluearchive') {
        const selected = blueArchiveSource.selectedServer.value
        const server = blueArchiveSource.servers.value.find(item => item.key === selected)
        const overview = blueArchivePresentation(
          server?.overview ?? createEmptySraActivityOverview()
        )
        const sections = sraActivitySections({
          key,
          overview,
          loading: blueArchiveSource.loadingByServer[selected],
          now: now.value,
          t,
        })
        // 三个服已经并行加载，切换仅改变展示，保留原有选择持久化。
        sections.activities.choices = {
          label: t('home.bluearchive.serverLabel'),
          selected,
          options: blueArchiveSource.servers.value.map(item => ({
            value: item.key,
            label: item.label,
          })),
        }
        // 横幅只报限时活动，缺活动时不拿总力战等玩法填充版本。
        return {
          ...base,
          ...sraActivityBanner(overview),
          ...(!overview.versionName ? { subtitle: '', startTime: '', endTime: '' } : {}),
          cover: overview.cover || '',
          loading: blueArchiveSource.loadingByServer[selected],
          ...sections,
        }
      }
      const source = sraSources[key as keyof typeof sraSources]
      const overview = source.overview.value
      const sections = sraActivitySections({
        key,
        overview,
        loading: source.loading.value,
        now: now.value,
        t,
      })
      if (key === 'arknights') {
        sections.extraSections = resourceActivitySection({
          resources: resources.value,
          error: resourceError.value,
          t,
        })
      }
      return {
        ...base,
        ...(key === 'stellasora'
          ? stellaActivityBanner(overview)
          : sraActivityBanner(
              key === 'starrail'
                ? {
                    ...overview,
                    activities: overview.activities.filter(
                      item => !isStarRailPermanentActivity(item)
                    ),
                  }
                : overview
            )),
        loading: source.loading.value,
        ...sections,
      }
    })
  )

  const panels = computed<HomeActivityPanel[]>(() =>
    sourcePanels.value.map(panel => {
      const completion = completionFor(panel.key)
      return {
        ...panel,
        activities: withActivityCompletion({
          section: panel.activities,
          completion,
          now: now.value,
          t,
          showError: true,
        }),
        extraSections: panel.extraSections.map(section =>
          section.completable
            ? withActivityCompletion({ section, completion, now: now.value, t })
            : section
        ),
      }
    })
  )

  const refresh = (key: HomeModuleKey) => {
    now.value = Date.now()
    sources.get(key)?.refresh()
  }
  const select = (key: HomeModuleKey, value: string) => {
    if (key !== 'bluearchive') return
    const server = blueArchiveSource.servers.value.find(item => item.key === value)
    if (server) blueArchiveSource.selectServer(server.key)
  }
  const action = async (key: HomeModuleKey, id: string) => {
    const completion = completionFor(key)
    if (id === 'retry-completion') {
      await completion.load()
      return
    }
    const panel = panels.value.find(panel => panel.key === key)
    const item = [panel?.activities, ...(panel?.extraSections ?? [])]
      .flatMap(section => section?.items ?? [])
      .find(item => item.id === id && item.action)
    if (!item?.startTime || !item.endTime) return
    const activity = { name: item.name, startTime: item.startTime, endTime: item.endTime }
    const currentTime = Date.now()
    if (
      !completion.ready.value ||
      completion.isSaving(activity) ||
      new Date(item.startTime).getTime() > currentTime ||
      new Date(item.endTime).getTime() <= currentTime
    )
      return
    try {
      await completion.toggle(activity)
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : t('home.activity.completionSaveFailed')
      )
    }
  }

  return { panels, sources, refresh, select, action }
}
