import { computed, ref, shallowRef, watch, type ShallowRef } from 'vue'
import { GetService, PowerSignal, type GlobalConfig, type ScriptIndexItem } from '@/api'
import {
  fetchTaskTargetSnapshot,
  type TaskTarget,
  type TaskTargetSnapshot,
} from '@/composables/useTaskOptions'
import { getConfig, saveConfig } from '@/utils/config'
import type { SettingChangeHandler } from '@/views/setting/settingTypes'
import { mergeLegacyDesktopSessionTargets } from './desktopSessionTargets'
import { MAX_DESKTOP_SESSION_TARGETS } from '../../../electron/services/desktopSessionProtocol'

type Reason = NonNullable<ScriptIndexItem['desktopSessionReason']>

/** 词表 bootstrap.desktopSession 下的键，由卡片翻译。 */
export type DesktopSessionTargetIssue = 'powerAction' | 'targetMissing' | `reasons.${Reason}`

/** 托管行的启动方式：随分身启动（StartOnOpen）、单独启动（Targets）或两者。 */
export type DesktopSessionLaunchMode = 'startOnOpen' | 'standalone' | 'both'

type ListKey = 'Targets' | 'StartOnOpen'

export interface DesktopSessionTargetRow {
  id: string
  kind?: TaskTarget['kind']
  name: string
  issue?: DesktopSessionTargetIssue
  launchable: boolean
  /** 在单独启动清单 Targets 里。 */
  standalone: boolean
  /** 在一并启动清单 StartOnOpen 里。 */
  startOnOpen: boolean
  /** 队列和托管名单里认得这一条。 */
  known: boolean
}

interface Capability {
  supported: boolean
  reason: Reason
}

const hasPowerAction = (afterAccomplish?: PowerSignal) =>
  Boolean(afterAccomplish && afterAccomplish !== PowerSignal.NO_ACTION)

/**
 * 桌面分身的两份清单，都存在后端 GlobalConfig.DesktopSession，写入走设置页的保存链路：
 * Targets 是单独启动时进分身的托管，StartOnOpen 是「打开分身并启动任务」一并派发的队列和托管。
 * 卡片显示时读取一次队列和托管，逐个单查两份清单里托管的分身能力，
 * 并把旧版卡片勾选一次性并入 StartOnOpen（旧的执行会话由后端并入 Targets）。
 */
export function useDesktopSessionTargets(options: {
  settings: () => GlobalConfig
  save: SettingChangeHandler
  onAddRejected: (issue: DesktopSessionTargetIssue) => void
  onLoadFailed: () => void
}) {
  const snapshot = shallowRef<TaskTargetSnapshot>()
  const loading = ref(false)
  const adding = ref(false)
  const capabilities = ref<Record<string, Capability>>({})
  const pendingCapabilities = new Set<string>()

  // 保存未落盘前先按草稿显示，连续增删时以最新草稿为准；保存失败回到设置里的值。
  const drafts: Record<ListKey, ShallowRef<string[] | null>> = {
    Targets: shallowRef(null),
    StartOnOpen: shallowRef(null),
  }
  const list = (key: ListKey) =>
    computed(() => drafts[key].value ?? options.settings().DesktopSession?.[key] ?? [])
  const standalone = list('Targets')
  const startOnOpen = list('StartOnOpen')
  // 先按一并启动的派发顺序，再接只在单独启动清单里的托管。
  const ids = computed(() => [...new Set([...startOnOpen.value, ...standalone.value])])
  const atLimit = computed(() => ids.value.length >= MAX_DESKTOP_SESSION_TARGETS)

  const candidates = computed(() => {
    const listed = new Set(ids.value)
    return (snapshot.value?.targets ?? [])
      .filter(target => !listed.has(target.value.toLowerCase()))
      .map(target => ({ target, powerAction: hasPowerAction(target.afterAccomplish) }))
  })

  const findTarget = (id: string) =>
    snapshot.value?.targets.find(item => item.value.toLowerCase() === id)

  const rows = computed<DesktopSessionTargetRow[]>(() => {
    const known = new Map(
      (snapshot.value?.targets ?? []).map(target => [target.value.toLowerCase(), target])
    )
    const unavailable = new Map(
      (snapshot.value?.unavailableScripts ?? []).map(item => [item.uid.toLowerCase(), item.name])
    )
    const inStandalone = new Set(standalone.value)
    const inStartOnOpen = new Set(startOnOpen.value)
    return ids.value.map(id => {
      const target = known.get(id)
      const capability = capabilities.value[id]
      const unavailableName = unavailable.get(id)
      let issue: DesktopSessionTargetIssue | undefined
      if (target?.kind === 'queue' && hasPowerAction(target.afterAccomplish)) issue = 'powerAction'
      else if (target?.kind === 'script' && capability?.supported === false)
        issue = `reasons.${capability.reason}`
      else if (!target && unavailableName !== undefined) issue = 'reasons.plugin_unavailable'
      else if (!target && snapshot.value) issue = 'targetMissing'
      return {
        id,
        kind: target?.kind ?? (unavailableName !== undefined ? 'script' : undefined),
        name: target?.name ?? unavailableName ?? id,
        issue,
        launchable: Boolean(target) && !issue,
        standalone: inStandalone.has(id),
        startOnOpen: inStartOnOpen.has(id),
        known: Boolean(target),
      }
    })
  })
  // 一并启动交给后端预检：不支持分身的托管弹拆分确认，带电源操作的队列由后端跳过。
  const launchIds = computed(() =>
    rows.value.filter(row => row.startOnOpen && row.known).map(row => row.id)
  )

  async function load() {
    loading.value = true
    try {
      snapshot.value = await fetchTaskTargetSnapshot()
    } catch {
      options.onLoadFailed()
    } finally {
      loading.value = false
    }
  }

  async function readCapability(scriptId: string): Promise<Capability> {
    const response = await GetService.getScriptApiScriptsGetPost({ scriptId })
    if (response.code !== 200) throw new Error(response.message)
    const item = response.index[0]
    return {
      supported: item?.desktopSessionSupported === true,
      reason: item?.desktopSessionReason ?? 'unsupported_config',
    }
  }

  // 托管能力随配置变化，每次显示卡片重新单查；最多同时查 4 个。
  async function refreshCapabilities(scriptIds: string[]) {
    const queue = scriptIds.filter(
      id => !(id in capabilities.value) && !pendingCapabilities.has(id)
    )
    queue.forEach(id => pendingCapabilities.add(id))
    const worker = async () => {
      for (let id = queue.shift(); id !== undefined; id = queue.shift()) {
        try {
          // 先等结果再展开：并发的单查各自写回，不互相覆盖。
          const capability = await readCapability(id)
          capabilities.value = { ...capabilities.value, [id]: capability }
        } catch {
          // 读不到就不标原因，单独启动时后端仍会拦下不支持的托管。
        } finally {
          pendingCapabilities.delete(id)
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(4, queue.length) }, worker))
  }

  watch(
    [ids, snapshot],
    () => {
      const scripts = new Set(
        (snapshot.value?.targets ?? [])
          .filter(target => target.kind === 'script')
          .map(target => target.value.toLowerCase())
      )
      void refreshCapabilities(ids.value.filter(id => scripts.has(id)))
    },
    { immediate: true }
  )

  async function saveList(key: ListKey, next: string[]): Promise<boolean> {
    drafts[key].value = next
    let saved = false
    try {
      saved = await options.save('DesktopSession', key, next)
    } catch {
      // 保存失败由设置页统一提示。
    }
    if (drafts[key].value === next) drafts[key].value = null
    return saved
  }

  /** 单查托管能力（fresh 为 false 时先用已查到的），不支持就提示并返回 false。 */
  async function ensureSupported(target: TaskTarget, fresh: boolean): Promise<boolean> {
    const id = target.value.toLowerCase()
    let capability = fresh ? undefined : capabilities.value[id]
    if (!capability) {
      try {
        capability = await readCapability(target.value)
      } catch {
        options.onLoadFailed()
        return false
      }
      capabilities.value = { ...capabilities.value, [id]: capability }
    }
    if (!capability.supported) options.onAddRejected(`reasons.${capability.reason}`)
    return capability.supported
  }

  /** 加入清单：队列只进一并启动；托管先单查分身能力，不支持就不加入，支持则两者都进。 */
  async function add(value: unknown): Promise<boolean> {
    if (typeof value !== 'string' || atLimit.value) return false
    const id = value.toLowerCase()
    const target = findTarget(id)
    if (!target || ids.value.includes(id) || hasPowerAction(target.afterAccomplish)) return false
    if (target.kind === 'queue') return saveList('StartOnOpen', [...startOnOpen.value, id])
    adding.value = true
    try {
      // 加入时总是重查：能力随配置变化，查到的可能已经过期。
      if (!(await ensureSupported(target, true)) || ids.value.includes(id)) return false
    } finally {
      adding.value = false
    }
    // 先存一并启动再存单独启动：后一次失败时停在单独启动不进分身的一边。
    if (!(await saveList('StartOnOpen', [...startOnOpen.value, id]))) return false
    return saveList('Targets', [...standalone.value, id])
  }

  /**
   * 切换托管行的启动方式。两份清单各存一次，先加后撤，任一步失败就停：
   * 半途停下时这一行仍在卡片上，每份清单要么是原值，要么是所选的值。
   */
  async function setMode(id: string, mode: DesktopSessionLaunchMode): Promise<boolean> {
    const target = findTarget(id)
    if (target?.kind !== 'script' || adding.value) return false
    const wantStandalone = mode !== 'startOnOpen'
    const wantStartOnOpen = mode !== 'standalone'
    const without = (list: string[]) => list.filter(item => item !== id)
    adding.value = true
    try {
      if (wantStandalone && !standalone.value.includes(id)) {
        if (!(await ensureSupported(target, false))) return false
        if (!(await saveList('Targets', [...standalone.value, id]))) return false
      }
      if (wantStartOnOpen && !startOnOpen.value.includes(id))
        if (!(await saveList('StartOnOpen', [...startOnOpen.value, id]))) return false
      if (!wantStandalone && standalone.value.includes(id))
        if (!(await saveList('Targets', without(standalone.value)))) return false
      if (!wantStartOnOpen && startOnOpen.value.includes(id))
        return saveList('StartOnOpen', without(startOnOpen.value))
      return true
    } finally {
      adding.value = false
    }
  }

  async function remove(id: string): Promise<boolean> {
    if (
      standalone.value.includes(id) &&
      !(await saveList(
        'Targets',
        standalone.value.filter(item => item !== id)
      ))
    )
      return false
    if (!startOnOpen.value.includes(id)) return true
    return saveList(
      'StartOnOpen',
      startOnOpen.value.filter(item => item !== id)
    )
  }

  // 旧版「打开分身时一并启动」的选择在卡片首次显示时并入 StartOnOpen，永不写 Targets；
  // 设置保存成功后才置迁移标记。
  let migrationStarted = false
  async function migrateLegacySelection(loaded: TaskTargetSnapshot) {
    if (migrationStarted) return
    migrationStarted = true
    let config: Awaited<ReturnType<typeof getConfig>>
    try {
      // 严格读取：配置文件读不出来时会抛错。常规读取会回落成默认配置（旧选择为空、没有标记），
      // 那样会在什么都没并进来的情况下置上迁移标记，旧选择就永久丢了。
      config = await getConfig({ strict: true })
    } catch {
      return
    }
    if (config.desktopSessionStartOnOpenMigrated === true) return
    const known = new Set(
      [...loaded.targets.map(target => target.value), ...loaded.unavailableScriptIds].map(id =>
        id.toLowerCase()
      )
    )
    const current = startOnOpen.value
    const merged = mergeLegacyDesktopSessionTargets(current, config.desktopSessionQueueIds, known)
    if (merged.length !== current.length && !(await saveList('StartOnOpen', merged))) return
    try {
      await saveConfig({ desktopSessionStartOnOpenMigrated: true })
    } catch {
      // 标记没写上时下次再并一次，重复的 id 会被去重。
    }
  }

  watch(
    [() => options.settings().DesktopSession, snapshot],
    ([group, loaded]) => {
      if (group && loaded) void migrateLegacySelection(loaded)
    },
    { immediate: true }
  )

  return {
    snapshot,
    loading,
    adding,
    standalone,
    startOnOpen,
    atLimit,
    candidates,
    rows,
    launchIds,
    load,
    add,
    setMode,
    remove,
  }
}
