import { computed, effectScope, getCurrentScope, onScopeDispose, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { TaskCreateIn } from '@/api'
import { t } from '@/i18n'
import { useHomeGreetingStore } from '@/stores/homeGreeting'
import { usePerformanceStore } from '@/stores/performance'
import { connectionState } from '@/services/websocket/connection'
import { useAppClosing } from './useAppClosing'
import { useAppInitialization } from './useAppInitialization'
import type { useAudioPlayer } from './useAudioPlayer'
import { isBackendRuntimeUpdating } from './useBackendRuntimeUpdate'
import { useDesktopMascot } from './useDesktopMascot'
import { useDesktopMascotTaskActions } from './useDesktopMascotTaskActions'
import { useDesktopMascotTaskAdapter } from './useDesktopMascotTaskAdapter'
import { useLocale } from './useLocale'
import { useTheme } from './useTheme'
import type { useSchedulerLogic } from '@/views/scheduler/useSchedulerLogic'

interface DesktopMascotHostOptions {
  isStandalonePage: Readonly<Ref<boolean>>
  isInitializationPage: Readonly<Ref<boolean>>
  // 音频和调度台由应用持有，宿主只使用已有实例提供的能力。
  playSound: ReturnType<typeof useAudioPlayer>['playSound']
  trackStartedTask: ReturnType<typeof useSchedulerLogic>['trackStartedTask']
}

/** 桌宠渲染端唯一装配入口，只释放自身作用域，不接管共享服务的生命周期。 */
export function useDesktopMascotHost(options: DesktopMascotHostOptions): () => void {
  const scope = effectScope(true)
  scope.run(() => {
    const logger = window.electronAPI.getLogger('桌宠宿主')
    const taskLogger = window.electronAPI.getLogger('桌宠任务')
    const { isAppReady } = useAppInitialization()
    const { isClosing } = useAppClosing()
    const { activeAppearance, antTokens } = useTheme()
    const { antdLocale } = useLocale()
    const performance = usePerformanceStore()
    const greeting = useHomeGreetingStore()
    const tasks = useDesktopMascotTaskAdapter()
    const ready = computed(
      () => isAppReady.value && performance.initialized && !options.isInitializationPage.value
    )

    useDesktopMascotTaskActions(
      {
        active: computed(() => !options.isStandalonePage.value && ready.value && !isClosing.value),
        canOperate: () => !isBackendRuntimeUpdating() && connectionState().value === 'open',
        api: window.electronAPI,
        onStarted: task => {
          options.trackStartedTask({
            ...task,
            selectedMode: TaskCreateIn.mode.AUTO_PROXY,
            modeLabel: t('scheduler.mode.autoProxy'),
          })
          void options
            .playSound('task_started')
            .catch(error => taskLogger.warn('播放任务启动音频失败:', error))
        },
      },
      {
        tasks: tasks.control,
        translate: t,
        reportWarning: (text, error) => taskLogger.warn(text, error),
        showError: text => {
          taskLogger.error('桌宠任务操作失败:', text)
          message.error(text)
        },
      }
    )

    useDesktopMascot(
      {
        isStandalonePage: options.isStandalonePage,
        isAppReady,
        ready,
        colors: computed(() => {
          // 同主题包切换一样触发同步，即使最终颜色相同也保留原有接线。
          void activeAppearance.value
          const tokens = antTokens.value
          return tokens
            ? {
                background: tokens.colorBgElevated,
                text: tokens.colorText,
                border: tokens.colorBorder,
                radius: tokens.borderRadius,
              }
            : undefined
        }),
        menuLabels: computed(() => {
          void antdLocale.value
          return {
            pauseAnimation: t('setting.basic.mascotPauseAnimation'),
            resumeAnimation: t('setting.basic.mascotResumeAnimation'),
            pauseIdleMessage: t('setting.basic.mascotPauseIdleMessage'),
            resumeIdleMessage: t('setting.basic.mascotResumeIdleMessage'),
            refreshIdleMessage: t('setting.basic.mascotRefreshIdleMessage'),
            refreshUnavailable: t('setting.basic.mascotRefreshUnavailable'),
            quickStart: t('setting.basic.mascotQuickStart'),
            stopTask: t('setting.basic.mascotStopTask'),
            noTasks: t('setting.basic.mascotNoTasks'),
            noRunningTasks: t('setting.basic.mascotNoRunningTasks'),
            tasksUnavailable: t('setting.basic.mascotTasksUnavailable'),
            loadingTasks: t('setting.basic.mascotLoadingTasks'),
            capabilityUnavailable: t('setting.basic.mascotCapabilityUnavailable'),
          }
        }),
        greeting: computed(() => greeting.greeting),
        working: computed(() => performance.anyScriptRunning),
        animate: computed(() => !performance.lowPerformanceMode),
      },
      {
        api: {
          setDesktopMascotReady: window.electronAPI.setDesktopMascotReady,
          setDesktopMascotActivity: window.electronAPI.setDesktopMascotActivity,
          setDesktopMascotIdleMessage: window.electronAPI.setDesktopMascotIdleMessage,
          showDesktopMascotNotice: window.electronAPI.showDesktopMascotNotice,
          onDesktopMascotError: window.electronAPI.onDesktopMascotError,
          onDesktopMascotRefreshIdleMessage: window.electronAPI.onDesktopMascotRefreshIdleMessage,
        },
        tasks: tasks.events,
        refreshIdleMessage: greeting.refreshGreeting,
        translate: t,
        reportError: (text, error) => logger.error(text, error),
        showError: () => message.error(t('setting.basic.desktopMascotFailed')),
      }
    )
  })

  const dispose = () => scope.stop()
  if (getCurrentScope()) onScopeDispose(dispose)
  return dispose
}
