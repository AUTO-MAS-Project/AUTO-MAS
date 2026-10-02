import type { HomeLayoutConfig, HomeModuleKey } from '@/types/home'

/** 活动轮播容器自身的模块键，既是排序里的一格，也是整组游戏卡的总开关 */
export const HOME_ACTIVITY_CAROUSEL_KEY: HomeModuleKey = 'activities'

/**
 * 活动轮播上线时就有的游戏卡。
 *
 * 迁移判断只认这一批：老配置里用户根本没见过后补的卡，若把新卡也算进
 * 「全关」判断，那个判断就永远不会成立，于是升级后会凭空多出一张卡。
 */
export const CAROUSEL_ERA_MODULE_KEYS: HomeModuleKey[] = [
  'endfield',
  'starrail',
  'genshin',
  'zenless',
  'wutheringwaves',
  'nte',
  'reverse1999',
  'bluearchive',
  'arknights',
]

/** 进入轮播的游戏活动卡；这里的相对顺序就是轮播的切换顺序 */
export const HOME_ACTIVITY_MODULE_KEYS: HomeModuleKey[] = [
  ...CAROUSEL_ERA_MODULE_KEYS,
  'stellasora',
]

/** 已接入日常便笺的游戏，提供首页社区信息的独立开关。 */
export const HOME_ACTIVITY_NOTE_KEYS: HomeModuleKey[] = [
  'endfield',
  'starrail',
  'genshin',
  'zenless',
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

  // 老配置里游戏卡全关了，等价于整块都不要；补键时顺手把总闸也关掉，
  // 否则升级后会凭空多出一张「轮播里的游戏都关掉了」的提示卡
  if (isMigration && CAROUSEL_ERA_MODULE_KEYS.every(key => hiddenModules.includes(key))) {
    hiddenModules.push(HOME_ACTIVITY_CAROUSEL_KEY)
  }

  return {
    moduleOrder: isMigration ? placeCarousel(mergedOrder) : mergedOrder,
    hiddenModules,
    hideScrollHint: config.hideScrollHint === true,
    // 新装及缺少该字段的旧配置统一默认关闭，避免阅读时自动切换；保留显式开启的选择。
    carouselAutoplay: config.carouselAutoplay === true,
    // 首页便笺默认不展示：新装与旧配置都保持关闭，用户在游戏社区设置里打开总开关。
    activityNotesVisible: config.activityNotesVisible === true,
    hiddenActivityNotes: normalizeModuleKeys(config.hiddenActivityNotes),
  }
}
