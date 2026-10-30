import { beginAnalyticsOperation } from '@/utils/analytics'
import type { AnalyticsEventProps } from '@/types/analytics'
import { useI18n } from 'vue-i18n'
import { computed, onScopeDispose, ref } from 'vue'
import { getConfig, saveConfig } from '@/utils/config'
import { useScriptApi } from '@/composables/useScriptApi'
import { onConnected } from '@/services/websocket/connection'
import type { HomeLayoutConfig, HomeModuleDescriptor, HomeModuleKey } from '@/types/home'
import {
  HOME_ACTIVITY_CAROUSEL_KEY,
  defaultHomeModuleOrder,
  isHomeActivityModuleKey,
  managedHomeActivityKeys,
  normalizeHomeLayoutConfig,
} from '@/views/home/homeLayoutConfig'

const HOME_LAYOUT_STORAGE_KEY = 'auto-mas.home.layout'
const MANAGED_ACTIVITY_RETRY_DELAY_MS = 30_000

export {
  HOME_ACTIVITY_CAROUSEL_KEY,
  HOME_ACTIVITY_MODULE_KEYS,
  HOME_ACTIVITY_NOTE_KEYS,
  defaultHomeModuleOrder,
  isHomeActivityModuleKey,
  normalizeHomeLayoutConfig,
} from '@/views/home/homeLayoutConfig'

/** 配置里是一条扁平顺序，界面上却是两级：顶层模块 + 轮播内部的游戏卡 */
const splitModuleOrder = (order: HomeModuleKey[]) => ({
  topLevel: order.filter(key => !isHomeActivityModuleKey(key)),
  activities: order.filter(isHomeActivityModuleKey),
})

/** 存回配置时把游戏卡顺序紧跟在轮播模块后面，保证两级视图能原样还原 */
const composeModuleOrder = (
  topLevel: HomeModuleKey[],
  activities: HomeModuleKey[]
): HomeModuleKey[] => {
  const order: HomeModuleKey[] = []
  for (const key of topLevel) {
    order.push(key)
    if (key === HOME_ACTIVITY_CAROUSEL_KEY) {
      order.push(...activities)
    }
  }
  return order
}

const getLayoutLogger = () => window.electronAPI.getLogger('首页布局')

export const useHomeLayout = () => {
  const layoutReady = ref(false)
  const layoutDrawerOpen = ref(false)
  const defaultSplit = splitModuleOrder(defaultHomeModuleOrder)
  const homeTopLevelOrder = ref<HomeModuleKey[]>([...defaultSplit.topLevel])
  const homeActivityOrder = ref<HomeModuleKey[]>([...defaultSplit.activities])
  const hiddenHomeModules = ref<HomeModuleKey[]>([])
  const shownActivityModules = ref<HomeModuleKey[]>([])
  const managedActivityKeys = ref<HomeModuleKey[]>([])
  const { getScripts, error: scriptsError } = useScriptApi()
  let managedActivityRetryTimer: number | undefined
  let disposed = false
  const scrollHintHidden = ref(false)
  const carouselAutoplay = ref(false)
  // 首页便笺：总开关默认关（在游戏社区设置里打开），每游戏单独开关默认全开
  const activityNotesVisible = ref(false)
  const hiddenActivityNotes = ref<HomeModuleKey[]>([])
  let saveQueue = Promise.resolve()

  const homeModuleOrder = computed(() =>
    composeModuleOrder(homeTopLevelOrder.value, homeActivityOrder.value)
  )

  const currentLayout = (): HomeLayoutConfig => ({
    moduleOrder: [...homeModuleOrder.value],
    hiddenModules: [...hiddenHomeModules.value],
    shownActivityModules: [...shownActivityModules.value],
    hideScrollHint: scrollHintHidden.value,
    carouselAutoplay: carouselAutoplay.value,
    activityNotesVisible: activityNotesVisible.value,
    hiddenActivityNotes: [...hiddenActivityNotes.value],
  })

  const applyLayout = (layout: HomeLayoutConfig) => {
    const split = splitModuleOrder(layout.moduleOrder)
    homeTopLevelOrder.value = split.topLevel
    homeActivityOrder.value = split.activities
    hiddenHomeModules.value = [...layout.hiddenModules]
    shownActivityModules.value = [...(layout.shownActivityModules ?? [])]
    scrollHintHidden.value = layout.hideScrollHint === true
    carouselAutoplay.value = layout.carouselAutoplay === true
    activityNotesVisible.value = layout.activityNotesVisible === true
    hiddenActivityNotes.value = [...(layout.hiddenActivityNotes ?? [])]
  }

  const logWarning = (message: string, error: unknown) => {
    const errorMessage = error instanceof Error ? error.message : String(error)
    getLayoutLogger().warn(`${message}: ${errorMessage}`)
  }

  const queueLayoutSave = (
    layout: HomeLayoutConfig,
    action?: AnalyticsEventProps['home_layout_changed']['action']
  ) => {
    const telemetry = action ? beginAnalyticsOperation('home_layout_changed') : null
    const snapshot: HomeLayoutConfig = {
      moduleOrder: [...layout.moduleOrder],
      hiddenModules: [...layout.hiddenModules],
      shownActivityModules: [...(layout.shownActivityModules ?? [])],
      hideScrollHint: layout.hideScrollHint === true,
      carouselAutoplay: layout.carouselAutoplay === true,
      activityNotesVisible: layout.activityNotesVisible === true,
      hiddenActivityNotes: [...(layout.hiddenActivityNotes ?? [])],
    }
    const saveTask = saveQueue.then(() => saveConfig({ homeLayout: snapshot }))
    void saveTask.then(
      () => telemetry?.finish({ action: action!, layout_preset: 'custom', outcome: 'success' }),
      () => telemetry?.finish({ action: action!, layout_preset: 'custom', outcome: 'unknown' })
    )
    saveQueue = saveTask.catch(error => {
      logWarning('保存首页布局配置失败', error)
    })
    return saveTask.catch(() => undefined)
  }

  const loadHomeLayout = async () => {
    try {
      const config = await getConfig()
      if (config.homeLayout) {
        const layout = normalizeHomeLayoutConfig(config.homeLayout)
        applyLayout(layout)
        // 文件里的旧布局也要落盘，后续读取才能沿用迁移后的排序与隐藏设置。
        if (JSON.stringify(layout) !== JSON.stringify(config.homeLayout)) {
          await queueLayoutSave(layout)
        }
        return
      }

      const legacyConfig = localStorage.getItem(HOME_LAYOUT_STORAGE_KEY)
      if (!legacyConfig) {
        return
      }

      const migratedLayout = normalizeHomeLayoutConfig(JSON.parse(legacyConfig))
      applyLayout(migratedLayout)

      try {
        await saveConfig({ homeLayout: migratedLayout })
        localStorage.removeItem(HOME_LAYOUT_STORAGE_KEY)
      } catch (error) {
        logWarning('迁移首页布局配置失败', error)
      }
    } catch (error) {
      logWarning('读取首页布局配置失败', error)
    } finally {
      layoutReady.value = true
    }
  }

  const isHomeModuleShown = (key: HomeModuleKey) => {
    if (hiddenHomeModules.value.includes(key)) return false
    return (
      !isHomeActivityModuleKey(key) ||
      shownActivityModules.value.includes(key) ||
      managedActivityKeys.value.includes(key)
    )
  }

  const isHomeModuleVisible = (key: HomeModuleKey) => {
    return (
      isHomeModuleShown(key) &&
      (key !== HOME_ACTIVITY_CAROUSEL_KEY || visibleActivityKeys.value.length > 0)
    )
  }

  // 后端启动完成后再读托管列表；自动结果只参与显示，不写成用户的手动选择。
  const loadManagedActivityModules = async () => {
    if (disposed) return
    window.clearTimeout(managedActivityRetryTimer)
    managedActivityRetryTimer = undefined
    const scripts = await getScripts()
    if (disposed) return
    // 读取失败不等于没有托管脚本，保留上次结果，等待重试或后端恢复。
    if (scriptsError.value !== null) {
      managedActivityRetryTimer = window.setTimeout(() => {
        void loadManagedActivityModules()
      }, MANAGED_ACTIVITY_RETRY_DELAY_MS)
      return
    }
    managedActivityKeys.value = managedHomeActivityKeys(scripts)
  }

  const stopManagedActivityReconnect = onConnected(() => {
    if (managedActivityRetryTimer !== undefined) void loadManagedActivityModules()
  })
  onScopeDispose(() => {
    disposed = true
    window.clearTimeout(managedActivityRetryTimer)
    stopManagedActivityReconnect()
  })

  const reorderHomeModules = (order: HomeModuleKey[]) => {
    const nextLayout = normalizeHomeLayoutConfig({
      ...currentLayout(),
      moduleOrder: composeModuleOrder(
        order.filter(key => !isHomeActivityModuleKey(key)),
        homeActivityOrder.value
      ),
    })
    applyLayout(nextLayout)
    return queueLayoutSave(currentLayout(), 'reorder')
  }

  const reorderActivityModules = (order: HomeModuleKey[]) => {
    const nextLayout = normalizeHomeLayoutConfig({
      ...currentLayout(),
      moduleOrder: composeModuleOrder(
        homeTopLevelOrder.value,
        order.filter(isHomeActivityModuleKey)
      ),
    })
    applyLayout(nextLayout)
    return queueLayoutSave(currentLayout(), 'reorder')
  }

  const setHomeModuleShown = (key: HomeModuleKey, visible: boolean) => {
    if (isHomeActivityModuleKey(key)) {
      shownActivityModules.value = shownActivityModules.value.filter(shownKey => shownKey !== key)
      if (visible) shownActivityModules.value.push(key)
    }
    if (visible) {
      hiddenHomeModules.value = hiddenHomeModules.value.filter(hiddenKey => hiddenKey !== key)
    } else if (!hiddenHomeModules.value.includes(key)) {
      hiddenHomeModules.value = [...hiddenHomeModules.value, key]
    }
    return queueLayoutSave(currentLayout(), 'visibility')
  }

  const setScrollHintHidden = (hidden: boolean) => {
    scrollHintHidden.value = hidden
    return queueLayoutSave(currentLayout(), 'save')
  }

  const setCarouselAutoplay = (autoplay: boolean) => {
    carouselAutoplay.value = autoplay
    return queueLayoutSave(currentLayout(), 'save')
  }

  /** 首页便笺总开关；由游戏社区设置页的「首页显示日常便笺」控制 */
  const setActivityNotesVisible = (visible: boolean) => {
    activityNotesVisible.value = visible
    return queueLayoutSave(currentLayout(), 'visibility')
  }

  /** 首页便笺的每游戏单独开关：关掉后轮播切到该游戏也不再显示便笺 */
  const setActivityNoteShown = (key: HomeModuleKey, shown: boolean) => {
    hiddenActivityNotes.value = shown
      ? hiddenActivityNotes.value.filter(hiddenKey => hiddenKey !== key)
      : [...hiddenActivityNotes.value.filter(hiddenKey => hiddenKey !== key), key]
    return queueLayoutSave(currentLayout(), 'visibility')
  }

  const isActivityNoteVisible = (key: HomeModuleKey | null) =>
    key !== null && !hiddenActivityNotes.value.includes(key)

  const { t } = useI18n()

  const toDescriptors = (keys: HomeModuleKey[], titleKey: (key: HomeModuleKey) => string) =>
    keys.map(key => ({
      key,
      title: t(titleKey(key)),
      visible: isHomeModuleShown(key),
    }))

  const homeModules = computed<HomeModuleDescriptor[]>(() =>
    toDescriptors(homeTopLevelOrder.value, key => `core.home.module.${key}`)
  )

  // 轮播内部用游戏短名，顶层列表用带“活动信息”的完整模块名
  const homeActivityModules = computed<HomeModuleDescriptor[]>(() =>
    toDescriptors(homeActivityOrder.value, key => `core.home.game.${key}`)
  )

  const visibleActivityKeys = computed(() =>
    homeActivityOrder.value.filter(key => isHomeModuleShown(key))
  )

  return {
    layoutReady,
    layoutDrawerOpen,
    homeModuleOrder,
    homeTopLevelOrder,
    homeActivityOrder,
    hiddenHomeModules,
    scrollHintHidden,
    carouselAutoplay,
    activityNotesVisible,
    hiddenActivityNotes,
    homeModules,
    homeActivityModules,
    visibleActivityKeys,
    loadHomeLayout,
    loadManagedActivityModules,
    reorderHomeModules,
    reorderActivityModules,
    setHomeModuleShown,
    setScrollHintHidden,
    setCarouselAutoplay,
    setActivityNotesVisible,
    setActivityNoteShown,
    isActivityNoteVisible,
    isHomeModuleShown,
    isHomeModuleVisible,
  }
}
