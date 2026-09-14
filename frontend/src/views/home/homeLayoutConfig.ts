import type { HomeLayoutConfig, HomeModuleKey } from '@/types/home'

/** 活动轮播容器自身的模块键，既是排序里的一格，也是整组游戏卡的总开关 */
export const HOME_ACTIVITY_CAROUSEL_KEY: HomeModuleKey = 'activities'

/** 进入轮播的游戏活动卡；这里的相对顺序就是轮播的切换顺序 */
export const HOME_ACTIVITY_MODULE_KEYS: HomeModuleKey[] = [
  'endfield',
  'starrail',
  'genshin',
  'zenless',
  'wutheringwaves',
  'nte',
  'reverse1999',
  'arknights',
]

export const defaultHomeModuleOrder: HomeModuleKey[] = [
  'command',
  'quick',
  'satellite',
  'proxy',
  HOME_ACTIVITY_CAROUSEL_KEY,
  ...HOME_ACTIVITY_MODULE_KEYS,
]

export const isHomeModuleKey = (value: unknown): value is HomeModuleKey => {
  return typeof value === 'string' && defaultHomeModuleOrder.includes(value as HomeModuleKey)
}

export const isHomeActivityModuleKey = (key: HomeModuleKey): boolean => {
  return HOME_ACTIVITY_MODULE_KEYS.includes(key)
}

const normalizeModuleKeys = (value: unknown): HomeModuleKey[] => {
  const keys = Array.isArray(value) ? value.filter(isHomeModuleKey) : []
  return keys.filter((key, index, array) => array.indexOf(key) === index)
}

/**
 * 旧配置里没有轮播模块，补齐时会被追加到最末尾——那样升级后整个活动区
 * 会突然掉到首页底部。这里让轮播顶替用户原来第一张游戏活动卡的位置。
 */
const placeCarousel = (order: HomeModuleKey[]): HomeModuleKey[] => {
  const rest: HomeModuleKey[] = order.filter(key => key !== HOME_ACTIVITY_CAROUSEL_KEY)
  const firstActivityIndex = rest.findIndex(isHomeActivityModuleKey)
  const insertAt = firstActivityIndex === -1 ? rest.length : firstActivityIndex
  rest.splice(insertAt, 0, HOME_ACTIVITY_CAROUSEL_KEY)
  return rest
}

export const normalizeHomeLayoutConfig = (value: unknown): HomeLayoutConfig => {
  const config =
    typeof value === 'object' && value !== null ? (value as Partial<HomeLayoutConfig>) : {}
  const configuredOrder = normalizeModuleKeys(config.moduleOrder)
  const missingModules = defaultHomeModuleOrder.filter(key => !configuredOrder.includes(key))
  const mergedOrder = [...configuredOrder, ...missingModules]
  const isMigration = !configuredOrder.includes(HOME_ACTIVITY_CAROUSEL_KEY)
  const hiddenModules = normalizeModuleKeys(config.hiddenModules)

  // 老配置里八张游戏卡全关了，等价于整块都不要；补键时顺手把总闸也关掉，
  // 否则升级后会凭空多出一张「轮播里的游戏都关掉了」的提示卡
  if (isMigration && HOME_ACTIVITY_MODULE_KEYS.every(key => hiddenModules.includes(key))) {
    hiddenModules.push(HOME_ACTIVITY_CAROUSEL_KEY)
  }

  return {
    moduleOrder: isMigration ? placeCarousel(mergedOrder) : mergedOrder,
    hiddenModules,
    hideScrollHint: config.hideScrollHint === true,
    // 未写过这项的老配置按开启处理，与新装用户保持一致
    carouselAutoplay: config.carouselAutoplay !== false,
  }
}
