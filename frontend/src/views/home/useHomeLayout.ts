import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import { getConfig, saveConfig } from '@/utils/config'
import type { HomeLayoutConfig, HomeModuleDescriptor, HomeModuleKey } from '@/types/home'
import {
  HOME_ACTIVITY_CAROUSEL_KEY,
  defaultHomeModuleOrder,
  isHomeActivityModuleKey,
  normalizeHomeLayoutConfig,
} from '@/views/home/homeLayoutConfig'

const HOME_LAYOUT_STORAGE_KEY = 'auto-mas.home.layout'

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
    scrollHintHidden.value = layout.hideScrollHint === true
    carouselAutoplay.value = layout.carouselAutoplay === true
    activityNotesVisible.value = layout.activityNotesVisible === true
    hiddenActivityNotes.value = [...(layout.hiddenActivityNotes ?? [])]
  }

  const logWarning = (message: string, error: unknown) => {
    const errorMessage = error instanceof Error ? error.message : String(error)
    getLayoutLogger().warn(`${message}: ${errorMessage}`)
  }

  const queueLayoutSave = (layout: HomeLayoutConfig) => {
    const snapshot: HomeLayoutConfig = {
      moduleOrder: [...layout.moduleOrder],
      hiddenModules: [...layout.hiddenModules],
      hideScrollHint: layout.hideScrollHint === true,
      carouselAutoplay: layout.carouselAutoplay === true,
      activityNotesVisible: layout.activityNotesVisible === true,
      hiddenActivityNotes: [...(layout.hiddenActivityNotes ?? [])],
    }
    const saveTask = saveQueue.then(() => saveConfig({ homeLayout: snapshot }))
    saveQueue = saveTask.catch(error => {
      logWarning('保存首页布局配置失败', error)
    })
    return saveTask.catch(() => undefined)
  }

  const loadHomeLayout = async () => {
    try {
      const config = await getConfig()
      if (config.homeLayout) {
        applyLayout(normalizeHomeLayoutConfig(config.homeLayout))
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
    return !hiddenHomeModules.value.includes(key)
  }

  const isHomeModuleVisible = (key: HomeModuleKey) => {
    return isHomeModuleShown(key)
  }

  const reorderHomeModules = (order: HomeModuleKey[]) => {
    const nextLayout = normalizeHomeLayoutConfig({
      ...currentLayout(),
      moduleOrder: composeModuleOrder(
        order.filter(key => !isHomeActivityModuleKey(key)),
        homeActivityOrder.value
      ),
    })
    applyLayout(nextLayout)
    return queueLayoutSave(currentLayout())
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
    return queueLayoutSave(currentLayout())
  }

  const setHomeModuleShown = (key: HomeModuleKey, visible: boolean) => {
    if (visible) {
      hiddenHomeModules.value = hiddenHomeModules.value.filter(hiddenKey => hiddenKey !== key)
    } else if (!hiddenHomeModules.value.includes(key)) {
      hiddenHomeModules.value = [...hiddenHomeModules.value, key]
    }
    return queueLayoutSave(currentLayout())
  }

  const setScrollHintHidden = (hidden: boolean) => {
    scrollHintHidden.value = hidden
    return queueLayoutSave(currentLayout())
  }

  const setCarouselAutoplay = (autoplay: boolean) => {
    carouselAutoplay.value = autoplay
    return queueLayoutSave(currentLayout())
  }

  /** 首页便笺总开关；由游戏社区设置页的「首页显示日常便笺」控制 */
  const setActivityNotesVisible = (visible: boolean) => {
    activityNotesVisible.value = visible
    return queueLayoutSave(currentLayout())
  }

  /** 首页便笺的每游戏单独开关：关掉后轮播切到该游戏也不再显示便笺 */
  const setActivityNoteShown = (key: HomeModuleKey, shown: boolean) => {
    hiddenActivityNotes.value = shown
      ? hiddenActivityNotes.value.filter(hiddenKey => hiddenKey !== key)
      : [...hiddenActivityNotes.value.filter(hiddenKey => hiddenKey !== key), key]
    return queueLayoutSave(currentLayout())
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
    toDescriptors(homeTopLevelOrder.value, key => `home.module.${key}`)
  )

  // 轮播内部用游戏短名，顶层列表用带“活动信息”的完整模块名
  const homeActivityModules = computed<HomeModuleDescriptor[]>(() =>
    toDescriptors(homeActivityOrder.value, key => `home.game.${key}`)
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
