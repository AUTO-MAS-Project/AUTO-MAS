import { computed, ref } from 'vue'
import type { SchedulerTab, TaskMessage } from './schedulerConstants'

// 使用内存变量（主窗口才会使用，Popup模式下保持空）
let schedulerTabsMemory: SchedulerTab[] = []

const loadTabsFromStorage = (): SchedulerTab[] => schedulerTabsMemory
const saveTabsToStorage = (tabs: SchedulerTab[]) => {
  schedulerTabsMemory = tabs
}

export function useSchedulerLogic() {
  const isDialogWindow = (window as any)?.electronAPI?.isDialogWindow?.() || false
  const isPopupRoute = typeof window !== 'undefined' && window.location.hash.startsWith('#/popup')
  if (isDialogWindow || isPopupRoute) {
    const empty = ref<SchedulerTab[]>([])
    return {
      schedulerTabs: empty,
      activeSchedulerTab: ref(''),
      taskOptionsLoading: ref(false),
      taskOptions: ref<any[]>([]),
      powerAction: ref(undefined),
      messageModalVisible: ref(false),
      currentMessage: ref<TaskMessage | null>(null),
      messageResponse: ref(''),
      addSchedulerTab: () => null,
      removeSchedulerTab: () => null,
      removeAllNonRunningTabs: () => null,
      startTask: () => null,
      stopTask: () => null,
      onLogScroll: () => null,
      setLogRef: () => null,
      onPowerActionChange: () => null,
      sendMessageResponse: () => null,
      cancelMessage: () => null,
      initialize: () => null,
      loadTaskOptions: () => null,
      cleanup: () => null,
      setOverviewRef: () => null,
      canChangePowerAction: computed(() => true),
    }
  }
  // 主窗口完整实现已在其他版本中定义；此精简文件仅保障 Popup 模式安全。
  const schedulerTabs = ref<SchedulerTab[]>(loadTabsFromStorage())
  return {
    schedulerTabs,
    activeSchedulerTab: ref(schedulerTabs.value[0]?.key || ''),
    taskOptionsLoading: ref(false),
    taskOptions: ref<any[]>([]),
    powerAction: ref(undefined),
    messageModalVisible: ref(false),
    currentMessage: ref<TaskMessage | null>(null),
    messageResponse: ref(''),
    addSchedulerTab: () => null,
    removeSchedulerTab: () => null,
    removeAllNonRunningTabs: () => null,
    startTask: () => null,
    stopTask: () => null,
    onLogScroll: () => null,
    setLogRef: () => null,
    onPowerActionChange: () => null,
    sendMessageResponse: () => null,
    cancelMessage: () => null,
    initialize: () => null,
    loadTaskOptions: () => null,
    cleanup: () => null,
    setOverviewRef: () => null,
    canChangePowerAction: computed(() => true),
  }
}
