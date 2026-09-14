import { describe, expect, it } from 'vitest'
import {
  HOME_ACTIVITY_CAROUSEL_KEY,
  HOME_ACTIVITY_MODULE_KEYS,
  defaultHomeModuleOrder,
  normalizeHomeLayoutConfig,
} from './homeLayoutConfig'

describe('normalizeHomeLayoutConfig', () => {
  it('新装用户拿到的默认顺序里，轮播排在代理状态之后、游戏卡之前', () => {
    const layout = normalizeHomeLayoutConfig({})
    expect(layout.moduleOrder).toEqual(defaultHomeModuleOrder)
    expect(layout.moduleOrder.indexOf(HOME_ACTIVITY_CAROUSEL_KEY)).toBe(
      layout.moduleOrder.indexOf('proxy') + 1
    )
  })

  it('老配置补齐轮播时，让它顶替第一张游戏活动卡的位置而不是掉到末尾', () => {
    const layout = normalizeHomeLayoutConfig({
      moduleOrder: ['command', 'starrail', 'quick', 'genshin', 'proxy'],
      hiddenModules: [],
    })

    const order = layout.moduleOrder
    expect(order.indexOf(HOME_ACTIVITY_CAROUSEL_KEY)).toBe(order.indexOf('starrail') - 1)
    expect(order[0]).toBe('command')
    // 游戏卡之间的相对顺序就是轮播顺序，迁移不能打乱
    expect(order.indexOf('starrail')).toBeLessThan(order.indexOf('genshin'))
  })

  it('已经带轮播的配置原样保留顺序，不再重新摆放', () => {
    const saved = normalizeHomeLayoutConfig({
      moduleOrder: ['command', 'starrail', 'quick', 'genshin', 'proxy'],
      hiddenModules: ['genshin'],
    })

    expect(normalizeHomeLayoutConfig(saved)).toEqual(saved)
  })

  it('老配置里八张游戏卡全关时，补键顺手关掉总闸，不留一张空提示卡', () => {
    const layout = normalizeHomeLayoutConfig({
      moduleOrder: ['command', 'quick'],
      hiddenModules: [...HOME_ACTIVITY_MODULE_KEYS],
    })

    expect(layout.hiddenModules).toContain(HOME_ACTIVITY_CAROUSEL_KEY)
  })

  it('只关掉部分游戏时不动总闸', () => {
    const layout = normalizeHomeLayoutConfig({
      moduleOrder: ['command', 'quick'],
      hiddenModules: HOME_ACTIVITY_MODULE_KEYS.slice(1),
    })

    expect(layout.hiddenModules).not.toContain(HOME_ACTIVITY_CAROUSEL_KEY)
  })

  it('已经带轮播的配置不会因为全关游戏就自动关掉总闸', () => {
    const layout = normalizeHomeLayoutConfig({
      moduleOrder: defaultHomeModuleOrder,
      hiddenModules: [...HOME_ACTIVITY_MODULE_KEYS],
    })

    expect(layout.hiddenModules).not.toContain(HOME_ACTIVITY_CAROUSEL_KEY)
  })

  it('缺省视为开启自动轮播，显式关闭时保留', () => {
    expect(normalizeHomeLayoutConfig({}).carouselAutoplay).toBe(true)
    expect(normalizeHomeLayoutConfig({ carouselAutoplay: false }).carouselAutoplay).toBe(false)
  })

  it('丢弃未知模块键并去重', () => {
    const layout = normalizeHomeLayoutConfig({
      moduleOrder: ['quick', 'nope', 'quick', 'command'],
      hiddenModules: ['genshin', 'nope', 'genshin'],
    })

    expect(layout.moduleOrder.filter(key => key === 'quick')).toHaveLength(1)
    expect(layout.moduleOrder).toContain('command')
    expect(layout.hiddenModules).toEqual(['genshin'])
  })

  it('补齐后仍然覆盖全部模块，不会漏掉任何一张卡', () => {
    const layout = normalizeHomeLayoutConfig({ moduleOrder: ['arknights'], hiddenModules: [] })
    expect([...layout.moduleOrder].sort()).toEqual([...defaultHomeModuleOrder].sort())
  })
})
