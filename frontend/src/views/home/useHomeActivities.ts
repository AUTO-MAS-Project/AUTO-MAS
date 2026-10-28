import { observeHomeActivitySource } from './homeActivityAnalytics'
import { computed, onScopeDispose, ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { GameCalendarActivityCompletionIn } from '@/api'
import { useActivityCompletionApi } from '@/composables/useActivityCompletionApi'
import type { HomeActivityPanel, HomeModuleKey, ResourceItem } from '@/types/home'
import { createActivityPanel, createHomeActivityModules } from './activityModuleFactory'
import { withActivityCompletion } from './activityCompletion'

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
  const modules = createHomeActivityModules({ t, resources, resourceError })
  const refreshing = ref(new Set<HomeModuleKey>())
  const defaultServer = GameCalendarActivityCompletionIn.server.CN
  const completions = new Map<string, ReturnType<typeof useActivityCompletionApi>>()
  for (const module of modules.values()) {
    for (const server of module.completionServers ?? [defaultServer]) {
      completions.set(
        `${module.game}:${server}`,
        useActivityCompletionApi({ game: module.game, server })
      )
    }
  }
  const completionFor = (key: HomeModuleKey) => {
    const module = modules.get(key)!
    return completions.get(`${module.game}:${module.selectedServer?.() ?? defaultServer}`)!
  }
  const now = ref(Date.now())
  // 活动状态与进度按分钟更新；倒计时跨过边界时另由 refresh 立即更新。
  const clock = window.setInterval(() => {
    now.value = Date.now()
  }, 60_000)
  onScopeDispose(() => window.clearInterval(clock))

  const sources = new Map<
    HomeModuleKey,
    { start: () => void; stop: () => void; refresh: () => void }
  >()
  for (const [key, module] of modules) {
    const source = observeHomeActivitySource(module.game, module.source)
    sources.set(key, {
      ...source,
      start: () => {
        source.start()
        for (const server of module.completionServers ?? [defaultServer]) {
          void completions.get(`${module.game}:${server}`)!.load()
        }
      },
    })
  }

  const sourcePanels = computed<HomeActivityPanel[]>(() =>
    visibleKeys.value.flatMap(key => {
      const panel = createActivityPanel({ modules, key, now: now.value })
      return panel ? [panel] : []
    })
  )

  const panels = computed<HomeActivityPanel[]>(() =>
    sourcePanels.value.map(panel => {
      const completion = completionFor(panel.key)
      return {
        ...panel,
        activities: withActivityCompletion({
          section: {
            ...panel.activities,
            refresh: {
              label: t('core.home.activity.refresh'),
              loading: refreshing.value.has(panel.key),
            },
          },
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

  const refresh = async (key: HomeModuleKey) => {
    if (refreshing.value.has(key)) return
    now.value = Date.now()
    refreshing.value = new Set(refreshing.value).add(key)
    try {
      await sources.get(key)?.refresh()
    } finally {
      const pending = new Set(refreshing.value)
      pending.delete(key)
      refreshing.value = pending
    }
  }
  const select = (key: HomeModuleKey, value: string) => modules.get(key)?.select?.(value)
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
        error instanceof Error ? error.message : t('core.home.activity.completionSaveFailed')
      )
    }
  }

  return { panels, sources, refresh, select, action }
}
