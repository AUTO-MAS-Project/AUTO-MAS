import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import { Service, type ZzzOdRecycleEntryOut, type ZzzOdSlotOut } from '@/api'

/** MAS 槽号段起点（需与 app/task/ZzzOd/tools/zzz_od_config.py 的 MAS_SLOT_BASE 保持同步）：
 *  恢复快照的候选目标只在这个号段里挑——低号段是一条龙「升序找最小空号」的地盘 */
const MAS_SLOT_BASE = 1001

/**
 * 实例槽管理（脚本设置页的实例槽 / 回收池两张表与恢复流程）。
 *
 * 槽目录是 MAS 分配在一条龙安装目录里的 ``config/{idx:02d}``，一条龙注册表与
 * GUI 都看不到；这份对照表用于看清「槽目录数与用户数对不上」（绑定但没跑过的槽
 * 没有目录），回收池则是被删用户/脚本留下的槽内容与备份池快照（可恢复到原槽号
 * 或其他空闲槽号）。表格、清理与恢复弹窗的状态与动作都收在这里，组件只负责渲染。
 */
export function useZzzOdSlotManage(scriptId: () => string) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('ZZZ-OD脚本编辑')

  const panelKeys = ref<string[]>([])
  const slotLoaded = ref(false)
  const slotTab = ref('slots')
  const slots = ref<ZzzOdSlotOut[]>([])
  const slotsLoading = ref(false)
  const recycleRows = ref<Array<ZzzOdRecycleEntryOut & { key: string }>>([])
  const recycleLoading = ref(false)

  /** 任一破坏性操作进行中：清理 / 清空回收池 / 恢复互斥。
   *  三者都动安装目录与回收池，并发会互相拆台（最坏是恢复进行中清空回收池，
   *  把刚存底的目标槽原内容一并删掉），故统一置灰而不是各锁各的 */
  const slotActionBusy = computed(
    () => slotsLoading.value || recycleLoading.value || restoring.value
  )

  const slotColumns = computed(() => [
    { title: t('edit.zzzodSlotColIdx'), key: 'idx', width: 72 },
    { title: t('edit.zzzodSlotColKind'), key: 'kind', width: 210 },
    { title: t('edit.zzzodSlotColOwner'), key: 'owner' },
    { title: t('edit.zzzodSlotColDir'), key: 'dir', width: 80 },
    { title: t('edit.zzzodSlotColSize'), key: 'size', width: 96 },
  ])

  const recycleColumns = computed(() => [
    { title: t('edit.zzzodRecycleColSlot'), key: 'slot', width: 72 },
    { title: t('edit.zzzodRecycleColKind'), key: 'kind', width: 100 },
    { title: t('edit.zzzodRecycleColTime'), key: 'ts', width: 170 },
    { title: t('edit.zzzodRecycleColFiles'), key: 'files', width: 72 },
    { title: t('edit.zzzodRecycleColSize'), key: 'size', width: 96 },
    { title: t('edit.zzzodRecycleColOps'), key: 'ops', width: 88 },
  ])

  const recycleTabLabel = computed(() =>
    recycleRows.value.length
      ? `${t('edit.zzzodSlotTabRecycle')} (${recycleRows.value.length})`
      : t('edit.zzzodSlotTabRecycle')
  )

  const slotKindLabel = (kind: string) =>
    kind === 'native'
      ? t('edit.zzzodSlotKindNative')
      : kind === 'mas'
        ? t('edit.zzzodSlotKindMas')
        : t('edit.zzzodSlotKindOrphan')

  const slotKindColor = (kind: string) =>
    kind === 'native' ? 'default' : kind === 'mas' ? 'processing' : 'warning'

  /** 号被一条龙抢走：槽进了原生注册表，却仍有 MAS 用户绑着这个号。
   *  一条龙的「新增实例」只按自己的注册表找最小空号、不扫盘，会把 MAS 槽
   *  的号当成空号拿去用；MAS 侧下次运行会改绑到高位空闲槽并把残留存底 */
  const slotNativeConflict = (slot: ZzzOdSlotOut) =>
    slot.kind === 'native' && Boolean(slot.owners?.length)

  /** 用户的配置来源（Info.Mode：脚本/用户/直控）→ 展示文案 */
  const slotOwnerModeLabel = (mode: string) =>
    mode === '脚本'
      ? t('edit.zzzodSlotOwnerModeScript')
      : mode === '直控'
        ? t('edit.zzzodSlotOwnerModeDirect')
        : t('edit.zzzodSlotOwnerModeUser')

  const slotOwnerText = (slot: ZzzOdSlotOut) =>
    slot.owners?.length
      ? slot.owners
          .map(item => `${item.userName}（${item.scriptName}·${slotOwnerModeLabel(item.mode)}）`)
          .join('、')
      : '—'

  const recycleKindLabel = (kind: string) =>
    kind === 'mas' ? t('edit.zzzodRecycleKindMas') : t('edit.zzzodRecycleKindSlot')

  const formatSlotSize = (size: number) =>
    size >= 1024 * 1024
      ? `${(size / 1024 / 1024).toFixed(1)} MB`
      : size >= 1024
        ? `${(size / 1024).toFixed(1)} KB`
        : `${size} B`

  /** 归档时间戳（目录名 20260921-225131，同秒顺延为 20260921-225131-1）→
   *  2026-09-21 22:51:31（带同秒序号时末尾拼 .N） */
  const formatArchiveTs = (ts: string) => {
    const time = `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)} ${ts.slice(9, 11)}:${ts.slice(11, 13)}:${ts.slice(13, 15)}`
    return ts.length > 15 ? `${time}.${ts.slice(16)}` : time
  }

  const loadSlots = async () => {
    slotsLoading.value = true
    try {
      const resp = await Service.getZzzodSlotsApiApiScriptsZzzodSlotsGet(scriptId())
      if (resp.code !== 200) {
        throw new Error(resp.message || t('edit.zzzodSlotsLoadFailed'))
      }
      slots.value = resp.data || []
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('edit.zzzodSlotsLoadFailed'))
    } finally {
      slotsLoading.value = false
    }
  }

  const loadRecycle = async () => {
    recycleLoading.value = true
    try {
      const resp = await Service.getZzzodRecycleApiApiScriptsZzzodRecycleGet(scriptId())
      if (resp.code !== 200) {
        throw new Error(resp.message || t('edit.zzzodSlotsLoadFailed'))
      }
      recycleRows.value = (resp.data || []).map(item => ({
        ...item,
        key: `${item.slot}-${item.kind}-${item.ts}`,
      }))
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('edit.zzzodSlotsLoadFailed'))
    } finally {
      recycleLoading.value = false
    }
  }

  /** 刷新实例槽与回收池（首次展开、清理/恢复后调用） */
  const loadSlotView = async () => {
    await Promise.all([loadSlots(), loadRecycle()])
  }

  /** 折叠面板首次展开时才请求：非常用功能，不进页面首屏 */
  const handlePanelChange = (keys: string[] | string) => {
    const opened = Array.isArray(keys) ? keys.length > 0 : Boolean(keys)
    if (opened && !slotLoaded.value) {
      slotLoaded.value = true
      void loadSlotView()
    }
  }

  const cleanOrphanSlots = async () => {
    slotsLoading.value = true
    try {
      const resp = await Service.cleanZzzodSlotsApiApiScriptsZzzodSlotsCleanPost({
        scriptId: scriptId(),
      })
      if (resp.code !== 200) {
        throw new Error(resp.message || t('edit.zzzodSlotsCleanFailed'))
      }
      message.success(t('edit.zzzodSlotsCleanDone', { count: (resp.data || []).length }))
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('edit.zzzodSlotsCleanFailed'))
    } finally {
      slotsLoading.value = false
      await loadSlotView()
    }
  }

  /** 清理无主槽：内容会先归档到回收池，仍属破坏性操作，需二次确认 */
  const confirmCleanOrphanSlots = () => {
    const count = slots.value.filter(item => item.kind === 'orphan' && item.has_dir).length
    if (!count) {
      message.info(t('edit.zzzodSlotsCleanNone'))
      return
    }
    Modal.confirm({
      title: t('edit.zzzodSlotsClean'),
      content: t('edit.zzzodSlotsCleanConfirm', { count }),
      okText: t('edit.zzzodSlotsClean'),
      okButtonProps: { danger: true },
      onOk: () => cleanOrphanSlots(),
    })
  }

  /** 在文件管理器里打开回收条目的归档目录（便于核对或手动找回文件） */
  const openRecycleFolder = async (entry: ZzzOdRecycleEntryOut) => {
    try {
      if (!window.electronAPI?.openFile) return
      const result = await window.electronAPI.openFile(entry.path)
      if (result && !result.success) {
        message.error(result.error || t('edit.zzzodRecycleOpenFailed'))
      }
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }

  const clearRecyclePool = async () => {
    recycleLoading.value = true
    try {
      const resp = await Service.clearZzzodRecycleApiApiScriptsZzzodRecycleClearPost({
        scriptId: scriptId(),
      })
      if (resp.code !== 200) {
        throw new Error(resp.message || t('edit.zzzodRecycleClearFailed'))
      }
      message.success(t('edit.zzzodRecycleClearDone', { count: resp.data ?? 0 }))
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('edit.zzzodRecycleClearFailed'))
    } finally {
      recycleLoading.value = false
      await loadSlotView()
    }
  }

  /** 清空回收池不可找回（恢复历史一并删除），需二次确认 */
  const confirmClearRecycle = () => {
    const totalSize = recycleRows.value.reduce((sum, item) => sum + item.size, 0)
    Modal.confirm({
      title: t('edit.zzzodRecycleClear'),
      content: t('edit.zzzodRecycleClearConfirm', {
        count: recycleRows.value.length,
        size: formatSlotSize(totalSize),
      }),
      okText: t('edit.zzzodRecycleClear'),
      okButtonProps: { danger: true },
      onOk: () => clearRecyclePool(),
    })
  }

  const restoring = ref(false)

  /** 目标槽是否被原生实例或 MAS 用户占用（与后端守卫同口径：孤儿槽视为空闲） */
  const slotOccupied = (idx: number) => {
    const row = slots.value.find(item => item.idx === idx)
    return Boolean(row && row.kind !== 'orphan')
  }

  /** 占用者描述（原生实例或绑定该槽的用户），用于冲突提示点名 */
  const slotOccupantText = (idx: number) => {
    const row = slots.value.find(item => item.idx === idx)
    if (!row) return ''
    return row.kind === 'native' ? t('edit.zzzodSlotKindNative') : slotOwnerText(row)
  }

  /** 恢复槽快照到目标槽号（覆盖性操作：后端先存底当前内容再替换） */
  const restoreRecycle = async (
    entry: ZzzOdRecycleEntryOut,
    options: { targetSlot?: number; force?: boolean } = {}
  ) => {
    restoring.value = true
    const dest = options.targetSlot ?? entry.slot
    try {
      const resp = await Service.restoreZzzodRecycleApiApiScriptsZzzodRecycleRestorePost({
        scriptId: scriptId(),
        slot: entry.slot,
        ts: entry.ts,
        targetSlot: options.targetSlot,
        force: options.force,
      })
      if (resp.code !== 200) {
        throw new Error(resp.message || t('edit.zzzodRecycleRestoreFailed'))
      }
      message.success(t('edit.zzzodRecycleRestoreDone', { slot: String(dest).padStart(2, '0') }))
      return true
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('edit.zzzodRecycleRestoreFailed'))
      return false
    } finally {
      // 先刷新再复位：复位过早会让弹窗在两次 GET 期间解除 loading，
      // 用户再点一次 OK 就是重复提交覆盖性恢复
      await loadSlotView()
      restoring.value = false
    }
  }

  /** 原槽被占用时的两个去处：强制覆盖（先存底）或换到其他空闲槽号 */
  const restoreConflict = reactive({
    open: false,
    entry: null as ZzzOdRecycleEntryOut | null,
    mode: 'force' as 'force' | 'other',
    targetSlot: undefined as number | undefined,
  })

  const freeSlotOptions = computed(() => {
    const occupied = new Set(
      slots.value.filter(item => item.kind !== 'orphan').map(item => item.idx)
    )
    // 可复用的无主残留 + 几个新空号，都只取 MAS 号段：低号段是一条龙
    // 「升序找最小空号」的地盘，把快照恢复进去迟早会被它抢走覆盖
    const free = new Set(
      slots.value
        .filter(item => item.kind === 'orphan' && item.idx >= MAS_SLOT_BASE)
        .map(item => item.idx)
    )
    let next = Math.max(MAS_SLOT_BASE, ...slots.value.map(item => item.idx + 1))
    while (free.size < 4) {
      if (!occupied.has(next)) free.add(next)
      next += 1
    }
    return [...free]
      .sort((a, b) => a - b)
      .map(idx => {
        const row = slots.value.find(item => item.idx === idx)
        const label = String(idx).padStart(2, '0')
        return {
          value: idx,
          label: row
            ? `${label}（${t('edit.zzzodSlotKindOrphan')}·${formatSlotSize(row.size ?? 0)}）`
            : `${label}（${t('edit.zzzodRecycleRestoreEmptySlot')}）`,
        }
      })
  })

  const submitRestoreConflict = async () => {
    const entry = restoreConflict.entry
    if (!entry) return
    const targetSlot = restoreConflict.mode === 'other' ? restoreConflict.targetSlot : undefined
    if (restoreConflict.mode === 'other' && !targetSlot) {
      message.warning(t('edit.zzzodRecycleRestoreOtherRequired'))
      return
    }
    const done = await restoreRecycle(entry, {
      targetSlot,
      force: restoreConflict.mode === 'force',
    })
    if (done) restoreConflict.open = false
  }

  /** 恢复确认文案按目标槽现场分三态：被占用 / 有内容（无主残留）/ 空槽。
   *  无主残留按设计视为空闲（可被恢复重新认领），但覆盖它仍是替换性操作，
   *  必须把「这里现在有东西」说清楚，不能与「空槽新建」混为一谈 */
  const restoreConfirmContent = (slotIdx: number) => {
    const slot = String(slotIdx).padStart(2, '0')
    if (slotOccupied(slotIdx)) {
      return t('edit.zzzodRecycleRestoreConfirmOccupied', {
        slot,
        occupant: slotOccupantText(slotIdx),
      })
    }
    const row = slots.value.find(item => item.idx === slotIdx)
    return row
      ? t('edit.zzzodRecycleRestoreConfirmOverwrite', {
          slot,
          size: formatSlotSize(row.size ?? 0),
        })
      : t('edit.zzzodRecycleRestoreConfirmEmpty', { slot })
  }

  /** 恢复槽快照是覆盖性操作，需二次确认；原槽被占用时改为选择去处 */
  const confirmRestoreRecycle = (entry: ZzzOdRecycleEntryOut) => {
    const occupied = slotOccupied(entry.slot)
    const overwrites = !occupied && slots.value.some(item => item.idx === entry.slot)
    Modal.confirm({
      title: t('edit.zzzodRecycleRestore'),
      content: restoreConfirmContent(entry.slot),
      okText: t('edit.zzzodRecycleRestore'),
      okButtonProps: { danger: overwrites },
      onOk: async () => {
        if (!occupied) {
          await restoreRecycle(entry)
          return
        }
        restoreConflict.entry = entry
        restoreConflict.mode = 'force'
        restoreConflict.targetSlot = undefined
        restoreConflict.open = true
      },
    })
  }

  return {
    panelKeys,
    slotTab,
    slots,
    slotsLoading,
    recycleRows,
    recycleLoading,
    slotActionBusy,
    slotColumns,
    recycleColumns,
    recycleTabLabel,
    slotKindLabel,
    slotKindColor,
    slotNativeConflict,
    slotOwnerText,
    slotOccupantText,
    recycleKindLabel,
    formatSlotSize,
    formatArchiveTs,
    loadSlotView,
    handlePanelChange,
    confirmCleanOrphanSlots,
    openRecycleFolder,
    confirmClearRecycle,
    restoring,
    restoreConflict,
    freeSlotOptions,
    submitRestoreConflict,
    confirmRestoreRecycle,
  }
}
