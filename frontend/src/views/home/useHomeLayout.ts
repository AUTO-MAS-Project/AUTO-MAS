import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import { getConfig, saveConfig } from '@/utils/config'
import type { HomeLayoutConfig, HomeModuleDescriptor, HomeModuleKey } from '@/types/home'

export const HOME_LAYOUT_STORAGE_KEY = 'auto-mas.home.layout'

export const defaultHomeModuleOrder: HomeModuleKey[] = [
  'command',
  'quick',
  'satellite',
  'proxy',
  'endfield',
  'starrail',
  'genshin',
  'zenless',
  'wutheringwaves',
  'nte',
  'reverse1999',
  'arknights',
]

const isHomeModuleKey = (value: unknown): value is HomeModuleKey => {
  return typeof value === 'string' && defaultHomeModuleOrder.includes(value as HomeModuleKey)
}

const normalizeModuleKeys = (value: unknown): HomeModuleKey[] => {
  const keys = Array.isArray(value) ? value.filter(isHomeModuleKey) : []
  return keys.filter((key, index, array) => array.indexOf(key) === index)
}

export const normalizeHomeLayoutConfig = (value: unknown): HomeLayoutConfig => {
  const config =
    typeof value === 'object' && value !== null ? (value as Partial<HomeLayoutConfig>) : {}
  const configuredOrder = normalizeModuleKeys(config.moduleOrder)
  const missingModules = defaultHomeModuleOrder.filter(key => !configuredOrder.includes(key))

  return {
    moduleOrder: [...configuredOrder, ...missingModules],
    hiddenModules: normalizeModuleKeys(config.hiddenModules),
    hideScrollHint: config.hideScrollHint === true,
  }
}

const getLayoutLogger = () => window.electronAPI.getLogger('首页布局')

export const useHomeLayout = () => {
  const layoutReady = ref(false)
  const layoutDrawerOpen = ref(false)
  const homeModuleOrder = ref<HomeModuleKey[]>([...defaultHomeModuleOrder])
  const hiddenHomeModules = ref<HomeModuleKey[]>([])
  const scrollHintHidden = ref(false)
  let saveQueue = Promise.resolve()

  const currentLayout = (): HomeLayoutConfig => ({
    moduleOrder: [...homeModuleOrder.value],
    hiddenModules: [...hiddenHomeModules.value],
    hideScrollHint: scrollHintHidden.value,
  })

  const applyLayout = (layout: HomeLayoutConfig) => {
    homeModuleOrder.value = [...layout.moduleOrder]
    hiddenHomeModules.value = [...layout.hiddenModules]
    scrollHintHidden.value = layout.hideScrollHint === true
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
      moduleOrder: order,
      hiddenModules: hiddenHomeModules.value,
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

  const { t } = useI18n()

  const homeModules = computed<HomeModuleDescriptor[]>(() =>
    homeModuleOrder.value.map(key => ({
      key,
      title: t(`home.module.${key}`),
      visible: isHomeModuleShown(key),
    }))
  )

  return {
    layoutReady,
    layoutDrawerOpen,
    homeModuleOrder,
    hiddenHomeModules,
    scrollHintHidden,
    homeModules,
    loadHomeLayout,
    reorderHomeModules,
    setHomeModuleShown,
    setScrollHintHidden,
    isHomeModuleShown,
    isHomeModuleVisible,
  }
}
