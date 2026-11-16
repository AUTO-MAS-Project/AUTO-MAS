import { effectScope, getCurrentScope, onScopeDispose, watch, type Ref } from 'vue'
import type {
  DesktopMascotColors,
  DesktopMascotHostAPI,
  DesktopMascotIdleMessage,
  DesktopMascotMenuLabels,
  DesktopMascotTaskEvent,
  DesktopMascotTaskEvents,
} from '@/types/desktopMascot'

interface DesktopMascotInputs {
  isStandalonePage: Readonly<Ref<boolean>>
  isAppReady: Readonly<Ref<boolean>>
  ready: Readonly<Ref<boolean>>
  colors: Readonly<Ref<DesktopMascotColors | undefined>>
  menuLabels: Readonly<Ref<DesktopMascotMenuLabels>>
  greeting: Readonly<Ref<DesktopMascotIdleMessage>>
  working: Readonly<Ref<boolean>>
  animate: Readonly<Ref<boolean>>
}

interface DesktopMascotCapabilities {
  api: DesktopMascotHostAPI
  tasks: DesktopMascotTaskEvents
  refreshIdleMessage(): void
  translate(key: string, params?: Record<string, string>): string
  reportError(message: string, error: unknown): void
  showError(): void
}

/** 桌宠只订阅共享状态，不接管主题、性能模式或任务运行状态的生命周期。 */
export function useDesktopMascot(
  inputs: DesktopMascotInputs,
  capabilities: DesktopMascotCapabilities
): () => void {
  const { isStandalonePage, isAppReady, ready, colors, menuLabels, greeting, working, animate } =
    inputs
  const { api, tasks, translate: t, reportError, showError } = capabilities
  const scope = effectScope(true)
  scope.run(() => {
    const showDesktopMascotError = () => {
      if (scope.active) showError()
    }
    const disposeDesktopMascotError = api.onDesktopMascotError?.(showDesktopMascotError)
    const disposeRefreshIdleMessage = api.onDesktopMascotRefreshIdleMessage?.(() => {
      if (scope.active && !isStandalonePage.value && ready.value) capabilities.refreshIdleMessage()
    })
    onScopeDispose(() => {
      disposeDesktopMascotError?.()
      disposeRefreshIdleMessage?.()
    })
    const announcedMascotTasks = new Set<string>()
    // 沿用任务总览的状态和收尾判定，不把部分失败误报为成功。
    const consumeTaskEvent = (event: DesktopMascotTaskEvent): void => {
      if (!scope.active || isStandalonePage.value || !isAppReady.value) return
      if (event.type === 'snapshot') {
        for (const id of announcedMascotTasks) {
          if (!event.activeTaskIds.has(id)) announcedMascotTasks.delete(id)
        }
        for (const task of event.tasks) {
          if (task.working) announcedMascotTasks.add(task.taskId)
        }
        return
      }
      if (event.type === 'removed') {
        announcedMascotTasks.delete(event.taskId)
        return
      }
      const { task } = event
      const name = task.name || t('core.setting.basic.mascotTask')
      let text: string
      let reaction: 'success' | 'failure' | 'stopped' | undefined
      if (event.type === 'started') {
        if (announcedMascotTasks.has(task.taskId)) return
        announcedMascotTasks.add(task.taskId)
        text = t('core.setting.basic.mascotTaskStarted', { name })
      } else {
        announcedMascotTasks.delete(task.taskId)
        const key = {
          success: 'mascotTaskCompleted',
          failure: 'mascotTaskFailed',
          stopped: 'mascotTaskStopped',
          partialFailure: 'mascotTaskPartialFailure',
        }[event.result]
        text = t(`core.setting.basic.${key}`, { name })
        reaction =
          event.result === 'success'
            ? 'success'
            : event.result === 'stopped'
              ? 'stopped'
              : 'failure'
      }
      void api.showDesktopMascotNotice?.(text, reaction, task.taskId).catch(error => {
        reportError('显示桌宠提醒失败:', error)
      })
    }
    const disposeMascotTaskEvents = tasks.subscribe(consumeTaskEvent)
    onScopeDispose(disposeMascotTaskEvents)
    watch(
      () => !isStandalonePage.value && isAppReady.value,
      active => {
        if (!active) return
        // 新实例只用已有快照标记运行任务，不重播开始或历史完成提醒。
        const snapshot = tasks.snapshot()
        consumeTaskEvent({
          type: 'snapshot',
          tasks: snapshot,
          activeTaskIds: new Set(snapshot.map(task => task.taskId)),
        })
      },
      { immediate: true, flush: 'sync' }
    )
    watch(
      greeting,
      greeting => {
        if (isStandalonePage.value) return
        void api
          .setDesktopMascotIdleMessage?.({ text: greeting.text, author: greeting.author })
          .catch(error => {
            reportError('同步桌宠待机留言失败:', error)
          })
      },
      { immediate: true }
    )
    watch(
      [working, animate],
      ([working, animate]) => {
        if (isStandalonePage.value) return
        void api.setDesktopMascotActivity?.(working, animate).catch(error => {
          reportError('同步桌宠工作状态失败:', error)
        })
      },
      { immediate: true }
    )
    watch(
      [ready, menuLabels, colors],
      ([ready, labels, colors]) => {
        if (isStandalonePage.value) return
        void api.setDesktopMascotReady?.(ready && Boolean(colors), labels, colors).catch(error => {
          reportError('同步桌面桌宠失败:', error)
          showDesktopMascotError()
        })
      },
      { immediate: true, flush: 'post' }
    )

    onScopeDispose(() => {
      announcedMascotTasks.clear()
      if (!isStandalonePage.value) {
        void api.setDesktopMascotReady?.(false).catch(error => {
          reportError('释放桌宠联动失败:', error)
        })
      }
    })
  })
  const dispose = () => scope.stop()
  if (getCurrentScope()) onScopeDispose(dispose)
  return dispose
}
