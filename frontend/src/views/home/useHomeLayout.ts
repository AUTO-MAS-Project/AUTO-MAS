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

export const moduleTitleMap: Record<HomeModuleKey, string> = {
  command: '快速开始',
  quick: '常用入口',
  satellite: '卫星环绕',
  proxy: '代理状态',
  endfield: '终末地活动信息',
  starrail: '崩坏：星穹铁道活动信息',
  genshin: '原神活动信息',
  zenless: '绝区零活动信息',
  wutheringwaves: '鸣潮活动信息',
  nte: '异环活动信息',
  reverse1999: '重返未来：1999活动信息',
  arknights: '明日方舟活动信息',
}

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
  }
}

const getLayoutLogger = () => window.electronAPI.getLogger('首页布局')

export const useHomeLayout = () => {
  const layoutReady = ref(false)
  const layoutDrawerOpen = ref(false)
  const homeModuleOrder = ref<HomeModuleKey[]>([...defaultHomeModuleOrder])
  const hiddenHomeModules = ref<HomeModuleKey[]>([])
  let saveQueue = Promise.resolve()

  const currentLayout = (): HomeLayoutConfig => ({
    moduleOrder: [...homeModuleOrder.value],
    hiddenModules: [...hiddenHomeModules.value],
  })

  const applyLayout = (layout: HomeLayoutConfig) => {
    homeModuleOrder.value = [...layout.moduleOrder]
    hiddenHomeModules.value = [...layout.hiddenModules]
  }

  const logWarning = (message: string, error: unknown) => {
    const errorMessage = error instanceof Error ? error.message : String(error)
    getLayoutLogger().warn(`${message}: ${errorMessage}`)
  }

  const queueLayoutSave = (layout: HomeLayoutConfig) => {
    const snapshot: HomeLayoutConfig = {
      moduleOrder: [...layout.moduleOrder],
      hiddenModules: [...layout.hiddenModules],
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

  const homeModules = computed<HomeModuleDescriptor[]>(() =>
    homeModuleOrder.value.map(key => ({
      key,
      title: moduleTitleMap[key],
      visible: isHomeModuleShown(key),
    }))
  )

  return {
    layoutReady,
    layoutDrawerOpen,
    homeModuleOrder,
    hiddenHomeModules,
    homeModules,
    loadHomeLayout,
    reorderHomeModules,
    setHomeModuleShown,
    isHomeModuleShown,
    isHomeModuleVisible,
  }
}
