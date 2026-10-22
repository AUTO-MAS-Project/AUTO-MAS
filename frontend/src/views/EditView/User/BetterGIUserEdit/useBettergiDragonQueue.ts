import { computed, ref, watch, toValue, type Ref, type MaybeRefOrGetter } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { BetterGiService, type BetterGIUserConfig_OneDragon } from '@/api'
import { useBettergiCustomGroups } from '@/composables/useBettergiCustomGroups'
import {
  ONE_DRAGON_GROUPS,
  STAMINA_COMBAT_VISIBLE,
  STAMINA_COMBAT_KEY,
  STAMINA_FROZEN_BUILTINS,
  ALLOW_DUPLICATE_GROUPS,
  type ConfigGroupIdentity,
  type ConfigGroupKind,
} from './bettergiQueueIdentity'
import type { useBettergiCatalogs } from './useBettergiCatalogs'
type QueueDraft = {
  [K in keyof BetterGIUserConfig_OneDragon]-?: NonNullable<BetterGIUserConfig_OneDragon[K]>
}
export function useBettergiDragonQueue(options: {
  scriptId: string
  userId: Ref<string>
  oneDragon: () => QueueDraft
  configName: MaybeRefOrGetter<string>
  masEnabled: Ref<boolean>
  locked: Ref<boolean>
  catalogs: ReturnType<typeof useBettergiCatalogs>
  saveField: (key: string, value: unknown) => Promise<boolean>
}) {
  const {
    scriptId,
    userId,
    oneDragon,
    masEnabled: masConfigEnabled,
    locked: configLocked,
    saveField,
  } = options
  const { isJsScriptName, isScriptGroupName, isKeyMouseName, isPathingName } = options.catalogs
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('BetterGI用户编辑')
  // ----- 自定义配置组管理（composable）-----
  const {
    table: customGroupsTable,
    selectedKeys: selectedCustomGroupKeys,
    syncFromForm: syncCustomGroupsFromForm,
    loadFromBettergi: loadCustomGroupsFromBettergi,
    listFromBettergi: listBgiCustomGroups,
    toggleMaster: toggleCustomGroupsMaster,
    deleteSelected: deleteSelectedCustomGroups,
    toggleEnabled: toggleCustomGroupEnabled,
    addByName: addCustomGroupByName,
  } = useBettergiCustomGroups({
    scriptId,
    userId: () => userId.value,
    oneDragon: () => oneDragon(),
    configName: () =>
      masConfigEnabled.value ? 'MAS独立配置' : toValue(options.configName) || '默认配置',
    masConfig: () => masConfigEnabled.value,
    editable: () => masConfigEnabled.value,
    saveField,
  })
  // 快速配置开关已隐藏（按配置来源派生），原先「关闭前先落盘一条龙组设置」的处理
  // 移到了 handleConfigModeChange：切到原生来源时 MAS 面板会隐藏，效果等同。
  const toggleGroup = (value: string) => {
    if (!masConfigEnabled.value) return
    const set = new Set(oneDragon().Groups)
    if (set.has(value)) {
      set.delete(value)
    } else {
      set.add(value)
    }
    // 按内置顺序排序，保持后端一条龙 TaskOrder 稳定
    const groups = ONE_DRAGON_GROUPS.map(g => g.value).filter(v => set.has(v))
    const prev = oneDragon().Groups
    oneDragon().Groups = groups
    void saveField('OneDragon.Groups', groups).then(ok => {
      // 保存失败必须回滚并提示：否则界面显示与后端数据脱节（运行时按旧数据执行，
      // 出现「界面开着、实际没跑」的静默不一致，直到重新进入页面才被发现）
      if (!ok) {
        oneDragon().Groups = prev
        message.error(`组开关「${value}」保存失败，已还原，请重试`)
      }
    })
  }

  // 队列行 uid 自增计数器
  let dragonRowSeq = 0

  // 当前一条龙队列（有序身份列表，顺序即执行顺序）
  const dragonList = ref<ConfigGroupIdentity[]>([])

  // 体力作战是否已加入一条龙（本地虚拟项，默认加入）
  const staminaInDragon = ref(STAMINA_COMBAT_VISIBLE)

  // 体力作战启用开关（本地虚拟项，不落库）
  const staminaCombatEnabled = ref(false)

  // 启用体力作战前的记忆快照：记录受影响内置组原本是否启用，用于关闭体力后恢复
  const staminaFrozenSnapshot = ref<Record<string, boolean>>({})

  // 当前选中的队列行（右侧面板展示）
  const selectedGroupIdentity = ref<ConfigGroupIdentity | null>(null)

  // 左侧是否可编辑/可展示列表（受「MAS 独立配置」总开关约束）
  const groupsEditable = computed(() => masConfigEnabled.value)

  const groupsShowCustom = computed(() => oneDragon().IfUseCustomGroups && masConfigEnabled.value)

  // 战斗 4 项（秘境/地脉花/幽境危战/首领讨伐）支持「同组多实例」：每个实例独立开关与设置，
  // 运行时经执行层（Plan）逐实例生效。其余组仍走全局开关（Groups / 自定义表），不进入 Plan。
  const COMBAT_BUILTIN_SET = new Set<string>([
    '自动秘境',
    '自动地脉花',
    '自动幽境危战',
    '自动首领讨伐',
  ])

  // 某队列实例在执行层 Plan 中的步骤名。
  // 与「后名」彻底解耦：后名仅作前端展示区分，身份由**行实例 uid** 决定——
  //   1) 未设后名的重复实例同样各自独立（否则同名会落到同一 Plan 步骤而共享设置）；
  //   2) 改后名不会改变步骤名，已保存的每实例设置不会丢失。
  // uid 最小者沿用基名（兼容旧 Plan 中已存在的「自动秘境」步骤），其余为「基名-uid」。
  const stepNameIn = (row: ConfigGroupIdentity, rows: ConfigGroupIdentity[]): string => {
    // 体力作战是本地虚拟项，无实例概念
    if (row.kind === 'stamina') return row.key
    // 战斗组的实例命名规则推广到全部可重复配置组：uid 最小者沿用基名（兼容旧 Plan 中
    // 已存在的「自动秘境」步骤），其余为「基名-{uid}」。自定义组由此获得每实例身份，
    // 开关与设置各自独立（与「后名」解耦：后名仅作显示别名）。
    const uids = rows.filter(i => i.kind === row.kind && i.key === row.key).map(i => i.uid ?? 0)
    const firstUid = uids.length ? Math.min(...uids) : (row.uid ?? 0)
    return row.uid === firstUid ? row.key : `${row.key}-${row.uid}`
  }

  const stepNameOf = (row: ConfigGroupIdentity): string => stepNameIn(row, dragonList.value)

  // 解析 OneDragon.Plan 中的步骤数组（兼容字符串 JSON / 对象 / 裸数组）
  const parsePlanSteps = (raw: unknown): Array<Record<string, any>> => {
    if (!raw) return []
    let obj: any = raw
    if (typeof raw === 'string') {
      try {
        obj = JSON.parse(raw)
      } catch {
        return []
      }
    }
    if (Array.isArray(obj)) return obj
    if (obj && Array.isArray(obj.steps)) return obj.steps
    return []
  }

  // 读取 Plan 中各步骤的启用状态（按步骤名索引），用于初始化队列行的 per-instance 启停
  const readPlanEnabled = (): Map<string, boolean> => {
    const m = new Map<string, boolean>()
    for (const s of parsePlanSteps((oneDragon() as any)?.Plan)) {
      if (s && typeof s.name === 'string') m.set(s.name, s.enabled !== false)
    }
    return m
  }

  // 乐观更新内存中的 Plan 步骤启用状态（下次读取/落库前保持界面一致）
  const updatePlanStepEnabled = (name: string, enabled: boolean) => {
    const steps = parsePlanSteps((oneDragon() as any)?.Plan)
    let changed = false
    for (const s of steps) {
      if (s && s.name === name) {
        s.enabled = enabled
        changed = true
        break
      }
    }
    if (changed) (oneDragon() as any).Plan = JSON.stringify({ version: 1, steps })
  }

  // 调用后端：按步骤名翻转 Plan 中某战斗实例的启用状态
  const setPlanStepEnabled = async (name: string, enabled: boolean): Promise<void> => {
    if (!scriptId || !userId.value || configLocked.value) return
    try {
      const resp =
        await BetterGiService.setOneDragonPlanStepEnabledApiScriptsBettergiOneDragonPlanStepEnabledPost(
          scriptId,
          userId.value,
          name,
          enabled
        )
      // 后端以 HTTP 200 + body.code 表达失败，需显式判定，否则开关静默不落库
      if (resp.code !== 200) {
        logger.error(resp.message || '一条龙步骤启用状态保存失败')
      }
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }

  // 「配置组名称」（前名）是否锁定：默认（内置 8 组）与专项（体力作战）沿用系统固定名，
  // 只允许改「名称备注」；其余来源（配置组 / JS 脚本 / 路径 / 录制 / 自定义）可自定义前名。
  const isNameLocked = (item: ConfigGroupIdentity): boolean =>
    item.kind === 'builtin' || item.kind === 'stamina'

  // 是否被体力作战冻结（启用体力作战时三个刷取内置组冻结）
  const isGroupFrozen = (item: ConfigGroupIdentity): boolean =>
    item.kind === 'builtin' &&
    staminaCombatEnabled.value &&
    STAMINA_FROZEN_BUILTINS.includes(item.key)

  const groupEnabled = (item: ConfigGroupIdentity): boolean => {
    // 战斗 4 项：每实例独立启停（来自 Plan step.enabled）
    if (item.kind === 'builtin' && COMBAT_BUILTIN_SET.has(item.key)) {
      return item.enabled !== false
    }
    if (item.kind === 'builtin') return oneDragon().Groups.includes(item.key)
    if (item.kind === 'stamina') return staminaCombatEnabled.value
    // 自定义组：每实例独立启停（行实例自带 enabled），与战斗组实例行为一致
    return item.enabled !== false
  }

  // 队列是否包含某配置组
  const inDragon = (item: ConfigGroupIdentity): boolean =>
    dragonList.value.some(i => i.kind === item.kind && i.key === item.key)

  // 同步后端内置组启用集合（当前 Groups 含 enabled 列表 + 冻结时剔除冻结项）
  const applyGroupsPatch = (next: string[]) => {
    const prev = oneDragon().Groups
    oneDragon().Groups = next
    void saveField('OneDragon.Groups', next).then(ok => {
      // 保存失败回滚并提示，避免界面与后端静默脱节（与 toggleGroup 同理）
      if (!ok) {
        oneDragon().Groups = prev
        message.error('组开关保存失败，已还原，请重试')
      }
    })
  }

  // 从当前 Groups 中剔除指定内置组（冻结 / 删除共用）
  const removeBuiltinsFromGroups = (keys: string[]) => {
    const set = new Set(keys)
    const next = oneDragon().Groups.filter(g => !set.has(g))
    if (next.join('\u0001') !== oneDragon().Groups.join('\u0001')) {
      applyGroupsPatch(next)
    }
  }

  // 生成一条带唯一 uid 的队列行实例
  const makeDragonRow = (item: ConfigGroupIdentity): ConfigGroupIdentity => ({
    ...item,
    enabled: item.enabled ?? true,
    // 持久化过的 uid 必须沿用：它是每实例设置/启停的身份，重开会撞号导致设置串台
    uid: item.uid ?? ++dragonRowSeq,
  })

  // 队列行去重辅助（仅用于初始化；允许重复时不用此函数）
  const pushDragon = (list: ConfigGroupIdentity[], item: ConfigGroupIdentity) => {
    if (!list.some(i => i.kind === item.kind && i.key === item.key)) list.push(makeDragonRow(item))
  }

  // 队列是否已初始化（初始化前的 appendCustomRows 不落库，避免把半成品队列写回）
  let dragonListReady = false

  // 读取已持久化的一条龙队列（OneDragon.Queue：JSON 数组，元素 {kind, name}）。
  // 生成 API 模型重新生成前该字段尚无类型声明，这里做宽松读取；缺失/非法按未持久化处理。
  const readStoredQueue = (): ConfigGroupIdentity[] => {
    const raw = (oneDragon() as unknown as Record<string, unknown>).Queue
    if (typeof raw !== 'string') return []
    let data: unknown
    try {
      data = JSON.parse(raw)
    } catch {
      return []
    }
    if (!Array.isArray(data)) return []
    const builtinNames = new Set(ONE_DRAGON_GROUPS.map(g => g.value))
    const rows: ConfigGroupIdentity[] = []
    for (const entry of data) {
      if (typeof entry !== 'object' || entry === null) continue
      const rec = entry as Record<string, unknown>
      const name = typeof rec.name === 'string' ? rec.name.trim() : ''
      if (!name) continue
      if (name === STAMINA_COMBAT_KEY) continue // 体力作战为本地虚拟项，不入持久化队列
      let kind: ConfigGroupKind
      if (builtinNames.has(name)) {
        kind = 'builtin' // 后端也会把内置组名强制归一为 builtin，这里双保险
      } else if (
        rec.kind === 'js' ||
        rec.kind === 'pathing' ||
        rec.kind === 'scriptgroup' ||
        rec.kind === 'keymouse'
      ) {
        kind = rec.kind
      } else {
        kind = resolveStoredRowKind(name)
      }
      const displayName = typeof rec.displayName === 'string' ? rec.displayName : undefined
      const suffix = typeof rec.suffix === 'string' ? rec.suffix : undefined
      const uid = typeof rec.uid === 'number' ? rec.uid : undefined
      const planUid = typeof rec.planUid === 'string' ? rec.planUid : undefined
      const enabled = typeof rec.enabled === 'boolean' ? rec.enabled : undefined
      rows.push(makeDragonRow({ kind, key: name, displayName, suffix, uid, planUid, enabled }))
    }
    // 第二遍：战斗组每实例启用状态来自 Plan；自定义组来自队列条目自带的 enabled。
    // 存量数据无该字段时回退按名查自定义组管理表，避免把用户已关闭的组误判为启用。
    const planEnabled = readPlanEnabled()
    for (const r of rows) {
      if (r.kind === 'builtin' && COMBAT_BUILTIN_SET.has(r.key)) {
        r.enabled = planEnabled.get(stepNameIn(r, rows)) ?? true
      } else if (r.kind !== 'builtin' && r.kind !== 'stamina' && r.enabled === undefined) {
        r.enabled = customGroupsTable.value.find(x => x.name === r.key)?.enabled ?? true
      }
    }
    // uid 已持久化：让自增序号跳过已用值，避免新行与既有行 uid 撞号
    for (const r of rows) {
      if (typeof r.uid === 'number' && r.uid > dragonRowSeq) dragonRowSeq = r.uid
    }
    return rows
  }

  // 把当前队列顺序/成员落库（体力作战行不持久化；运行时后端按此重建 TaskOrder）
  const persistDragonQueue = () => {
    if (!dragonListReady || !groupsEditable.value) return
    // 战斗实例解析其 Plan 步骤 uid（按行实例的步骤名精确对应）；非战斗行无 planUid。
    // 后端 build_combat_steps 按 planUid 精确匹配 Plan 步骤——同名多实例（「自动秘境」×3）
    // 的拖拽顺序据此逐实例生效，不再退化为按 Plan 原顺序 FIFO。
    const planSteps = parsePlanSteps((oneDragon() as any)?.Plan)
    const entries = dragonList.value
      .filter(i => i.kind !== 'stamina')
      .map(i => {
        let planUid: string | undefined
        const stepName = stepNameIn(i, dragonList.value)
        if (i.kind === 'builtin' && COMBAT_BUILTIN_SET.has(i.key)) {
          planUid = planSteps.find(s => s && s.name === stepName)?.uid
        }
        const entry: Record<string, unknown> = {
          kind: i.kind,
          name: i.key,
          displayName: i.displayName,
          suffix: i.suffix,
          uid: i.uid,
          planUid,
        }
        // 实例名（组名-{uid}）：非首实例才有，供后端定位该实例独立的设置副本。
        // 内置组不写：BGI 一条龙只认内置基名，实例名会导致任务无法识别。
        if (stepName !== i.key && i.kind !== 'builtin') entry.step = stepName
        // 自定义组每实例开关（战斗组启用状态走 Plan，不写此字段）
        if (i.kind !== 'builtin') entry.enabled = i.enabled !== false
        return entry
      })
    void saveField('OneDragon.Queue', JSON.stringify(entries))
    // 存在战斗实例时确保执行层开启：否则 Plan 中的 per-instance 设置/启停不会被运行时消费
    const draft = oneDragon()
    const hasCombat = dragonList.value.some(
      i => i.kind === 'builtin' && COMBAT_BUILTIN_SET.has(i.key)
    )
    if (hasCombat && draft.UseExecutionLayer !== true) {
      draft.UseExecutionLayer = true
      void saveField('OneDragon.UseExecutionLayer', true)
    }
  }

  // 依据用户数据初始化一条龙队列（loadUser 后调用一次，随后由增删/拖拽维护）：
  // 已持久化队列优先（顺序与成员、含重复实例原样恢复）；否则种子 =
  // 8 内置（默认在列，enabled 由 Groups 表达）+ 体力作战（默认在列，默认关闭）。
  // 默认顺序：领取邮件 → 领取尘歌壶奖励 → 合成树脂 → 体力作战 → 自动幽境危战 →
  //           自动地脉花 → 自动首领讨伐 → 自动秘境 → 领取每日奖励
  const initDragonList = () => {
    const stored = readStoredQueue()
    if (stored.length) {
      dragonList.value = stored
    } else {
      const order: ConfigGroupIdentity[] = []
      for (const g of ONE_DRAGON_GROUPS) {
        // 体力作战固定插入第 3 位：即「合成树脂」之后、「自动幽境危战」之前
        if (staminaInDragon.value && g.value === '自动幽境危战') {
          pushDragon(order, { kind: 'stamina', key: STAMINA_COMBAT_KEY })
        }
        pushDragon(order, { kind: 'builtin', key: g.value })
      }
      // 兜底：若「自动幽境危战」不在内置列表（理论不发生），体力作战追加到末尾避免丢失
      if (staminaInDragon.value && !order.some(i => i.kind === 'stamina')) {
        pushDragon(order, { kind: 'stamina', key: STAMINA_COMBAT_KEY })
      }
      // 自定义组仅在总开关开启时并入（来自 BetterGI 现有配置 / CustomGroups）
      if (groupsShowCustom.value) {
        for (const row of customGroupsTable.value) {
          // 仅真实自定义组并入队列；路径/录制/ScriptGroup 各有独立入队口径，不在此镜像
          if (resolveStoredRowKind(row.name) !== 'custom') continue
          pushDragon(order, { kind: 'custom', key: row.name })
        }
      }
      // 与 readStoredQueue 第二遍一致：战斗组每实例启用态来自 Plan，自定义组缺省按管理表回退。
      // 新用户（无持久化队列）必须在此回显，否则战斗开关恒为默认开启、关闭后刷新即回弹
      // （一旦手动加一项使队列非空、走 if 分支才会正确显示，正是此 bug 的表象）。
      const planEnabledInit = readPlanEnabled()
      for (const r of order) {
        if (r.kind === 'builtin' && COMBAT_BUILTIN_SET.has(r.key)) {
          r.enabled = planEnabledInit.get(stepNameIn(r, order)) ?? true
        } else if (r.kind !== 'builtin' && r.kind !== 'stamina' && r.enabled === undefined) {
          r.enabled = customGroupsTable.value.find(x => x.name === r.key)?.enabled ?? true
        }
      }
      dragonList.value = order
    }
    dragonListReady = true
    // 持久化队列里没有、而 BetterGI 侧新增的自定义组仍补入队列末尾
    appendCustomRows()
  }

  // 由存储的自定义组名推断队列行来源类型：命中 JS 脚本目录→js；命中录制目录→keymouse；
  // 命中 AutoPathing 文件→pathing；命中 ScriptGroup 配置组目录→scriptgroup；其余→custom
  const resolveStoredRowKind = (name: string): ConfigGroupKind => {
    if (isJsScriptName(name)) return 'js'
    if (isKeyMouseName(name)) return 'keymouse'
    if (isPathingName(name)) return 'pathing'
    if (isScriptGroupName(name)) return 'scriptgroup'
    return 'custom'
  }

  // 把 BetterGI 侧新增的自定义组补入队列末尾（保留用户已删除的自定义组不回来）
  const appendCustomRows = () => {
    if (!dragonListReady || !groupsShowCustom.value) return
    let appended = false
    for (const row of customGroupsTable.value) {
      // 仅真实自定义组镜像进队列；路径/录制/ScriptGroup 名各有独立入队口径，避免被当成配置组补进一条龙
      if (resolveStoredRowKind(row.name) !== 'custom') continue
      const item: ConfigGroupIdentity = { kind: 'custom', key: row.name }
      if (!inDragon(item)) {
        dragonList.value.push(makeDragonRow(item))
        appended = true
      }
    }
    if (appended) persistDragonQueue()
  }

  // 供 draggable v-model 使用（纯前端顺序）
  const dragonListModel = computed<ConfigGroupIdentity[]>({
    get: () => dragonList.value,
    set: value => {
      dragonList.value = value
    },
  })

  // ---- 开关 ----
  // 开启/关闭体力作战（含互斥冻结/解冻 + 记忆恢复）
  const toggleStaminaCombat = () => {
    const next = !staminaCombatEnabled.value
    if (next) {
      // 启用体力作战：先记忆受影响组原本的启用状态，再自动关闭（冻结）
      staminaFrozenSnapshot.value = Object.fromEntries(
        STAMINA_FROZEN_BUILTINS.map(name => [name, oneDragon().Groups.includes(name)])
      )
      removeBuiltinsFromGroups(STAMINA_FROZEN_BUILTINS)
    } else {
      // 关闭体力作战：按记忆恢复原本开启的组（记忆为空则不误改）
      const toRestore = STAMINA_FROZEN_BUILTINS.filter(name => staminaFrozenSnapshot.value[name])
      if (toRestore.length) {
        const nextGroups = [...new Set([...oneDragon().Groups, ...toRestore])]
        applyGroupsPatch(nextGroups)
      }
      staminaFrozenSnapshot.value = {}
    }
    staminaCombatEnabled.value = next
  }

  // 移除体力作战（右键移出）时同样按记忆恢复受影响组
  const restoreStaminaFrozen = () => {
    const toRestore = STAMINA_FROZEN_BUILTINS.filter(name => staminaFrozenSnapshot.value[name])
    if (toRestore.length) {
      applyGroupsPatch([...new Set([...oneDragon().Groups, ...toRestore])])
    }
    staminaFrozenSnapshot.value = {}
    staminaCombatEnabled.value = false
  }

  // 清空整条一条龙：清掉队列、后端内置组/自定义组，并关闭体力作战（不做冻结组恢复）
  const clearDragon = () => {
    dragonList.value = []
    staminaInDragon.value = false
    staminaCombatEnabled.value = false
    staminaFrozenSnapshot.value = {}
    applyGroupsPatch([])
    if (oneDragon().CustomGroups !== '[]') {
      oneDragon().CustomGroups = '[]'
      void saveField('OneDragon.CustomGroups', '[]')
    }
    selectedGroupIdentity.value = null
    persistDragonQueue()
  }

  // 行开关：内置写 Groups、体力作战本地翻转（互斥）、自定义交给 composable 持久化
  const toggleConfigGroup = (item: ConfigGroupIdentity) => {
    if (!groupsEditable.value) return
    if (isGroupFrozen(item)) return
    // 战斗 4 项：每实例独立启停（写入 Plan step.enabled），基名仍保留在 Groups 供运行时纳入
    if (item.kind === 'builtin' && COMBAT_BUILTIN_SET.has(item.key)) {
      const next = !(item.enabled !== false)
      item.enabled = next
      updatePlanStepEnabled(stepNameOf(item), next)
      void setPlanStepEnabled(stepNameOf(item), next)
      return
    }
    if (item.kind === 'builtin') {
      toggleGroup(item.key)
    } else if (item.kind === 'stamina') {
      toggleStaminaCombat()
    } else {
      // 自定义组：翻转本行实例的 enabled 并落库（每实例独立，不再按名共用开关）
      item.enabled = !(item.enabled !== false)
      persistDragonQueue()
    }
  }

  // ---- 添加：把配置组加入一条龙（放到队列末尾）----
  const addToDragon = (item: ConfigGroupIdentity): boolean => {
    if (configLocked.value) {
      message.error(t('edit.configLocked'))
      return false
    }
    if (!groupsEditable.value) return false
    if (!ALLOW_DUPLICATE_GROUPS && inDragon(item)) return false
    // 体力作战开启时刷取类官方内置组被冻结，禁止再次加入一条龙（防止把被接管的组写回后端 Groups）
    if (item.kind === 'builtin' && isGroupFrozen(item)) {
      message.warning(t('edit.bettergiGroupFrozenTip'))
      return false
    }
    if (item.kind === 'builtin') {
      if (!oneDragon().Groups.includes(item.key)) {
        applyGroupsPatch([...oneDragon().Groups, item.key])
      }
    } else if (item.kind === 'stamina') {
      staminaInDragon.value = true
    } else if (item.kind === 'pathing' || item.kind === 'keymouse') {
      // 路径/录制为独立队列项，不写入 CustomGroups（避免被当成自定义配置组污染一条龙）
    } else {
      // 自定义组：确保进入 CustomGroups（启用）并打开总开关
      if (addCustomGroupByName(item.key)) {
        if (!oneDragon().IfUseCustomGroups) toggleCustomGroupsMaster()
      } else {
        const row = customGroupsTable.value.find(r => r.name === item.key)
        if (row && !row.enabled) toggleCustomGroupEnabled(row)
      }
    }
    // 追加到队列末尾：生成带唯一 uid 的行实例（重复开关开启时允许同一配置多次添加）。
    // 同组已有自定义前名时沿用到新实例，避免队列里同一个配置组显示两个名字。
    const alias = dragonList.value.find(
      i => i.kind === item.kind && i.key === item.key
    )?.displayName
    dragonList.value.push(makeDragonRow(alias ? { ...item, displayName: alias } : item))
    persistDragonQueue()
    return true
  }

  // 队列中是否仍存在同类配置组（删除某实例后判断是否还保留后端启用）
  const hasSameKindRow = (item: ConfigGroupIdentity, exceptUid?: number): boolean =>
    dragonList.value.some(i => i.uid !== exceptUid && i.kind === item.kind && i.key === item.key)

  // ---- 右键删除：从一条龙移除（按行实例 uid，一次只删一行）----
  const removeFromDragon = (item: ConfigGroupIdentity) => {
    if (!groupsEditable.value) return
    if (configLocked.value) {
      message.error(t('edit.configLocked'))
      return
    }
    if (item.kind === 'builtin') {
      if (isGroupFrozen(item)) return // 冻结中不可删除
      dragonList.value = dragonList.value.filter(i => i.uid !== item.uid)
      if (!hasSameKindRow(item, item.uid)) {
        removeBuiltinsFromGroups([item.key])
      }
    } else if (item.kind === 'stamina') {
      dragonList.value = dragonList.value.filter(i => i.uid !== item.uid)
      if (!hasSameKindRow(item, item.uid)) {
        staminaInDragon.value = false
        restoreStaminaFrozen() // 最后一个体力作战被移除：恢复受影响组
      }
    } else {
      dragonList.value = dragonList.value.filter(i => i.uid !== item.uid)
      // 仅当这是最后一个同配置实例时才从 CustomGroups 移除
      if (!hasSameKindRow(item, item.uid)) {
        const row = customGroupsTable.value.find(r => r.name === item.key)
        if (row) {
          selectedCustomGroupKeys.value = [row.name]
          void deleteSelectedCustomGroups()
        }
      }
    }
    if (selectedGroupIdentity.value && selectedGroupIdentity.value.uid === item.uid) {
      selectedGroupIdentity.value = null
    }
    persistDragonQueue()
  }

  // 右侧选中行：展示该配置组详情
  const selectConfigGroup = (item: ConfigGroupIdentity) => {
    selectedGroupIdentity.value = { ...item }
  }

  // ---- 监听：BetterGI 现有自定义组在总开关开启时并入队列末尾 ----
  watch(
    () => customGroupsTable.value.map(r => r.name).join('\u0001'),
    () => appendCustomRows(),
    { immediate: true }
  )

  watch(
    () => masConfigEnabled.value,
    () => {
      if (!masConfigEnabled.value) selectedGroupIdentity.value = null
    }
  )
  return {
    customGroupsTable,
    syncCustomGroupsFromForm,
    loadCustomGroupsFromBettergi,
    listBgiCustomGroups,
    dragonList,
    selectedGroupIdentity,
    groupsEditable,
    groupsShowCustom,
    stepNameOf,
    isNameLocked,
    isGroupFrozen,
    groupEnabled,
    inDragon,
    persistDragonQueue,
    initDragonList,
    resolveStoredRowKind,
    dragonListModel,
    clearDragon,
    toggleConfigGroup,
    addToDragon,
    removeFromDragon,
    selectConfigGroup,
  }
}
