import type { Composer } from 'vue-i18n'
import type { useActivityCompletionApi } from '@/composables/useActivityCompletionApi'
import type { HomeActivitySection } from '@/types/home'

/** 活动列表和常驻活动共用完成标记；卡池、资源关卡不接入该能力。 */
export const withActivityCompletion = ({
  section,
  completion,
  now,
  t,
  showError = false,
}: {
  section: HomeActivitySection
  completion: ReturnType<typeof useActivityCompletionApi>
  now: number
  t: Composer['t']
  showError?: boolean
}): HomeActivitySection => ({
  ...section,
  alerts: [
    ...(showError && completion.errorMessage.value
      ? [
          {
            id: 'retry-completion',
            message: t('home.activity.completionUnavailable'),
            description: completion.errorMessage.value,
            type: 'warning' as const,
            action: {
              label: t('home.activity.retryCompletion'),
              loading: completion.loading.value,
            },
          },
        ]
      : []),
    ...(section.alerts ?? []),
  ],
  items: section.items
    .map(item => {
      if (!item.startTime || !item.endTime) return item
      const activity = { name: item.name, startTime: item.startTime, endTime: item.endTime }
      const upcoming = new Date(item.startTime).getTime() > now
      const completed = completion.isCompleted(activity)
      return {
        ...item,
        completed,
        status: {
          label: t(
            completed
              ? 'home.activity.completed'
              : upcoming
                ? 'home.activity.upcoming'
                : 'home.activity.running'
          ),
          color: completed ? undefined : upcoming ? 'blue' : 'green',
        },
        action: {
          label: t(completed ? 'home.activity.undoCompletion' : 'home.activity.markCompleted', {
            name: item.name,
          }),
          disabled:
            !completion.ready.value ||
            completion.isSaving(activity) ||
            upcoming ||
            new Date(item.endTime).getTime() <= now,
          loading: completion.isSaving(activity),
        },
      }
    })
    .sort((a, b) => Number(a.completed) - Number(b.completed)),
})
