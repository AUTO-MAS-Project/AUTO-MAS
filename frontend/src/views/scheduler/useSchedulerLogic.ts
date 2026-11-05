import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { message, Modal } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { Service, PowerIn } from '@/api'
import { useSchedulerStore } from '@/stores/scheduler'
import { useTaskApi } from '@/composables/useTaskApi'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { scopeRequest, reconcileScope } from '@/composables/taskSelection'
import { fetchTaskTargets, fetchTaskScope, type TaskTarget } from '@/composables/useTaskOptions'
import { onTaskRuntimeEvent } from '@/composables/useTaskRuntimeState'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import { WS_ID_MAIN, WS_POWER_SIGN_UPDATED } from '@/services/websocket/types'
import type { SchedulerTab } from './schedulerConstants'

/** 页面只编排草稿、请求和局部界面；运行数据与订阅不随页面挂载变化。 */
export function useSchedulerLogic() {
  const store = useSchedulerStore()
  const {
    tabs: schedulerTabs,
    activeTab: activeSchedulerTab,
    panels: schedulerPanels,
  } = storeToRefs(store)
  const taskApi = useTaskApi()
  const taskOptions = ref<TaskTarget[]>([])
  const taskOptionsLoading = ref(false)
  const powerAction = ref(PowerIn.signal.NO_ACTION)
  const latestScopeRequest = new WeakMap<SchedulerTab, object>()
  let optionsRequest: object | undefined
  let viewActive = true
  let initialized = false
  let powerSubscription: string | undefined
  let disposeRuntime: (() => void) | undefined

  async function loadTaskScope(tab: SchedulerTab) {
    const target = taskOptions.value.find(item => item.value === tab.selectedTaskId)
    const request = {}
    latestScopeRequest.set(tab, request)
    if (!target) {
      tab.scope = undefined
      tab.scopeLoading = false
      return
    }
    tab.scopeLoading = true
    tab.scopeError = undefined
    try {
      const fresh = await fetchTaskScope(target, taskOptions.value)
      if (latestScopeRequest.get(tab) === request && tab.selectedTaskId === target.value)
        tab.scope = reconcileScope(fresh, tab.scope)
    } catch (error) {
      if (latestScopeRequest.get(tab) === request)
        tab.scopeError =
          error instanceof Error ? error.message : t('core.scheduler.control.runScopeLoadFailed')
    } finally {
      if (latestScopeRequest.get(tab) === request) tab.scopeLoading = false
    }
  }
  async function handleTaskSelectionChange(tab: SchedulerTab, taskId: string | null) {
    if (store.statusFor(tab) === '运行' || tab.starting) return
    if (tab.selectedTaskId !== taskId) tab.scope = undefined
    tab.selectedTaskId = taskId
    await loadTaskScope(tab)
  }
  async function loadTaskOptions() {
    const request = (optionsRequest = {})
    taskOptionsLoading.value = true
    try {
      const options = await fetchTaskTargets()
      if (optionsRequest !== request) return
      taskOptions.value = options
      for (const tab of schedulerTabs.value) {
        if (store.statusFor(tab) === '运行' || tab.starting) continue
        if (!options.some(option => option.value === tab.selectedTaskId)) {
          tab.selectedTaskId = null
          tab.scope = undefined
        } else if (viewActive) void loadTaskScope(tab)
      }
    } catch (error) {
      if (optionsRequest === request)
        message.error(
          error instanceof Error ? error.message : t('core.scheduler.toast.fetchTaskListFailed')
        )
    } finally {
      if (optionsRequest === request) taskOptionsLoading.value = false
    }
  }
  async function startTask(tab: SchedulerTab) {
    if (tab.starting || store.statusFor(tab) === '运行') return
    const target = taskOptions.value.find(item => item.value === tab.selectedTaskId)
    if (!target || !tab.scope || tab.scopeLoading || tab.scopeError) {
      message.error(tab.scopeError || t('core.scheduler.control.runScopeLoadFailed'))
      return
    }
    tab.starting = true
    try {
      const response = await taskApi.startTask(scopeRequest(tab.scope), {
        source: 'scheduler',
        target_kind: target.kind,
      })
      store.bindRun(tab, response.taskId)
      await useAudioPlayer().playSound('task_started')
      message.success(t('core.scheduler.toast.taskStarted'))
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : t('core.scheduler.toast.startTaskFailed')
      )
    } finally {
      tab.starting = false
    }
  }
  async function stopTask(tab: SchedulerTab) {
    if (!tab.taskId || store.statusFor(tab) !== '运行') return
    try {
      await taskApi.stopTask(tab.taskId, { source: 'scheduler' })
      await useAudioPlayer().playSound('maa_task_aborted')
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    }
  }
  function removeSchedulerTab(key: string) {
    const tab = schedulerTabs.value.find(tab => tab.key === key)
    if (!tab) return
    if (store.statusFor(tab) === '运行' || tab.starting) {
      Modal.warning({
        title: t('core.scheduler.modal.cannotDeleteTitle'),
        content: t('core.scheduler.modal.cannotDeleteContent', { title: store.titleFor(tab) }),
        okText: t('core.scheduler.modal.gotIt'),
      })
      return
    }
    if (key === 'main') {
      message.warning(t('core.scheduler.toast.mainTabUndeletable'))
      return
    }
    Modal.confirm({
      centered: true,
      title: t('core.scheduler.modal.deleteTitle'),
      content: t('core.scheduler.modal.deleteContent', { title: store.titleFor(tab) }),
      okText: t('core.scheduler.modal.deleteOk'),
      cancelText: t('core.common.cancel'),
      okType: 'danger',
      onOk() {
        store.removeTab(key)
      },
    })
  }
  function removeAllNonRunningTabs() {
    const idle = schedulerTabs.value.filter(
      tab => tab.key !== 'main' && !tab.starting && store.statusFor(tab) !== '运行'
    )
    if (!idle.length) {
      message.info(t('core.scheduler.toast.noIdleTabs'))
      return
    }
    Modal.confirm({
      centered: true,
      title: t('core.scheduler.modal.batchDeleteTitle'),
      content: t('core.scheduler.modal.batchDeleteContent', { count: idle.length }),
      okText: t('core.scheduler.modal.deleteOk'),
      cancelText: t('core.common.cancel'),
      okType: 'danger',
      onOk() {
        idle.forEach(tab => store.removeTab(tab.key))
        message.success(t('core.scheduler.toast.batchDeleted', { count: idle.length }))
      },
    })
  }
  async function getPowerState() {
    try {
      const response = await Service.getPowerApiDispatchGetPowerPost()
      if (response.code === 200 && response.signal)
        powerAction.value = response.signal as PowerIn.signal
    } catch (error) {
      window.electronAPI.getLogger('调度台').warn('读取电源操作失败', error)
    }
  }
  async function onPowerActionChange(signal: PowerIn.signal) {
    try {
      const response = await Service.setPowerApiDispatchSetPowerPost({ signal })
      if (response.code !== 200) throw new Error(response.message)
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : t('core.scheduler.toast.powerActionFailed')
      )
      void getPowerState()
    }
  }
  async function initialize() {
    store.bootstrap()
    if (!initialized) {
      initialized = true
      window.addEventListener('power-state-changed', getPowerState)
      powerSubscription = subscribe({ id: WS_ID_MAIN, type: WS_POWER_SIGN_UPDATED }, () => {
        void getPowerState()
      })
      disposeRuntime = onTaskRuntimeEvent(event => {
        if (event.type === 'completed' && viewActive) void loadTaskOptions()
      })
    }
    void getPowerState()
    await loadTaskOptions()
  }
  async function setSchedulerViewActive(active: boolean) {
    const wasActive = viewActive
    viewActive = active
    if (active && !wasActive) await loadTaskOptions()
  }
  function cleanup() {
    optionsRequest = undefined
    window.removeEventListener('power-state-changed', getPowerState)
    if (powerSubscription) unsubscribe(powerSubscription)
    disposeRuntime?.()
    initialized = false
  }
  return {
    schedulerTabs,
    schedulerPanels,
    activeSchedulerTab,
    taskOptionsLoading,
    taskOptions,
    powerAction,
    addSchedulerTab: () => store.addTab(),
    removeSchedulerTab,
    removeAllNonRunningTabs,
    startTask,
    stopTask,
    handleTaskSelectionChange,
    loadTaskScope,
    loadTaskOptions,
    onPowerActionChange,
    initialize,
    cleanup,
    setSchedulerViewActive,
  }
}
