import { ref, watch } from 'vue'
import {
  getDepotMaintainPreset,
  type DepotMaintainPlan,
  type DepotMaintainPresetKey,
} from './depotMaintainPresets'

export type DepotMaintainPlanRow = DepotMaintainPlan & { key: number }

interface DepotMaintainPlanEditorOptions {
  getSavedPlans: () => string
  savePlans: (value: string) => void
  loadStageCandidates: (itemId: string) => Promise<void>
  getBestStage: (itemId: string) => string | undefined
  isLoading: () => boolean
}

const DEBOUNCE_FLUSH_MS = 500

// 由用户编辑页持有，折叠或关闭快速配置时仍继续完成编辑。
export function useDepotMaintainPlanEditor(options: DepotMaintainPlanEditorOptions) {
  const plans = ref<DepotMaintainPlanRow[]>([])
  const selectedRowKeys = ref<number[]>([])
  const pendingEdits = new Set<Promise<void>>()
  const rowEditVersions = new WeakMap<DepotMaintainPlanRow, number>()
  let saveTimer: ReturnType<typeof setTimeout> | undefined
  let lastEmitted: string | null = null
  let nextKey = 0
  let disposed = false
  let editGeneration = 0

  watch(
    options.getSavedPlans,
    value => {
      // 自身保存的回声不重建条目，保留输入、选中状态和打开的下拉。
      if (value === lastEmitted) {
        lastEmitted = null
        return
      }
      lastEmitted = null
      // 配置恢复等外部更新使旧操作失效；自身失败回读的草稿保护由页面处理。
      editGeneration++
      if (saveTimer !== undefined) {
        clearTimeout(saveTimer)
        saveTimer = undefined
      }
      selectedRowKeys.value = []
      try {
        const parsed: unknown = JSON.parse(value || '[]')
        plans.value = Array.isArray(parsed)
          ? parsed
              .filter((plan: unknown): plan is DepotMaintainPlan => {
                if (!plan || typeof plan !== 'object') return false
                const row = plan as Partial<DepotMaintainPlan>
                return (
                  typeof row.Stage === 'string' &&
                  typeof row.DropId === 'string' &&
                  typeof row.DropCount === 'number'
                )
              })
              .map(plan => ({ key: nextKey++, ...plan }))
          : []
      } catch {
        plans.value = []
      }
      for (const itemId of new Set(plans.value.map(plan => plan.DropId).filter(Boolean))) {
        void options.loadStageCandidates(itemId)
      }
    },
    { immediate: true }
  )

  const savePlans = () => {
    if (saveTimer !== undefined) {
      clearTimeout(saveTimer)
      saveTimer = undefined
    }
    const next = JSON.stringify(
      plans.value.map(({ Stage, DropId, DropCount }) => ({ Stage, DropId, DropCount }))
    )
    if (next === options.getSavedPlans()) return
    lastEmitted = next
    options.savePlans(next)
  }

  const queueSave = () => {
    if (saveTimer !== undefined) clearTimeout(saveTimer)
    saveTimer = setTimeout(savePlans, DEBOUNCE_FLUSH_MS)
  }

  const trackPendingEdit = (edit: () => Promise<void>) => {
    const pending: Promise<void> = edit().finally(() => pendingEdits.delete(pending))
    pendingEdits.add(pending)
    return pending
  }

  const onItemChange = (record: DepotMaintainPlanRow) =>
    trackPendingEdit(async () => {
      const itemId = record.DropId
      const version = (rowEditVersions.get(record) ?? 0) + 1
      rowEditVersions.set(record, version)
      // 换物品时旧关卡无效，先清空；候选返回后仅为未被再次编辑的条目选关。
      record.Stage = ''
      savePlans()
      if (!itemId) return
      await options.loadStageCandidates(itemId)
      if (
        disposed ||
        !plans.value.includes(record) ||
        record.DropId !== itemId ||
        rowEditVersions.get(record) !== version
      )
        return
      if (!record.Stage) {
        const best = options.getBestStage(itemId)
        if (best) record.Stage = best
      }
      savePlans()
    })

  const onStageChange = (record: DepotMaintainPlanRow) => {
    // 手选或主动清空关卡都使此前的自动选关失效。
    rowEditVersions.set(record, (rowEditVersions.get(record) ?? 0) + 1)
    savePlans()
  }

  const importPreset = (preset: DepotMaintainPresetKey) =>
    trackPendingEdit(async () => {
      const generation = editGeneration
      selectedRowKeys.value = []
      const imported = getDepotMaintainPreset(preset).map(plan => ({ key: nextKey++, ...plan }))
      await Promise.all(
        [...new Set(imported.map(plan => plan.DropId).filter(Boolean))].map(itemId =>
          options.loadStageCandidates(itemId)
        )
      )
      if (disposed || generation !== editGeneration) return
      for (const plan of imported) {
        const best = options.getBestStage(plan.DropId)
        if (best) plan.Stage = best
      }
      // 合并到当前列表，候选等待期间的新编辑和删除不会被旧快照覆盖。
      plans.value.push(...imported)
      savePlans()
    })

  const moveRow = (index: number, offset: number) => {
    const target = index + offset
    if (options.isLoading() || target < 0 || target >= plans.value.length) return
    const next = [...plans.value]
    ;[next[index], next[target]] = [next[target], next[index]]
    plans.value = next
    savePlans()
  }

  const addPlan = () => {
    plans.value.push({ key: nextKey++, Stage: '', DropId: '', DropCount: 1 })
    savePlans()
  }

  const removePlan = (key: number) => {
    selectedRowKeys.value = selectedRowKeys.value.filter(selectedKey => selectedKey !== key)
    plans.value = plans.value.filter(plan => plan.key !== key)
    savePlans()
  }

  const removeSelectedPlans = () => {
    plans.value = plans.value.filter(plan => !selectedRowKeys.value.includes(plan.key))
    selectedRowKeys.value = []
    savePlans()
  }

  const flushPendingEdits = async () => {
    while (pendingEdits.size > 0) await Promise.all([...pendingEdits])
    if (saveTimer !== undefined) savePlans()
  }

  const hasPendingEdits = () => saveTimer !== undefined || pendingEdits.size > 0

  const dispose = () => {
    if (saveTimer !== undefined) savePlans()
    disposed = true
  }

  return {
    plans,
    selectedRowKeys,
    savePlans,
    queueSave,
    onItemChange,
    onStageChange,
    importPreset,
    moveRow,
    addPlan,
    removePlan,
    removeSelectedPlans,
    flushPendingEdits,
    hasPendingEdits,
    dispose,
  }
}

export type DepotMaintainPlanEditorState = ReturnType<typeof useDepotMaintainPlanEditor>
