import { effectScope, onScopeDispose, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { t } from '@/i18n'
import type { useTheme } from './useTheme'
import type { useLocale } from './useLocale'
import { onTaskRuntimeEvent } from './useTaskRuntimeState'
import { usePerformanceStore } from '@/stores/performance'
import { useHomeGreetingStore } from '@/stores/homeGreeting'
import { resolveTaskCompletionFeedback, scriptHasStatus } from '@/utils/taskFailures'

type DesktopMascotOptions = Pick<ReturnType<typeof useTheme>, 'activeAppearance' | 'antTokens'> &
  Pick<ReturnType<typeof useLocale>, 'antdLocale'> & {
    isStandalonePage: Readonly<Ref<boolean>>
    isInitializationPage: Readonly<Ref<boolean>>
    isAppReady: Readonly<Ref<boolean>>
  }

/** 桌宠只订阅共享状态，不接管主题、性能模式或任务运行状态的生命周期。 */
export function useDesktopMascot(options: DesktopMascotOptions): () => void {
  const {
    isStandalonePage,
    isInitializationPage,
    isAppReady,
    activeAppearance,
    antdLocale,
    antTokens,
  } = options
  const logger = window.electronAPI.getLogger('桌宠联动')
  const performanceStore = usePerformanceStore()
  const homeGreetingStore = useHomeGreetingStore()
  const scope = effectScope()
  scope.run(() => {
    const showDesktopMascotError = () => {
      if (scope.active) message.error(t('setting.basic.desktopMascotFailed'))
    }
    const disposeDesktopMascotError =
      window.electronAPI.onDesktopMascotError?.(showDesktopMascotError)
    onScopeDispose(() => disposeDesktopMascotError?.())
    const announcedMascotTasks = new Set<string>()
    const mascotRunningStatuses = new Set(['运行', '运行中'])
    // 沿用任务总览的状态和收尾判定，不把部分失败误报为成功。
    const disposeMascotTaskEvents = onTaskRuntimeEvent(event => {
      if (isStandalonePage.value || !isAppReady.value) return
      if (event.type === 'snapshot') {
        for (const id of announcedMascotTasks) {
          if (!event.activeTaskIds.has(id)) announcedMascotTasks.delete(id)
        }
        for (const state of event.states) {
          if (
            state.mode !== 'ScriptConfig' &&
            state.taskInfo.some(info => scriptHasStatus(info, mascotRunningStatuses))
          )
            announcedMascotTasks.add(state.taskId)
        }
        return
      }
      if (event.type === 'removed') {
        announcedMascotTasks.delete(event.taskId)
        return
      }
      const { state } = event
      if (state.mode === 'ScriptConfig') return
      const name =
        state.taskName ||
        state.taskInfo
          .map(info => info.name)
          .filter(Boolean)
          .join('、') ||
        t('setting.basic.mascotTask')
      let text: string
      let reaction: 'success' | 'failure' | 'stopped' | undefined
      if (event.type === 'info') {
        if (
          announcedMascotTasks.has(state.taskId) ||
          !state.taskInfo.some(info => scriptHasStatus(info, mascotRunningStatuses))
        )
          return
        announcedMascotTasks.add(state.taskId)
        text = t('setting.basic.mascotTaskStarted', { name })
      } else if (event.type === 'completed' && state.outcome) {
        announcedMascotTasks.delete(state.taskId)
        const feedback = resolveTaskCompletionFeedback({
          outcome: state.outcome,
          task_info: state.taskInfo,
        })
        const key = {
          success: 'mascotTaskCompleted',
          error: 'mascotTaskFailed',
          cancelled: 'mascotTaskStopped',
          partialFailure: 'mascotTaskPartialFailure',
        }[feedback.kind]
        text = t(`setting.basic.${key}`, { name })
        reaction =
          feedback.kind === 'success'
            ? 'success'
            : feedback.kind === 'cancelled'
              ? 'stopped'
              : 'failure'
      } else return
      void window.electronAPI.showDesktopMascotNotice?.(text, reaction).catch(error => {
        logger.error('显示桌宠提醒失败:', error)
      })
    })
    onScopeDispose(disposeMascotTaskEvents)
    watch(
      () => homeGreetingStore.greeting,
      greeting => {
        if (isStandalonePage.value) return
        void window.electronAPI
          .setDesktopMascotIdleMessage?.({ text: greeting.text, author: greeting.author })
          .catch(error => {
            logger.error('同步桌宠待机留言失败:', error)
          })
      },
      { immediate: true }
    )
    watch(
      () => [performanceStore.anyScriptRunning, performanceStore.lowPerformanceMode] as const,
      ([working, lowPerformance]) => {
        if (isStandalonePage.value) return
        void window.electronAPI
          .setDesktopMascotActivity?.(working, !lowPerformance)
          .catch(error => {
            logger.error('同步桌宠工作状态失败:', error)
          })
      },
      { immediate: true }
    )
    watch(
      () =>
        [
          isAppReady.value && performanceStore.initialized && !isInitializationPage.value,
          activeAppearance.value,
          antdLocale.value,
          antTokens.value,
        ] as const,
      ([ready, , , tokens]) => {
        if (isStandalonePage.value) return
        void window.electronAPI
          .setDesktopMascotReady?.(
            ready && Boolean(tokens),
            {
              pauseAnimation: t('setting.basic.mascotPauseAnimation'),
              resumeAnimation: t('setting.basic.mascotResumeAnimation'),
              pauseIdleMessage: t('setting.basic.mascotPauseIdleMessage'),
              resumeIdleMessage: t('setting.basic.mascotResumeIdleMessage'),
            },
            tokens
              ? {
                  background: tokens.colorBgElevated,
                  text: tokens.colorText,
                  border: tokens.colorBorder,
                  radius: tokens.borderRadius,
                }
              : undefined
          )
          .catch(error => {
            logger.error('同步桌面桌宠失败:', error)
            showDesktopMascotError()
          })
      },
      { immediate: true, flush: 'post' }
    )

    onScopeDispose(() => {
      announcedMascotTasks.clear()
      if (!isStandalonePage.value) {
        void window.electronAPI.setDesktopMascotReady?.(false).catch(error => {
          logger.error('释放桌宠联动失败:', error)
        })
      }
    })
  })
  const dispose = () => scope.stop()
  onScopeDispose(dispose)
  return dispose
}
