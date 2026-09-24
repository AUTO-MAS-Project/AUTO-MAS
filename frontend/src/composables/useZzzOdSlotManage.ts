import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import { formatBytes } from '@/utils/byteFormat'
import { Service, type ZzzOdRecycleEntryOut, type ZzzOdSlotOut } from '@/api'

/**
 * 实例槽管理（脚本设置页的实例槽 / 回收池两张表与恢复流程）。
 *
 * 槽目录是 MAS 分配在一条龙安装目录里的 ``config/{idx:02d}``，一条龙注册表与
 * GUI 都看不到；这份对照表用于看清「槽目录数与用户数对不上」（绑定但没跑过的槽
 * 没有目录），回收池则是被删用户/脚本留下的槽内容与备份池快照。恢复的落点是
 * **某个用户的绑定槽**（现有用户或新建用户）——只物化内容而不建立绑定的恢复
 * 没有出口，MAS 下次运行不会认领它。表格、清理与恢复弹窗的状态与动作都收在
 * 这里，组件只负责渲染。
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
          .map(item =>
            t('edit.zzzodSlotOwnerItem', {
              user: item.userName,
              script: item.scriptName,
              mode: slotOwnerModeLabel(item.mode),
            })
          )
          .join(t('edit.zzzodSlotOwnerJoiner'))
      : '—'

  const recycleKindLabel = (kind: string) =>
    kind === 'mas' ? t('edit.zzzodRecycleKindMas') : t('edit.zzzodRecycleKindSlot')

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
      // 抛异常也要让用户看见（与返回 !success 的分支同口径），不能只进日志
      message.error(t('edit.zzzodRecycleOpenFailed'))
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
        size: formatBytes(totalSize),
      }),
      okText: t('edit.zzzodRecycleClear'),
      okButtonProps: { danger: true },
      onOk: () => clearRecyclePool(),
    })
  }

  const restoring = ref(false)

  /** 恢复目标：某个现有用户（落到它的绑定槽）或新建一个用户 */
  const restoreTarget = reactive({
    open: false,
    entry: null as ZzzOdRecycleEntryOut | null,
    mode: 'existing' as 'existing' | 'new',
    userId: undefined as string | undefined,
    newUserName: '',
  })

  /** 当前脚本的用户（恢复目标候选）。恢复必须落到某个用户的绑定槽：
   *  只把内容物化到裸槽号的恢复没有出口，MAS 不会认领它 */
  const userOptions = ref<Array<{ value: string; label: string }>>([])
  const usersLoading = ref(false)

  const loadUsers = async () => {
    usersLoading.value = true
    try {
      const resp = await Service.getUserApiScriptsUserGetPost({
        scriptId: scriptId(),
      })
      if (resp.code !== 200) {
        throw new Error(resp.message || t('edit.zzzodSlotsLoadFailed'))
      }
      userOptions.value = resp.index.map(item => {
        const cfg = resp.data[item.uid] as { Info?: { Name?: string } } | undefined
        return { value: item.uid, label: cfg?.Info?.Name || item.uid }
      })
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('edit.zzzodSlotsLoadFailed'))
    } finally {
      usersLoading.value = false
    }
  }

  /** 选中用户当前的绑定槽号（0 = 还没有绑定槽，恢复会新建一个） */
  const restoreTargetSlot = computed(() => {
    if (restoreTarget.mode !== 'existing' || !restoreTarget.userId) return 0
    const row = slots.value.find(item =>
      item.owners?.some(owner => owner.userId === restoreTarget.userId)
    )
    return row?.idx ?? 0
  })

  /** 打开恢复弹窗（用户列表按需加载） */
  const openRestoreDialog = async (entry: ZzzOdRecycleEntryOut) => {
    restoreTarget.entry = entry
    restoreTarget.mode = 'existing'
    restoreTarget.userId = undefined
    restoreTarget.newUserName = t('edit.zzzodRecycleRestoreNewUserNameDefault')
    restoreTarget.open = true
    await loadUsers()
  }

  /** 恢复槽快照给目标用户（覆盖性操作：后端先存底目标槽当前内容再替换） */
  const restoreRecycle = async (
    entry: ZzzOdRecycleEntryOut,
    options: { targetUser?: string; newUserName?: string }
  ) => {
    restoring.value = true
    try {
      const resp = await Service.restoreZzzodRecycleApiApiScriptsZzzodRecycleRestorePost({
        scriptId: scriptId(),
        slot: entry.slot,
        ts: entry.ts,
        targetUser: options.targetUser,
        newUserName: options.newUserName,
      })
      if (resp.code !== 200) {
        throw new Error(resp.message || t('edit.zzzodRecycleRestoreFailed'))
      }
      message.success(t('edit.zzzodRecycleRestoreDone'))
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

  const submitRestore = async () => {
    const entry = restoreTarget.entry
    if (!entry) return
    if (restoreTarget.mode === 'existing') {
      if (!restoreTarget.userId) {
        message.warning(t('edit.zzzodRecycleRestoreUserRequired'))
        return
      }
      const done = await restoreRecycle(entry, { targetUser: restoreTarget.userId })
      if (done) restoreTarget.open = false
      return
    }
    const name = restoreTarget.newUserName.trim()
    if (!name) {
      message.warning(t('edit.zzzodRecycleRestoreNameRequired'))
      return
    }
    const done = await restoreRecycle(entry, { newUserName: name })
    if (done) restoreTarget.open = false
  }

  /** 恢复是覆盖性操作（目标用户已有绑定槽时替换其内容），需二次确认 */
  const confirmRestoreRecycle = (entry: ZzzOdRecycleEntryOut) => {
    Modal.confirm({
      title: t('edit.zzzodRecycleRestore'),
      content: t('edit.zzzodRecycleRestoreConfirm', {
        slot: String(entry.slot).padStart(2, '0'),
      }),
      okText: t('edit.zzzodRecycleRestore'),
      onOk: () => openRestoreDialog(entry),
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
    recycleKindLabel,
    formatBytes,
    formatArchiveTs,
    loadSlotView,
    handlePanelChange,
    confirmCleanOrphanSlots,
    openRecycleFolder,
    confirmClearRecycle,
    restoring,
    restoreTarget,
    restoreTargetSlot,
    userOptions,
    usersLoading,
    submitRestore,
    confirmRestoreRecycle,
  }
}
