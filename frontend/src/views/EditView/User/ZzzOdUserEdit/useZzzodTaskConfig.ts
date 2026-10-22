import {
  computed,
  ref,
  reactive,
  toValue,
  watch,
  onScopeDispose,
  type Ref,
  type MaybeRefOrGetter,
} from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { Service } from '@/api'
import type { TaskCard } from './zzzodTypes'
export function useZzzodTaskConfig(options: {
  scriptId: string
  userId: MaybeRefOrGetter<string>
  instanceIdx: MaybeRefOrGetter<number | null>
  nativeMode: MaybeRefOrGetter<boolean>
  locked: Ref<boolean>
}) {
  const { scriptId, locked: configLocked } = options
  const { t } = useI18n()
  const getContext = () => ({
    userId: toValue(options.userId),
    instanceIdx: toValue(options.nativeMode) ? toValue(options.instanceIdx) : undefined,
  })
  type Context = ReturnType<typeof getContext>
  let contextVersion = 0
  let modalVersion = 0
  const reads = new Map<string, number>()
  const writes = new Set<Promise<boolean>>()
  const modalWrites = new Set<Promise<void>>()
  let saveChain: Promise<boolean> = Promise.resolve(true)
  // ══ 任务卡片 ⚙：可配置任务弹出选项编辑（数据驱动元数据表）══
  // 字段类型决定渲染：select/team 下拉 / bool 开关 / number 数字；
  // plan_list（体力刷本/恶名狩猎）不走弹层，⚙ 打开计划编辑弹窗
  interface TaskConfigField {
    field: string
    title: string
    type: 'select' | 'bool' | 'number' | 'team' | 'plan_list'
    value: any
    options: { label: string; value: string }[]
    columns?: any[]
    newItem?: Record<string, any>
  }

  const taskConfigData = ref<Record<string, TaskConfigField[]>>({})

  const taskConfigLoading = ref<Record<string, boolean>>({})

  const taskPopoverOpen = ref<Record<string, boolean>>({})

  // 提示框受控：点击按钮后隐藏，避免盖住弹出的选项框（再次悬停恢复）
  const taskTipVisible = ref<Record<string, boolean>>({})

  const jumpTipVisible = ref<Record<string, boolean>>({})

  const setTaskLoading = (appId: string, loading: boolean) => {
    taskConfigLoading.value = { ...taskConfigLoading.value, [appId]: loading }
  }

  const setPopoverOpen = (appId: string, open: boolean) => {
    taskPopoverOpen.value = { ...taskPopoverOpen.value, [appId]: open }
  }
  const nextRead = (appId: string) => {
    const request = (reads.get(appId) ?? 0) + 1
    reads.set(appId, request)
    return request
  }

  /** 拉取任务配置字段（原生来源读所选实例原生 yml；独立来源读绑定槽） */
  const loadTaskConfig = async (
    card: TaskCard,
    request = nextRead(card.app_id)
  ): Promise<TaskConfigField[] | null> => {
    const context = getContext()
    const version = contextVersion
    const resp = await Service.getZzzodAppConfigApiApiScriptsZzzodAppConfigGet(
      scriptId,
      context.userId,
      card.app_id,
      context.instanceIdx
    )
    if (version !== contextVersion || reads.get(card.app_id) !== request) return null
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodTaskConfigLoadFailed'))
    }
    const fields = (resp.fields ?? []) as TaskConfigField[]
    taskConfigData.value = { ...taskConfigData.value, [card.app_id]: fields }
    return fields
  }

  /** ⚙ 点击（popover 受控模式）：plan_list 或字段较多（大设置）打开编辑弹窗，否则弹出层 */
  const handleTaskPopoverChange = async (card: TaskCard, open: boolean) => {
    const version = contextVersion
    const request = nextRead(card.app_id)
    const current = () => version === contextVersion && reads.get(card.app_id) === request
    if (!open) {
      setTaskLoading(card.app_id, false)
      setPopoverOpen(card.app_id, false)
      return
    }
    // 隐藏悬停提示，避免盖住弹出的选项框
    taskTipVisible.value = { ...taskTipVisible.value, [card.app_id]: false }
    setTaskLoading(card.app_id, true)
    try {
      const fields = await loadTaskConfig(card, request)
      if (!fields) return
      const useModal = fields.some(f => f.type === 'plan_list') || fields.length > 6
      if (useModal) {
        void openPlanModal(card, fields)
      } else {
        setPopoverOpen(card.app_id, true)
      }
    } catch (e) {
      if (current())
        message.error(e instanceof Error ? e.message : t('edit.zzzodTaskConfigLoadFailed'))
    } finally {
      if (current()) setTaskLoading(card.app_id, false)
    }
  }

  /** 数值框保存策略：@change 防抖合并（stepper 连点/长按自动步进/键入各合并
   * 为一次请求），失焦立即落盘待保存值；清空/纯空白/值未变由
   * saveTaskConfigField 守卫拦下 */
  const TASK_CONFIG_SAVE_DELAY = 600

  interface PendingTaskConfigSave {
    timer: ReturnType<typeof setTimeout>
    card: TaskCard
    field: TaskConfigField
    value: any
    context: Context
  }

  const taskConfigPending = new Map<string, PendingTaskConfigSave>()

  const taskConfigKey = (card: TaskCard, field: TaskConfigField) => `${card.app_id}::${field.field}`

  const scheduleTaskConfigSave = (card: TaskCard, field: TaskConfigField, value: any) => {
    const context = getContext()
    const key = taskConfigKey(card, field)
    const existing = taskConfigPending.get(key)
    if (existing) clearTimeout(existing.timer)
    const timer = setTimeout(() => {
      taskConfigPending.delete(key)
      void saveTaskConfigField(card, field, value, context)
    }, TASK_CONFIG_SAVE_DELAY)
    taskConfigPending.set(key, { timer, card, field, value, context })
  }

  const flushTaskConfigSave = (card: TaskCard, field: TaskConfigField) => {
    const pending = taskConfigPending.get(taskConfigKey(card, field))
    if (!pending) return
    clearTimeout(pending.timer)
    taskConfigPending.delete(taskConfigKey(card, field))
    void saveTaskConfigField(pending.card, pending.field, pending.value, pending.context)
  }

  const flushAllTaskConfigSaves = async () => {
    do {
      for (const pending of [...taskConfigPending.values()]) {
        clearTimeout(pending.timer)
        void saveTaskConfigField(pending.card, pending.field, pending.value, pending.context)
      }
      taskConfigPending.clear()
      await Promise.all([...writes, ...modalWrites])
    } while (taskConfigPending.size || writes.size || modalWrites.size)
  }

  const saveTaskConfigField = (
    card: TaskCard,
    field: TaskConfigField,
    value: any,
    context = getContext()
  ): Promise<boolean> => {
    if (configLocked.value) {
      message.error(t('edit.configLocked'))
      return Promise.resolve(false)
    }
    // 数值框清空（change 拿到 null/空串/纯空白）与 NaN 一律不发请求（后端
    // int(null/'' ) 报 400）；值未变跳过——Tab 经过或步进回原值时不发多余请求
    if (value === null || value === undefined || Number.isNaN(value)) return Promise.resolve(false)
    if (typeof value === 'string' && value.trim() === '') return Promise.resolve(false)
    if (Number(value) === Number(field.value)) return Promise.resolve(false)
    const persist = async (): Promise<boolean> => {
      try {
        const resp = await Service.saveZzzodAppConfigApiApiScriptsZzzodAppConfigSavePost({
          scriptId,
          userId: context.userId,
          appId: card.app_id,
          values: { [field.field]: value },
          instanceIdx: context.instanceIdx,
        })
        if (resp.code !== 200) {
          throw new Error(resp.message || t('edit.zzzodTaskConfigSaveFailed'))
        }
        field.value = value
        message.success(t('edit.zzzodTaskConfigSaved'))
        return true
      } catch (e) {
        message.error(e instanceof Error ? e.message : t('edit.zzzodTaskConfigSaveFailed'))
        return false
      }
    }
    const run = saveChain.then(persist, persist)
    saveChain = run
    writes.add(run)
    void run.finally(() => writes.delete(run))
    return run
  }

  // ══ 任务计划编辑弹窗（plan_list 大设置）══
  const planModal = reactive({
    open: false,
    loading: false,
    saving: false,
    appId: '',
    title: '',
    fields: [] as TaskConfigField[],
    draft: [] as Record<string, any>[],
    trainCategories: [] as any[],
  })

  const planModalField = computed(() => planModal.fields.find(f => f.type === 'plan_list') ?? null)

  const planModalOtherFields = computed(() => planModal.fields.filter(f => f.type !== 'plan_list'))

  const openPlanModal = async (card: TaskCard, fields?: TaskConfigField[]) => {
    const version = ++modalVersion
    planModal.saving = false
    planModal.appId = card.app_id
    planModal.title = card.app_name
    planModal.open = true
    planModal.loading = true
    try {
      const loaded = fields ?? (await loadTaskConfig(card))
      if (version !== modalVersion || !loaded) return
      planModal.fields = loaded
      const planField = loaded.find(f => f.type === 'plan_list')
      planModal.draft = ((planField?.value as any[]) ?? []).map(p => ({ ...p }))
      if (planField) {
        const resp = await Service.getZzzodTaskOptionsApiApiScriptsZzzodOptionsGet(
          scriptId,
          card.app_id
        )
        if (version !== modalVersion) return
        if (resp.code !== 200) {
          throw new Error(resp.message || t('edit.zzzodTaskConfigLoadFailed'))
        }
        planModal.trainCategories = resp.trainCategories ?? []
      }
    } catch (e) {
      if (version !== modalVersion) return
      message.error(e instanceof Error ? e.message : t('edit.zzzodTaskConfigLoadFailed'))
      planModal.open = false
    } finally {
      if (version === modalVersion) planModal.loading = false
    }
  }

  /** 弹窗保存：plan_list 提交整表（后端按 plan_id 保留已运行进度），其余字段提交当前值 */
  const persistPlanModal = async () => {
    if (configLocked.value) return
    const context = getContext()
    const version = modalVersion
    planModal.saving = true
    try {
      const values: Record<string, any> = {}
      for (const f of planModal.fields) {
        if (f.type === 'plan_list') {
          values[f.field] = planModal.draft.map(({ __key, ...rest }) => rest)
        } else {
          values[f.field] = f.value
        }
      }
      const resp = await Service.saveZzzodAppConfigApiApiScriptsZzzodAppConfigSavePost({
        scriptId,
        userId: context.userId,
        appId: planModal.appId,
        values,
        instanceIdx: context.instanceIdx,
      })
      if (resp.code !== 200) {
        throw new Error(resp.message || t('edit.zzzodTaskConfigSaveFailed'))
      }
      if (version === modalVersion) {
        planModal.saving = false
        planModal.open = false
      }
      message.success(t('edit.zzzodTaskConfigSaved'))
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('edit.zzzodTaskConfigSaveFailed'))
    } finally {
      if (version === modalVersion) planModal.saving = false
    }
  }
  const savePlanModal = () => {
    const run = persistPlanModal()
    modalWrites.add(run)
    void run.finally(() => modalWrites.delete(run))
    return run
  }
  watch(
    () => [toValue(options.userId), toValue(options.nativeMode), toValue(options.instanceIdx)],
    () => {
      // 排入的写入继续使用原上下文；新的视图不接收旧元数据或弹窗响应。
      void flushAllTaskConfigSaves()
      contextVersion++
      modalVersion++
      taskConfigData.value = {}
      taskConfigLoading.value = {}
      taskPopoverOpen.value = {}
      taskTipVisible.value = {}
      jumpTipVisible.value = {}
      planModal.open = false
      planModal.loading = false
      planModal.saving = false
      planModal.fields = []
      planModal.draft = []
      planModal.trainCategories = []
    },
    { flush: 'sync' }
  )
  watch(
    () => planModal.open,
    open => {
      if (!open) modalVersion++
    },
    { flush: 'sync' }
  )
  onScopeDispose(() => {
    contextVersion++
    modalVersion++
  })
  return {
    hasPendingSaves: () => taskConfigPending.size > 0 || writes.size > 0 || modalWrites.size > 0,
    taskConfigData,
    taskConfigLoading,
    taskPopoverOpen,
    taskTipVisible,
    jumpTipVisible,
    handleTaskPopoverChange,
    scheduleTaskConfigSave,
    flushTaskConfigSave,
    flushAllTaskConfigSaves,
    saveTaskConfigField,
    planModal,
    planModalField,
    planModalOtherFields,
    savePlanModal,
  }
}
