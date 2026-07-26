import { describe, expect, it } from 'vitest'
import { FALLBACK_PAGE_DECLARATIONS } from '@/router/pageDeclarations.ts'
import {
  buildGlobalSearchGroups,
  matchesKeyword,
  GLOBAL_SEARCH_GROUP_LIMIT,
  SCRIPT_SEARCH_ITEM_KEY,
  SETTING_SEARCH_ENTRIES,
  type PluginInstanceLike,
} from './globalSearch.ts'

const navPages = FALLBACK_PAGE_DECLARATIONS.filter(page => !page.dev_only)

const pluginInstances: PluginInstanceLike[] = [
  { id: 'maa-1', name: 'MAA 日常', plugin: 'MaaFW' },
  { id: 'hsr-1', name: '星穹铁道签到', plugin: 'HSR' },
]

describe('globalSearch 匹配逻辑', () => {
  it('模糊匹配：不区分大小写的子串命中', () => {
    expect(matchesKeyword('插件管理', '插件')).toBe(true)
    expect(matchesKeyword('MaaFW', 'maafw')).toBe(true)
    expect(matchesKeyword('MaaFW', 'AAF')).toBe(true)
    expect(matchesKeyword('插件管理', '管理插')).toBe(false)
    expect(matchesKeyword('任何文本', '')).toBe(false)
    expect(matchesKeyword('任何文本', '   ')).toBe(false)
  })

  it('空关键字不产生任何分组', () => {
    expect(buildGlobalSearchGroups('', navPages, pluginInstances)).toEqual([])
    expect(buildGlobalSearchGroups('   ', navPages, pluginInstances)).toEqual([])
  })

  it('导航页面名可被搜索并跳转对应路由', () => {
    const groups = buildGlobalSearchGroups('插件', navPages, [])
    const pagesGroup = groups.find(group => group.key === 'pages')

    expect(pagesGroup).toBeDefined()
    const labels = pagesGroup!.items.map(item => item.label)
    expect(labels).toContain('插件管理')
    expect(labels).toContain('插件市场')

    const manageItem = pagesGroup!.items.find(item => item.label === '插件管理')
    expect(manageItem!.target).toEqual({ path: '/plugins' })
  })

  it('所有主导航页面名均可精确命中', () => {
    const expected: Array<[string, string]> = [
      ['主页', '/home'],
      ['脚本管理', '/scripts'],
      ['计划管理', '/plans'],
      ['游戏与模拟器', '/game-center'],
      ['插件管理', '/plugins'],
      ['插件市场', '/plugins-market'],
      ['调度队列', '/queue'],
      ['调度中心', '/scheduler'],
      ['历史记录', '/history'],
      ['工具', '/tools'],
      ['设置', '/settings'],
    ]

    for (const [label, path] of expected) {
      const groups = buildGlobalSearchGroups(label, navPages, [])
      const pagesGroup = groups.find(group => group.key === 'pages')
      const item = pagesGroup?.items.find(candidate => candidate.target.path === path)
      expect(item, `页面 ${label} 应可被搜索`).toBeDefined()
    }
  })

  it('设置分组标题命中后跳 /settings 并带 tab/section query', () => {
    const groups = buildGlobalSearchGroups('托盘', navPages, [])
    const settingsGroup = groups.find(group => group.key === 'settings')

    expect(settingsGroup).toBeDefined()
    const trayItem = settingsGroup!.items.find(item => item.label === '系统托盘')
    expect(trayItem).toBeDefined()
    expect(trayItem!.target.path).toBe('/settings')
    expect(trayItem!.target.query).toEqual({ tab: 'basic', section: '系统托盘' })
  })

  it('设置 tab 标题本身也可命中（仅带 tab query）', () => {
    const groups = buildGlobalSearchGroups('通知', navPages, [])
    const settingsGroup = groups.find(group => group.key === 'settings')

    const tabItem = settingsGroup!.items.find(
      item => item.label === '通知' && !item.target.query?.section
    )
    expect(tabItem).toBeDefined()
    expect(tabItem!.target.query).toEqual({ tab: 'notify' })
  })

  it('设置静态表覆盖设置页全部五个 tab', () => {
    const tabs = new Set(SETTING_SEARCH_ENTRIES.map(entry => entry.tab))
    expect([...tabs].sort()).toEqual(['advanced', 'basic', 'function', 'notify', 'others'])
    // 每个 tab 至少包含 tab 本身与一个分组标题
    for (const tab of tabs) {
      const entries = SETTING_SEARCH_ENTRIES.filter(entry => entry.tab === tab)
      expect(entries.some(entry => !entry.section)).toBe(true)
      expect(entries.some(entry => Boolean(entry.section))).toBe(true)
    }
  })

  it('插件实例名命中后跳 /plugins', () => {
    const groups = buildGlobalSearchGroups('签到', navPages, pluginInstances)
    const pluginsGroup = groups.find(group => group.key === 'plugins')

    expect(pluginsGroup).toBeDefined()
    expect(pluginsGroup!.items).toHaveLength(1)
    expect(pluginsGroup!.items[0].label).toBe('星穹铁道签到')
    expect(pluginsGroup!.items[0].target.path).toBe('/plugins')
  })

  it('插件实例也可按插件类型名模糊命中（不区分大小写）', () => {
    const groups = buildGlobalSearchGroups('maafw', navPages, pluginInstances)
    const pluginsGroup = groups.find(group => group.key === 'plugins')

    expect(pluginsGroup).toBeDefined()
    expect(pluginsGroup!.items[0].label).toBe('MAA 日常')
  })

  it('脚本分组保留原有行为：始终提供脚本管理搜索入口', () => {
    const groups = buildGlobalSearchGroups('不存在的东西xyz', navPages, pluginInstances)

    expect(groups).toHaveLength(1)
    expect(groups[0].key).toBe('scripts')
    expect(groups[0].items[0].key).toBe(SCRIPT_SEARCH_ITEM_KEY)
    expect(groups[0].items[0].target).toEqual({
      path: '/scripts',
      query: { search: '不存在的东西xyz' },
    })
  })

  it('分组顺序固定为 页面 → 设置 → 插件 → 脚本', () => {
    // “设置”同时命中：页面(设置页)、设置静态表(keywords 含“设置”)、插件实例名
    const groups = buildGlobalSearchGroups('设置', navPages, [
      { id: 'p1', name: '设置助手插件', plugin: 'Demo' },
    ])
    expect(groups.map(group => group.key)).toEqual(['pages', 'settings', 'plugins', 'scripts'])
  })

  it('每个分组的条目数不超过上限', () => {
    const manyInstances: PluginInstanceLike[] = Array.from({ length: 20 }, (_, index) => ({
      id: `id-${index}`,
      name: `批量实例 ${index}`,
      plugin: 'Bulk',
    }))
    const groups = buildGlobalSearchGroups('批量实例', navPages, manyInstances)
    const pluginsGroup = groups.find(group => group.key === 'plugins')

    expect(pluginsGroup!.items.length).toBeLessThanOrEqual(GLOBAL_SEARCH_GROUP_LIMIT)
  })

  it('隐藏页面与重复路径不进入结果', () => {
    const pages = [
      ...navPages,
      { ...navPages[0], id: 'home-dup' },
      { ...navPages[0], id: 'hidden', path: '/hidden', menu_label: '隐藏页', visible: false },
    ]
    const groups = buildGlobalSearchGroups('主页', pages, [])
    const pagesGroup = groups.find(group => group.key === 'pages')
    expect(pagesGroup!.items.filter(item => item.target.path === '/home')).toHaveLength(1)

    const hiddenGroups = buildGlobalSearchGroups('隐藏页', pages, [])
    expect(hiddenGroups.find(group => group.key === 'pages')).toBeUndefined()
  })
})
