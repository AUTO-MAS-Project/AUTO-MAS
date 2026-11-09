import { computed, onScopeDispose, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { TaskMode } from '@/api'
import { translate as t } from '@/i18n'
import { persistScope } from '@/composables/taskSelection'
import {
  getTaskRuntimeState,
  getTaskRuntimeStates,
  onTaskRuntimeEvent,
  retainTaskRuntime,
  registerAcceptedTask,
  releaseTaskRuntime,
  type TaskRuntimeState,
} from '@/composables/useTaskRuntimeState'
import { resolveTaskCompletionFeedback } from '@/utils/taskFailures'
import {
  TASK_MODE_LABEL_KEYS,
  type SchedulerTab,
  type SchedulerStatus,
} from '@/views/scheduler/schedulerConstants'

const STORAGE_KEY = 'scheduler-tabs-session'
const MAX_AUTOMATIC_COMPLETED_TABS = 20
const logger = window.electronAPI.getLogger('调度台')

function draft(tab: SchedulerTab): SchedulerTab {
  return {
    key: tab.key,
    title: tab.titleNumber === undefined ? tab.title : '',
    titleNumber: tab.titleNumber,
    closable: tab.closable,
    selectedTaskId: tab.selectedTaskId,
    selectedMode: tab.selectedMode,
    scope: tab.scope && Array.isArray(tab.scope.entries) ? persistScope(tab.scope) : undefined,
    taskId: tab.taskId,
    automatic: tab.automatic === true,
  }
}

function restoreTabs(): SchedulerTab[] {
  try {
    const workspace = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? 'null')
    const saved = Array.isArray(workspace) ? workspace : workspace?.tabs
    if (Array.isArray(saved) && saved.length && saved.every(tab => typeof tab?.key === 'string')) {
      return saved.map(draft)
    }
  } catch (error) {
    logger.warn(`读取调度台草稿失败: ${String(error)}`)
  }
  return [
    {
      key: 'main',
      title: '',
      closable: false,
      selectedTaskId: null,
      selectedMode: TaskMode.AUTO_PROXY,
      taskId: null,
    },
  ]
}

/** 标签及草稿的唯一所有者；运行信息和日志只通过运行 UUID 引用。 */
export const useSchedulerStore = defineStore('scheduler', () => {
  const tabs = ref<SchedulerTab[]>(restoreTabs())
  const savedActive = (() => {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? 'null')?.activeTab
    } catch {
      return null
    }
  })()
  const activeTab = ref(
    tabs.value.find(tab => tab.key === savedActive)?.key ?? tabs.value[0]?.key ?? 'main'
  )
  let counter = Math.max(1, ...tabs.value.map(tab => Number(tab.key.replace('tab-', '')) || 0))
  let saveTimer: number | undefined
  let disposeRuntime: (() => void) | undefined
  let retained = new Set<string>()

  const titleFor = (tab: SchedulerTab) =>
    tab.key === 'main'
      ? t('core.scheduler.mainTab')
      : tab.titleNumber === undefined
        ? tab.title
        : t('core.scheduler.tabName', { n: tab.titleNumber })
  const runFor = (tab: SchedulerTab) => (tab.taskId ? getTaskRuntimeState(tab.taskId) : undefined)
  const statusFor = (tab: SchedulerTab): SchedulerStatus => {
    const state = runFor(tab)
    if (!state) return tab.taskId ? '运行' : '空闲'
    if (state.phase !== 'completed') return '运行'
    const feedback = state.outcome
      ? resolveTaskCompletionFeedback({
          outcome: state.outcome,
          task_info: state.taskInfo,
        })
      : null
    return feedback?.kind === 'error' || feedback?.kind === 'partialFailure' ? '异常' : '结束'
  }
  // 不读取日志正文；高频日志不会重新计算总览、标题和状态。
  const panels = computed(() =>
    tabs.value.map(tab => {
      const runtime = runFor(tab)
      return {
        tab,
        runtime,
        title: titleFor(tab),
        status: statusFor(tab),
        taskLabel: runtime?.taskName ?? t('core.scheduler.scope.task'),
        modeLabel:
          runtime?.taskType ?? t(TASK_MODE_LABEL_KEYS[runtime?.mode ?? TaskMode.AUTO_PROXY]),
      }
    })
  )

  function persist() {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ tabs: tabs.value.map(draft), activeTab: activeTab.value })
      )
    } catch (error) {
      logger.warn(`保存调度台草稿失败: ${String(error)}`)
    }
  }
  watch(
    () => tabs.value.map(draft),
    () => {
      if (saveTimer !== undefined) window.clearTimeout(saveTimer)
      saveTimer = window.setTimeout(() => {
        saveTimer = undefined
        persist()
      }, 800)
    }
  )
  watch(
    () => tabs.value.map(tab => tab.taskId),
    ids => {
      const next = new Set(ids.filter((id): id is string => Boolean(id)))
      retained.forEach(id => {
        if (!next.has(id)) releaseTaskRuntime(id)
      })
      next.forEach(id => retainTaskRuntime(id))
      retained = next
    },
    { immediate: true, flush: 'sync' }
  )

  watch(activeTab, persist)

  function addTab(): SchedulerTab {
    const tab: SchedulerTab = {
      key: `tab-${++counter}`,
      title: '',
      titleNumber: counter,
      closable: true,
      selectedTaskId: null,
      selectedMode: TaskMode.AUTO_PROXY,
      taskId: null,
    }
    tabs.value.push(tab)
    activeTab.value = tab.key
    persist()
    return tabs.value[tabs.value.length - 1]
  }
  function removeTab(key: string) {
    const index = tabs.value.findIndex(tab => tab.key === key)
    if (index < 0) return
    tabs.value.splice(index, 1)
    if (activeTab.value === key) activeTab.value = tabs.value[Math.max(0, index - 1)]?.key ?? 'main'
    persist()
  }
  function bindRun(tab: SchedulerTab, taskId: string) {
    // WS 可能先创建了展示页；只调整绑定，运行对象及其日志不发生迁移。
    const extra = tabs.value.find(item => item.taskId === taskId && item.key !== tab.key)
    if (extra) removeTab(extra.key)
    tab.taskId = taskId
    activeTab.value = tab.key
    persist()
  }
  function trackStartedTask(task: {
    taskId: string
    selectedTaskId: string
    selectedMode: TaskMode
    taskLabel?: string
    modeLabel?: string
  }) {
    registerAcceptedTask(task.taskId, task.selectedMode)
    const existing = tabs.value.find(tab => tab.taskId === task.taskId)
    const reusable = tabs.value.find(
      tab =>
        tab.key !== 'main' &&
        !tab.starting &&
        statusFor(tab) !== '运行' &&
        tab.selectedTaskId === task.selectedTaskId
    )
    const tab = reusable ?? existing ?? addTab()
    tab.selectedTaskId = task.selectedTaskId
    tab.selectedMode = task.selectedMode
    bindRun(tab, task.taskId)
    return tab
  }
  function ensureRun(state: TaskRuntimeState) {
    if (tabs.value.some(tab => tab.taskId === state.taskId)) return
    const tab = addTab()
    tab.automatic = true
    bindRun(tab, state.taskId)
  }
  function pruneAutomaticTabs() {
    const completed = tabs.value.filter(
      tab => tab.automatic && tab.closable && !tab.starting && runFor(tab)?.phase === 'completed'
    )
    let excess = completed.length - MAX_AUTOMATIC_COMPLETED_TABS
    for (const tab of completed) {
      if (excess <= 0) break
      if (tab.key === activeTab.value) continue
      removeTab(tab.key)
      excess--
    }
  }
  function bootstrap() {
    if (disposeRuntime) return
    getTaskRuntimeStates()
      .filter(state => state.phase !== 'completed')
      .forEach(ensureRun)
    pruneAutomaticTabs()
    disposeRuntime = onTaskRuntimeEvent(event => {
      if (event.type === 'created') {
        ensureRun(event.state)
        pruneAutomaticTabs()
      }
      if (event.type === 'completed') pruneAutomaticTabs()
      if (event.type === 'snapshot') {
        event.states.forEach(ensureRun)
        tabs.value.forEach(tab => {
          if (
            tab.taskId &&
            !event.activeTaskIds.has(tab.taskId) &&
            !getTaskRuntimeState(tab.taskId)
          )
            tab.taskId = null
        })
        pruneAutomaticTabs()
      }
    })
  }
  function shutdown() {
    disposeRuntime?.()
    disposeRuntime = undefined
    persist()
  }
  onScopeDispose(() => {
    shutdown()
    if (saveTimer !== undefined) window.clearTimeout(saveTimer)
    retained.forEach(id => releaseTaskRuntime(id))
  })

  return {
    tabs,
    activeTab,
    panels,
    addTab,
    removeTab,
    bindRun,
    trackStartedTask,
    statusFor,
    titleFor,
    bootstrap,
    shutdown,
  }
})

export function bootstrapSchedulerTabs() {
  useSchedulerStore().bootstrap()
}
export function disposeSchedulerTabs() {
  useSchedulerStore().shutdown()
}
