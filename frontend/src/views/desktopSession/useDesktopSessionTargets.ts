import { computed, ref, shallowRef, watch } from 'vue'
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

export interface DesktopSessionTargetRow {
  id: string
  kind?: TaskTarget['kind']
  name: string
  issue?: DesktopSessionTargetIssue
  launchable: boolean
}

interface Capability {
  supported: boolean
  reason: Reason
}

const hasPowerAction = (afterAccomplish?: PowerSignal) =>
  Boolean(afterAccomplish && afterAccomplish !== PowerSignal.NO_ACTION)

/**
 * 桌面分身清单：存在后端 GlobalConfig.DesktopSession.Targets，写入走设置页的保存链路。
 * 卡片显示时读取一次队列和托管，逐个单查清单里托管的分身能力，并把旧键一次性并入清单。
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
  const draft = shallowRef<string[] | null>(null)
  const targets = computed(
    () => draft.value ?? options.settings().DesktopSession?.Targets ?? ([] as string[])
  )
  const atLimit = computed(() => targets.value.length >= MAX_DESKTOP_SESSION_TARGETS)

  const candidates = computed(() => {
    const listed = new Set(targets.value)
    return (snapshot.value?.targets ?? [])
      .filter(target => !listed.has(target.value.toLowerCase()))
      .map(target => ({ target, powerAction: hasPowerAction(target.afterAccomplish) }))
  })

  const rows = computed<DesktopSessionTargetRow[]>(() => {
    const known = new Map(
      (snapshot.value?.targets ?? []).map(target => [target.value.toLowerCase(), target])
    )
    const unavailable = new Map(
      (snapshot.value?.unavailableScripts ?? []).map(item => [item.uid.toLowerCase(), item.name])
    )
    return targets.value.map(id => {
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
      }
    })
  })
  const launchableIds = computed(() => rows.value.filter(row => row.launchable).map(row => row.id))

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
  async function refreshCapabilities(ids: string[]) {
    const queue = ids.filter(id => !(id in capabilities.value) && !pendingCapabilities.has(id))
    queue.forEach(id => pendingCapabilities.add(id))
    const worker = async () => {
      for (let id = queue.shift(); id !== undefined; id = queue.shift()) {
        try {
          capabilities.value = { ...capabilities.value, [id]: await readCapability(id) }
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
    [targets, snapshot],
    () => {
      const scripts = new Set(
        (snapshot.value?.targets ?? [])
          .filter(target => target.kind === 'script')
          .map(target => target.value.toLowerCase())
      )
      void refreshCapabilities(targets.value.filter(id => scripts.has(id)))
    },
    { immediate: true }
  )

  async function saveTargets(next: string[]): Promise<boolean> {
    draft.value = next
    let saved = false
    try {
      saved = await options.save('DesktopSession', 'Targets', next)
    } catch {
      // 保存失败由设置页统一提示。
    }
    if (draft.value === next) draft.value = null
    return saved
  }

  /** 加入清单；托管先单查分身能力，不支持就不加入。 */
  async function add(value: unknown): Promise<boolean> {
    if (typeof value !== 'string' || atLimit.value) return false
    const id = value.toLowerCase()
    const target = snapshot.value?.targets.find(item => item.value.toLowerCase() === id)
    if (!target || targets.value.includes(id) || hasPowerAction(target.afterAccomplish))
      return false
    if (target.kind === 'script') {
      adding.value = true
      try {
        const capability = await readCapability(target.value)
        capabilities.value = { ...capabilities.value, [id]: capability }
        if (!capability.supported) {
          options.onAddRejected(`reasons.${capability.reason}`)
          return false
        }
      } catch {
        options.onLoadFailed()
        return false
      } finally {
        adding.value = false
      }
    }
    if (targets.value.includes(id)) return false
    return saveTargets([...targets.value, id])
  }

  function remove(id: string): Promise<boolean> {
    return saveTargets(targets.value.filter(item => item !== id))
  }

  // 旧版「打开分身时一并启动」的选择在卡片首次显示时并入清单；设置保存成功后才置迁移标记。
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
    if (config.desktopSessionQueueIdsMigrated === true) return
    const known = new Set(
      [...loaded.targets.map(target => target.value), ...loaded.unavailableScriptIds].map(id =>
        id.toLowerCase()
      )
    )
    const current = targets.value
    const merged = mergeLegacyDesktopSessionTargets(current, config.desktopSessionQueueIds, known)
    if (merged.length !== current.length && !(await saveTargets(merged))) return
    try {
      await saveConfig({ desktopSessionQueueIdsMigrated: true })
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
    targets,
    atLimit,
    candidates,
    rows,
    launchableIds,
    load,
    add,
    remove,
  }
}
