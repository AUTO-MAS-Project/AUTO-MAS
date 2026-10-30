import { computed, ref, watch, toValue, onScopeDispose, type Ref, type MaybeRefOrGetter } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { BetterGIDomainCatalogItem } from '@/api'
import {
  fetchDomainCatalog,
  fetchGlobalDomainSettings,
  fetchGlobalStygianSettings,
  fetchOneDragonSettings,
  saveGlobalDomainSettings,
  saveGlobalStygianSettings,
  saveOneDragonSettings,
} from '@/composables/useBettergiOneDragonSettings'
import {
  BUILTIN_GROUP_SETTING_SECTIONS,
  type DragonSettingField,
  type DragonSettingSection,
} from './bettergiGroupSettingsSchema'
import type { ConfigGroupIdentity } from './bettergiQueueIdentity'
export function useBettergiGroupSettings(options: {
  scriptId: string
  userId: Ref<string>
  selected: Ref<ConfigGroupIdentity | null>
  masEnabled: Ref<boolean>
  locked: Ref<boolean>
  configName: MaybeRefOrGetter<string>
  stepName: (row: ConfigGroupIdentity) => string
}) {
  const {
    scriptId,
    userId,
    selected: selectedGroupIdentity,
    masEnabled: masConfigEnabled,
    locked: configLocked,
    stepName: stepNameOf,
  } = options
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('BetterGI用户编辑')
  let active = true
  let readVersion = 0
  let selectionVersion = 0
  let editVersion = 0
  const invalidateReads = () => {
    readVersion += 1
    selectionVersion += 1
    dragonSettingsLoading.value = false
  }
  onScopeDispose(() => {
    active = false
    invalidateReads()
    if (dragonGroupAutoSaveTimer) clearTimeout(dragonGroupAutoSaveTimer)
    dragonGroupAutoSaveTimer = null
  })
  // 当前选中内置组的设置分组（无字段返回空）
  const currentGroupSettingSections = computed<DragonSettingSection[]>(() => {
    const sel = selectedGroupIdentity.value
    if (!sel || sel.kind !== 'builtin') return []
    return BUILTIN_GROUP_SETTING_SECTIONS[sel.key] || []
  })

  // 周表与队伍场景共享目录，进入页面即加载，不随右栏配置组切换而清空。
  const domainCatalog = ref<BetterGIDomainCatalogItem[]>([])
  const domainCatalogError = ref(false)
  let domainCatalogPromise: Promise<BetterGIDomainCatalogItem[]> | null = null
  const loadDomainCatalog = (): Promise<BetterGIDomainCatalogItem[]> => {
    if (!active || !scriptId) return Promise.resolve([])
    if (domainCatalog.value.length) return Promise.resolve(domainCatalog.value)
    if (!domainCatalogPromise) {
      domainCatalogPromise = fetchDomainCatalog(scriptId)
        .then(list => {
          if (active) {
            domainCatalog.value = list
            domainCatalogError.value = list.length === 0
          }
          return list
        })
        .catch(e => {
          if (active) {
            logger.error(e instanceof Error ? e.message : String(e))
            domainCatalogError.value = true
          }
          return [] as BetterGIDomainCatalogItem[]
        })
        .finally(() => {
          domainCatalogPromise = null
        })
    }
    return domainCatalogPromise
  }

  // 当前组是否需要周表秘境目录（仅「自动秘境」的每周秘境表格模式需要）
  const needDomainCatalog = computed<boolean>(() =>
    currentGroupSettingSections.value.some(s => s.kind === 'weekly-table')
  )

  // 一条龙 per-user 设置（每日秘境/每周秘境/首领/地脉花等，随用户与配置组切换）
  const dragonSettings = ref<Record<string, unknown>>({})

  const dragonSettingsLoading = ref(false)

  const dragonSettingsSaving = ref(false)

  const dragonSettingsDirty = ref(false)

  // 全局 config.json 秘境刷取配置（领奖树脂/分解圣遗物/奖励识别；只随 scriptId，不随用户/配置组）
  const globalDomainSettings = ref<Record<string, unknown>>({})

  const globalDomainSettingsDirty = ref(false)

  // 全局 config.json 幽境危战段设置（刷取战场/队伍/策略/次数与树脂；autoStygianOnslaughtConfig 段）
  const globalStygianSettings = ref<Record<string, unknown>>({})

  const globalStygianSettingsDirty = ref(false)

  const hasDragonGroupSettingsDirty = computed(
    () =>
      dragonSettingsDirty.value ||
      globalDomainSettingsDirty.value ||
      globalStygianSettingsDirty.value
  )

  // 当前选中内置组是否有设置 schema（含每周秘境周表等非 fields 形态的分组）
  const hasGroupSettingFields = computed<boolean>(() =>
    currentGroupSettingSections.value.some(
      s =>
        s.fields.length > 0 ||
        s.kind === 'weekly-table' ||
        s.kind === 'weekly-field-table' ||
        s.kind === 'daily-leyline'
    )
  )

  // BetterGI 一条龙独立模式专属配置名（MAS 槽位；开启「用户独立配置」时固定使用，
  // 一条龙名称下拉冻结，不再让用户选择 BGI 实配名）。与后端 one_dragon.launch_slot_name() 一致。
  const MAS_ONE_DRAGON_SLOT_NAME = 'MAS独立配置'

  // 右栏任务设置读写的配置名：独立模式固定为 MAS 槽位名；否则用户所选一条龙名（默认配置兜底）
  const dragonConfigName = computed<string>(() =>
    masConfigEnabled.value ? MAS_ONE_DRAGON_SLOT_NAME : toValue(options.configName) || '默认配置'
  )

  // 当前组的字段是否需要全局秘境段（触发 globalDomain 加载/保存）
  const needGlobalDomainSettings = computed<boolean>(() =>
    currentGroupSettingSections.value.some(s => s.fields.some(f => f.source === 'globalDomain'))
  )

  // 当前组的字段是否需要全局幽境段（触发 globalStygian 加载/保存）
  const needGlobalStygianSettings = computed<boolean>(() =>
    currentGroupSettingSections.value.some(s => s.fields.some(f => f.source === 'globalStygian'))
  )

  // 右栏设置自动保存：debounce 合并连击（如文本逐字输入），串行队列避免并发丢保存。
  // dragonGroupSaveSel 锁定「正在编辑的配置组」：自动保存 / 切换前冲刷都在该组落库，
  // 避免切换组后定时器才触发、把旧组数据误写进新组的配置。
  let dragonGroupAutoSaveTimer: ReturnType<typeof setTimeout> | null = null

  let dragonGroupSaveChain: Promise<boolean> = Promise.resolve(true)

  let dragonGroupSaveSel: ConfigGroupIdentity | null = null

  const scheduleDragonGroupAutoSave = (silent = true) => {
    dragonGroupSaveSel = selectedGroupIdentity.value ?? null
    if (dragonGroupAutoSaveTimer) clearTimeout(dragonGroupAutoSaveTimer)
    dragonGroupAutoSaveTimer = setTimeout(() => {
      dragonGroupAutoSaveTimer = null
      void saveDragonGroupSettings(silent, dragonGroupSaveSel)
    }, 400)
  }

  // 编辑字段：本地即时更新并自动落库（无需点「保存设置」）；按数据来源分流到对应 store，
  // 再经 debounce 写回。字段来源必须与 DragonSettingField.source 对齐。
  const updateSettingField = (field: DragonSettingField, value: unknown) => {
    editVersion += 1
    if (field.source === 'globalDomain') {
      globalDomainSettings.value = { ...globalDomainSettings.value, [field.key]: value }
      globalDomainSettingsDirty.value = true
    } else if (field.source === 'globalStygian') {
      globalStygianSettings.value = { ...globalStygianSettings.value, [field.key]: value }
      globalStygianSettingsDirty.value = true
    } else {
      dragonSettings.value = { ...dragonSettings.value, [field.key]: value }
      dragonSettingsDirty.value = true
    }
    void scheduleDragonGroupAutoSave(true)
  }

  // 读取该用户一条龙配置设置项 + （如需要）全局秘境/幽境段（切换选中行时刷新）
  const loadDragonGroupSettings = async () => {
    const sel = selectedGroupIdentity.value
    const version = ++readVersion
    const revision = editVersion
    const contextUserId = userId.value
    const current = () =>
      active &&
      version === readVersion &&
      revision === editVersion &&
      contextUserId === userId.value &&
      sel?.uid === selectedGroupIdentity.value?.uid &&
      sel?.key === selectedGroupIdentity.value?.key
    dragonGroupSaveSel = sel ?? null
    if (!sel || sel.kind !== 'builtin' || !userId.value) {
      dragonSettings.value = {}
      dragonSettingsDirty.value = false
      globalDomainSettings.value = {}
      globalDomainSettingsDirty.value = false
      globalStygianSettings.value = {}
      globalStygianSettingsDirty.value = false
      return
    }
    if (!hasGroupSettingFields.value) return
    dragonSettingsLoading.value = true
    try {
      // 四份数据互不依赖，并行拉取
      const globalUserId = masConfigEnabled.value ? userId.value : undefined
      const [dragon, globalDomain, globalStygian] = await Promise.all([
        fetchOneDragonSettings(scriptId, userId.value, dragonConfigName.value, stepNameOf(sel)),
        needGlobalDomainSettings.value
          ? fetchGlobalDomainSettings(scriptId, globalUserId, stepNameOf(sel))
          : Promise.resolve<Record<string, unknown>>({}),
        needGlobalStygianSettings.value
          ? fetchGlobalStygianSettings(scriptId, globalUserId, stepNameOf(sel))
          : Promise.resolve<Record<string, unknown>>({}),
        needDomainCatalog.value ? loadDomainCatalog() : Promise.resolve(domainCatalog.value),
      ])
      if (!current()) return
      dragonSettings.value = dragon
      dragonSettingsDirty.value = false
      globalDomainSettings.value = globalDomain
      globalDomainSettingsDirty.value = false
      globalStygianSettings.value = globalStygian
      globalStygianSettingsDirty.value = false
    } catch (e) {
      if (!current()) return
      logger.error(e instanceof Error ? e.message : String(e))
      message.error(e instanceof Error ? e.message : t('core.edit.bettergiGroupSettingsLoadFailed'))
    } finally {
      if (version === readVersion) dragonSettingsLoading.value = false
    }
  }

  // 保存：一条龙字段写回 per-user 副本；globalDomain/globalStygian 字段写回 BetterGI 全局 config.json 段。
  // 经串行队列执行（避免并发丢保存，优于原 `if (saving) return` 直接丢弃）；silent=true 时不弹成功提示
  // （自动保存场景）。返回 Promise<boolean> 便于调用方（切换组 / 整体保存前）await 冲刷未决编辑。
  const saveDragonGroupSettings = (
    silent = false,
    selOverride?: ConfigGroupIdentity | null
  ): Promise<boolean> => {
    const sel = selOverride ?? selectedGroupIdentity.value
    const contextUserId = userId.value
    const contextConfigName = dragonConfigName.value
    const contextGlobalUserId = masConfigEnabled.value ? contextUserId : undefined
    const contextStep = sel ? stepNameOf(sel) : ''
    const run = dragonGroupSaveChain.then(async () => {
      if (configLocked.value) {
        if (hasDragonGroupSettingsDirty.value) {
          message.error(t('core.edit.configLocked'))
          return false
        }
        return true
      }
      if (!sel || sel.kind !== 'builtin' || !contextUserId) return false
      const tasks: Promise<unknown>[] = []
      if (dragonSettingsDirty.value) {
        const settings = dragonSettings.value
        tasks.push(
          saveOneDragonSettings(
            scriptId,
            contextUserId,
            contextConfigName,
            settings,
            contextStep
          ).then(() => {
            if (dragonSettings.value === settings) dragonSettingsDirty.value = false
          })
        )
      }
      if (globalDomainSettingsDirty.value) {
        const settings = globalDomainSettings.value
        tasks.push(
          saveGlobalDomainSettings(scriptId, contextGlobalUserId, settings, contextStep).then(
            () => {
              if (globalDomainSettings.value === settings) globalDomainSettingsDirty.value = false
            }
          )
        )
      }
      if (globalStygianSettingsDirty.value) {
        const settings = globalStygianSettings.value
        tasks.push(
          saveGlobalStygianSettings(scriptId, contextGlobalUserId, settings, contextStep).then(
            () => {
              if (globalStygianSettings.value === settings) globalStygianSettingsDirty.value = false
            }
          )
        )
      }
      if (tasks.length === 0) return true
      try {
        await Promise.all(tasks)
        if (!silent) message.success(t('core.edit.bettergiGroupSettingsSaved'))
        return true
      } catch (e) {
        logger.error(e instanceof Error ? e.message : String(e))
        message.error(
          e instanceof Error ? e.message : t('core.edit.bettergiGroupSettingsSaveFailed')
        )
        return false
      }
    })
    dragonGroupSaveChain = run.catch(() => false)
    return run
  }
  // 切换选中内置组时加载该组的设置项（分组标签页状态由子组件按 sections 变化自动重置）
  watch(
    () => selectedGroupIdentity.value?.uid,
    async () => {
      const version = ++selectionVersion
      const previous = dragonGroupSaveSel
      // 切换组前先冲刷未决的自动保存，避免 debounce 未触发时编辑被跳过而丢失
      const saved = await flushPending()
      if (!active || version !== selectionVersion) return
      if (!saved) {
        // 保留失败草稿所属的组，避免用新组的字段编辑旧组的值。
        selectedGroupIdentity.value = previous
        return
      }
      await loadDragonGroupSettings()
    }
  )
  async function flushPending(allDirty = false): Promise<boolean> {
    const pending = !!dragonGroupAutoSaveTimer
    if (dragonGroupAutoSaveTimer) {
      clearTimeout(dragonGroupAutoSaveTimer)
      dragonGroupAutoSaveTimer = null
    }
    if (allDirty) {
      while (hasDragonGroupSettingsDirty.value) {
        if (!(await saveDragonGroupSettings(true, dragonGroupSaveSel))) return false
      }
    } else if (pending) return saveDragonGroupSettings(true, dragonGroupSaveSel)
    return dragonGroupSaveChain
  }
  return {
    MAS_ONE_DRAGON_SLOT_NAME,
    dragonConfigName,
    currentGroupSettingSections,
    domainCatalog,
    domainCatalogError,
    loadDomainCatalog,
    dragonSettings,
    dragonSettingsLoading,
    dragonSettingsSaving,
    dragonSettingsDirty,
    globalDomainSettings,
    globalDomainSettingsDirty,
    globalStygianSettings,
    globalStygianSettingsDirty,
    hasDragonGroupSettingsDirty,
    updateSettingField,
    saveDragonGroupSettings,
    flushPending,
    invalidateReads,
  }
}
