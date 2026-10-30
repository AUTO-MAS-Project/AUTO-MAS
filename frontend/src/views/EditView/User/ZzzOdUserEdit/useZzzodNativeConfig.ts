import { AdapterSetupService as Service } from '@/composables/useAdapterSetupApi'
import {
  computed,
  ref,
  reactive,
  watch,
  toValue,
  onScopeDispose,
  type Ref,
  type MaybeRefOrGetter,
} from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  type ZzzOdNativeAccountField,
  type ZzzOdNativeConfigOut,
  ZzzOdNativeLaunchArgs,
} from '@/api'
import type { TaskCard, AfterDoneValue } from './zzzodTypes'
export function useZzzodNativeConfig(
  scriptId: string,
  configLocked: Ref<boolean>,
  active: MaybeRefOrGetter<boolean> = true
) {
  const { t } = useI18n()
  // ══ 原生来源：所选实例的原生配置（强绑定一条龙原始 YAML，页面即改原生）══
  const nativeInstanceIdx = ref<number | null>(null)

  // 运行实例（value 为一条龙原生中文取值，label 走词表；初始值对齐上游
  // InstanceRun.ALL 默认，加载后由后端返回值覆盖）
  const nativeInstanceRun = ref('全部实例')

  // 原生来源下「游戏结束后操作」读写的是一条龙原生 after_done（UI 与原生 GUI
  // 同源，改哪边另一边都同步）；独立来源/共享来源模式走 MAS 用户字段（会话双向联动）
  const nativeAfterDone = ref<AfterDoneValue>('无')

  const instanceRunOptions = [
    { label: t('core.edit.zzzodInstanceRunCurrent'), value: '仅运行当前' },
    { label: t('core.edit.zzzodInstanceRunAll'), value: '全部实例' },
  ]

  const nativeLoading = ref(false)

  const pendingCount = ref(0)
  const nativeSaving = computed(() => pendingCount.value > 0)
  let contextVersion = 0
  let readVersion = 0
  let saveChain: Promise<boolean> = Promise.resolve(true)
  const runModeWrites = new Set<Promise<void>>()
  watch(
    () => [nativeInstanceIdx.value, toValue(active)],
    () => {
      contextVersion++
      readVersion++
      nativeLoading.value = false
    },
    { flush: 'sync' }
  )
  onScopeDispose(() => {
    contextVersion++
    readVersion++
  })
  const flushNativeSaves = async () => {
    let tail: Promise<boolean>
    do {
      tail = saveChain
      await Promise.all([tail, ...runModeWrites])
    } while (tail !== saveChain || runModeWrites.size)
  }

  const nativeAccountFields = ref<ZzzOdNativeAccountField[]>([])

  const nativeAccountValues = reactive<Record<string, string>>({})

  const nativeTasks = ref<TaskCard[]>([])

  // 原生来源启动参数（game.yml 字段 + dx12 开关；改动即时整组提交，与其他区块解耦）
  const getDefaultLaunchArgs = (): ZzzOdNativeLaunchArgs => ({
    launch_argument: false,
    screen_size: ZzzOdNativeLaunchArgs.screen_size._1920X1080,
    full_screen: ZzzOdNativeLaunchArgs.full_screen._0,
    popup_window: false,
    dx12: false,
    monitor: ZzzOdNativeLaunchArgs.monitor._1,
    launch_argument_advance: '',
  })

  const nativeLaunchArgs = reactive<ZzzOdNativeLaunchArgs>(getDefaultLaunchArgs())

  const applyNativeConfig = (data: ZzzOdNativeConfigOut) => {
    nativeAccountFields.value = data.account ?? []
    const values: Record<string, string> = {}
    for (const f of data.account ?? []) {
      if (f.value != null) values[f.key] = String(f.value)
    }
    Object.keys(nativeAccountValues).forEach(k => delete nativeAccountValues[k])
    Object.assign(nativeAccountValues, values)
    Object.assign(nativeLaunchArgs, getDefaultLaunchArgs(), data.launchArgs ?? {})
    nativeInstanceRun.value = data.instanceRun || '全部实例'
    nativeAfterDone.value = (data.afterDone as AfterDoneValue) || '无'
    nativeTasks.value = toTaskCards(data.tasks ?? [])
  }

  const loadNativeConfig = async (instanceIdx: number) => {
    const context = contextVersion
    const request = ++readVersion
    const current = () =>
      context === contextVersion &&
      request === readVersion &&
      instanceIdx === nativeInstanceIdx.value
    nativeLoading.value = true
    try {
      const resp = await Service.getZzzodNativeConfigApiApiScriptsZzzodNativeConfigGet(
        scriptId,
        instanceIdx
      )
      if (resp.code !== 200) {
        throw new Error(resp.message || t('core.edit.zzzodNativeLoadFailed'))
      }
      if (current()) applyNativeConfig(resp)
    } catch (e) {
      if (!current()) return
      message.error(e instanceof Error ? e.message : t('core.edit.zzzodNativeLoadFailed'))
      nativeAccountFields.value = []
      nativeTasks.value = []
      nativeAfterDone.value = '无'
    } finally {
      if (current()) nativeLoading.value = false
    }
  }

  /** 运行实例（仅运行当前/全部启用实例）是 one_dragon.yml 全局设置，
   * 与原生来源页当前编辑哪个实例无关，独立保存 */
  const runModeCount = ref(0)
  const runModeSaving = computed(() => runModeCount.value > 0)

  const persistNativeInstanceRun = async () => {
    if (configLocked.value) return
    runModeCount.value++
    try {
      const resp = await Service.setZzzodInstanceRunModeApiApiScriptsZzzodInstancesRunModePost({
        scriptId,
        instanceRun: nativeInstanceRun.value,
      })
      if (resp.code !== 200) {
        throw new Error(resp.message || t('core.edit.zzzodNativeSaveFailed'))
      }
    } catch (e) {
      message.error(e instanceof Error ? e.message : t('core.edit.zzzodNativeSaveFailed'))
    } finally {
      runModeCount.value--
    }
  }
  const handleNativeInstanceRunChange = () => {
    const run = persistNativeInstanceRun()
    runModeWrites.add(run)
    void run.finally(() => runModeWrites.delete(run))
    return run
  }

  /** 原生来源按需保存：只提交指定区块并只回读该区块。
   *
   *  - 账号字段（「保存设置」按钮）：全量提交 account + tasks + instanceRun；
   *  - 任务开关/排序、运行实例：即时增量提交对应字段——不把未保存的账号
   *    草稿一并落盘或覆盖。
   */
  type NativeSaveSection = 'all' | 'tasks' | 'launchArgs' | 'afterDone'

  /** 提交给后端的任务条目（后端只认 app_id/enabled） */
  const toNativeTaskIn = (list: TaskCard[]): { app_id: string; enabled: boolean }[] =>
    list.map(t => ({ app_id: t.app_id, enabled: !!t.enabled }))

  /** 后端任务条目 → 卡片（加载与保存回读共用） */
  const toTaskCards = (tasks: NonNullable<ZzzOdNativeConfigOut['tasks']>) =>
    tasks.map(
      t =>
        ({
          app_id: t.app_id,
          app_name: t.app_name,
          enabled: !!t.enabled,
          configurable: t.configurable,
          jump: t.jump,
        }) as TaskCard
    )

  const saveNativeConfig = (
    payload: {
      account?: Record<string, string>
      tasks?: { app_id: string; enabled: boolean }[]
      instanceRun?: string
      afterDone?: string
      launchArgs?: ZzzOdNativeLaunchArgs
    },
    section: NativeSaveSection = 'all',
    silent = false
  ): Promise<boolean> => {
    if (configLocked.value) {
      message.error(t('core.edit.configLocked'))
      return Promise.resolve(false)
    }
    if (nativeInstanceIdx.value === null) return Promise.resolve(false)
    // 新实例尚未加载时不能把上个实例残留的区块提交到新目标。
    if (nativeLoading.value) return Promise.resolve(false)
    const instanceIdx = nativeInstanceIdx.value
    const context = contextVersion
    const snapshot = {
      account: { ...nativeAccountValues },
      tasks: JSON.stringify(nativeTasks.value),
      launchArgs: { ...nativeLaunchArgs },
      afterDone: nativeAfterDone.value,
      instanceRun: nativeInstanceRun.value,
    }
    readVersion++
    nativeLoading.value = false
    pendingCount.value++
    const persist = async (): Promise<boolean> => {
      try {
        const resp = await Service.saveZzzodNativeConfigApiApiScriptsZzzodNativeConfigSavePost({
          scriptId,
          instanceIdx,
          ...payload,
        })
        if (resp.code !== 200) {
          throw new Error(resp.message || t('core.edit.zzzodNativeSaveFailed'))
        }
        if (context === contextVersion) {
          if (section === 'all') {
            nativeAccountFields.value = resp.account ?? []
            for (const field of resp.account ?? []) {
              if (nativeAccountValues[field.key] === snapshot.account[field.key]) {
                nativeAccountValues[field.key] = field.value == null ? '' : String(field.value)
              }
            }
            if (nativeInstanceRun.value === snapshot.instanceRun)
              nativeInstanceRun.value = resp.instanceRun || '全部实例'
          }
          if (
            (section === 'all' || section === 'tasks') &&
            JSON.stringify(nativeTasks.value) === snapshot.tasks
          )
            nativeTasks.value = toTaskCards(resp.tasks ?? [])
          if (section === 'all' || section === 'launchArgs') {
            const updated = { ...getDefaultLaunchArgs(), ...resp.launchArgs }
            for (const key of Object.keys(updated) as (keyof ZzzOdNativeLaunchArgs)[]) {
              if (nativeLaunchArgs[key] === snapshot.launchArgs[key])
                Object.assign(nativeLaunchArgs, { [key]: updated[key] })
            }
          }
          if (
            (section === 'all' || section === 'afterDone') &&
            nativeAfterDone.value === snapshot.afterDone
          )
            nativeAfterDone.value = (resp.afterDone as AfterDoneValue) || '无'
        }
        if (!silent) message.success(t('core.edit.zzzodNativeSaved'))
        return true
      } catch (e) {
        message.error(e instanceof Error ? e.message : t('core.edit.zzzodNativeSaveFailed'))
        return false
      } finally {
        pendingCount.value--
      }
    }
    const run = saveChain.then(persist, persist)
    saveChain = run
    return run
  }

  /** 原生来源启动参数：单字段即时提交（只发变更字段，读-改-写由后端持锁完成）。
   *
   * 不发全量：并发点不同开关时，全量会携带其他字段的旧值，串行写盘后后者
   * 覆盖前者已落盘的字段（丢更新）；单字段提交 + 后端「值未变跳过」语义
   * 才能让并发保存各落各的字段。
   */
  const saveNativeLaunchArgsField = (key: keyof ZzzOdNativeLaunchArgs, value: unknown) => {
    ;(nativeLaunchArgs as Record<string, unknown>)[key] = value
    return saveNativeConfig(
      { launchArgs: { [key]: value } as ZzzOdNativeLaunchArgs },
      'launchArgs',
      true
    )
  }

  /** 「保存设置」：账号字段全量写回（连同当前任务编排与运行实例，保持表单一致） */
  const saveNativeAccount = () =>
    saveNativeConfig(
      {
        account: { ...nativeAccountValues },
        tasks: toNativeTaskIn(nativeTasks.value),
        instanceRun: nativeInstanceRun.value,
        afterDone: nativeAfterDone.value,
      },
      'all'
    )
  return {
    hasPendingNativeSaves: () => pendingCount.value > 0 || runModeWrites.size > 0,
    flushNativeSaves,
    nativeInstanceIdx,
    nativeInstanceRun,
    nativeAfterDone,
    instanceRunOptions,
    nativeLoading,
    nativeSaving,
    nativeAccountFields,
    nativeAccountValues,
    nativeTasks,
    nativeLaunchArgs,
    loadNativeConfig,
    runModeSaving,
    handleNativeInstanceRunChange,
    toNativeTaskIn,
    saveNativeConfig,
    saveNativeLaunchArgsField,
    saveNativeAccount,
  }
}
