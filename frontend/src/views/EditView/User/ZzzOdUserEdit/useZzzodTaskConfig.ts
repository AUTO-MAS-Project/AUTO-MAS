import { computed, ref, reactive, toValue, type Ref, type MaybeRefOrGetter } from 'vue'
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

  /** 拉取任务配置字段（原生来源读所选实例原生 yml；独立来源读绑定槽） */
  const loadTaskConfig = async (card: TaskCard): Promise<TaskConfigField[]> => {
    const instanceIdx = toValue(options.nativeMode) ? toValue(options.instanceIdx) : null
    const resp = await Service.getZzzodAppConfigApiApiScriptsZzzodAppConfigGet(
      scriptId,
      toValue(options.userId),
      card.app_id,
      instanceIdx
    )
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodTaskConfigLoadFailed'))
    }
    const fields = (resp.fields ?? []) as TaskConfigField[]
    taskConfigData.value = { ...taskConfigData.value, [card.app_id]: fields }
    return fields
  }

  /** ⚙ 点击（popover 受控模式）：plan_list 或字段较多（大设置）打开编辑弹窗，否则弹出层 */
  const handleTaskPopoverChange = async (card: TaskCard, open: boolean) => {
    if (!open) {
      setPopoverOpen(card.app_id, false)
      return
    }
    // 隐藏悬停提示，避免盖住弹出的选项框
    taskTipVisible.value = { ...taskTipVisible.value, [card.app_id]: false }
    setTaskLoading(card.app_id, true)
    try {
      const fields = await loadTaskConfig(card)
      const useModal = fields.some(f => f.type === 'plan_list') || fields.length > 6
      if (useModal) {
        void openPlanModal(card, fields)
      } else {
        setPopoverOpen(card.app_id, true)
      }
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('edit.zzzodTaskConfigLoadFailed'))
    } finally {
      setTaskLoading(card.app_id, false)
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
  }

  const taskConfigPending = new Map<string, PendingTaskConfigSave>()

  const taskConfigKey = (card: TaskCard, field: TaskConfigField) => `${card.app_id}::${field.field}`

  const scheduleTaskConfigSave = (card: TaskCard, field: TaskConfigField, value: any) => {
    const key = taskConfigKey(card, field)
    const existing = taskConfigPending.get(key)
    if (existing) clearTimeout(existing.timer)
    const timer = setTimeout(() => {
      taskConfigPending.delete(key)
      void saveTaskConfigField(card, field, value)
    }, TASK_CONFIG_SAVE_DELAY)
    taskConfigPending.set(key, { timer, card, field, value })
  }

  const flushTaskConfigSave = (card: TaskCard, field: TaskConfigField) => {
    const pending = taskConfigPending.get(taskConfigKey(card, field))
    if (!pending) return
    clearTimeout(pending.timer)
    taskConfigPending.delete(taskConfigKey(card, field))
    void saveTaskConfigField(pending.card, pending.field, pending.value)
  }

  const flushAllTaskConfigSaves = () => {
    for (const pending of [...taskConfigPending.values()]) {
      clearTimeout(pending.timer)
      void saveTaskConfigField(pending.card, pending.field, pending.value)
    }
    taskConfigPending.clear()
  }

  const saveTaskConfigField = async (
    card: TaskCard,
    field: TaskConfigField,
    value: any
  ): Promise<boolean> => {
    if (configLocked.value) {
      message.error(t('edit.configLocked'))
      return false
    }
    // 数值框清空（change 拿到 null/空串/纯空白）与 NaN 一律不发请求（后端
    // int(null/'' ) 报 400）；值未变跳过——Tab 经过或步进回原值时不发多余请求
    if (value === null || value === undefined || Number.isNaN(value)) return false
    if (typeof value === 'string' && value.trim() === '') return false
    if (Number(value) === Number(field.value)) return false
    try {
      const resp = await Service.saveZzzodAppConfigApiApiScriptsZzzodAppConfigSavePost({
        scriptId,
        userId: toValue(options.userId),
        appId: card.app_id,
        values: { [field.field]: value },
        instanceIdx: toValue(options.nativeMode) ? toValue(options.instanceIdx) : undefined,
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
    planModal.appId = card.app_id
    planModal.title = card.app_name
    planModal.open = true
    planModal.loading = true
    try {
      const loaded = fields ?? (await loadTaskConfig(card))
      planModal.fields = loaded
      const planField = loaded.find(f => f.type === 'plan_list')
      planModal.draft = ((planField?.value as any[]) ?? []).map(p => ({ ...p }))
      if (planField) {
        const resp = await Service.getZzzodTaskOptionsApiApiScriptsZzzodOptionsGet(
          scriptId,
          card.app_id
        )
        if (resp.code !== 200) {
          throw new Error(resp.message || t('edit.zzzodTaskConfigLoadFailed'))
        }
        planModal.trainCategories = resp.trainCategories ?? []
      }
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('edit.zzzodTaskConfigLoadFailed'))
      planModal.open = false
    } finally {
      planModal.loading = false
    }
  }

  /** 弹窗保存：plan_list 提交整表（后端按 plan_id 保留已运行进度），其余字段提交当前值 */
  const savePlanModal = async () => {
    if (configLocked.value) return
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
        userId: toValue(options.userId),
        appId: planModal.appId,
        values,
        instanceIdx: toValue(options.nativeMode) ? toValue(options.instanceIdx) : undefined,
      })
      if (resp.code !== 200) {
        throw new Error(resp.message || t('edit.zzzodTaskConfigSaveFailed'))
      }
      planModal.open = false
      message.success(t('edit.zzzodTaskConfigSaved'))
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('edit.zzzodTaskConfigSaveFailed'))
    } finally {
      planModal.saving = false
    }
  }
  return {
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
