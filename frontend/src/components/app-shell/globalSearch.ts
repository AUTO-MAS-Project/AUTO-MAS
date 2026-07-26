/**
 * 全局搜索数据源、匹配逻辑与搜索会话状态机（供 GlobalSearch.vue 与单元测试复用）。
 *
 * 数据源：
 * 1. pages    —— 导航页面声明（AppSider 传入的 main/dev/bottom 菜单项）
 * 2. settings —— 设置页 tab 与分组标题静态表（源自 src/views/setting/index.vue
 *                的 settingNavItems 与各 Tab*.vue 的 section-header <h3>）
 * 3. plugins  —— 已安装插件实例名（/api/plugins/get 快照）
 * 4. scripts  —— 保留原有「跳转脚本管理搜索」行为
 *
 * 各数据源互相独立：任一来源为空/拉取失败只影响自身分组，静态源始终可命中。
 */

import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import type { PageDeclaration } from '@/router/pageDeclarations.ts'

export interface GlobalSearchTarget {
  path: string
  query?: Record<string, string>
}

export interface GlobalSearchItem {
  key: string
  label: string
  /** 次级说明文字（展示在条目右侧） */
  note?: string
  /** 额外参与模糊匹配的文本 */
  keywords?: string[]
  target: GlobalSearchTarget
}

export type GlobalSearchGroupKey = 'pages' | 'settings' | 'plugins' | 'scripts'

export interface GlobalSearchGroup {
  key: GlobalSearchGroupKey
  label: string
  items: GlobalSearchItem[]
}

export interface PluginInstanceLike {
  id: string
  name: string
  plugin?: string
}

export type SettingTabKey = 'basic' | 'function' | 'notify' | 'advanced' | 'others'

export interface SettingSearchEntry {
  tab: SettingTabKey
  tabLabel: string
  /** 缺省表示 tab 本身；否则为该 tab 下的分组标题 */
  section?: string
}

/**
 * 设置页静态表。
 * tab 定义源：src/views/setting/index.vue settingNavItems；
 * 分组标题源：src/views/setting/Tab*.vue 中 .section-header h3。
 * 设置页结构变更时需同步维护（globalSearch.test.ts 有覆盖度断言）。
 */
export const SETTING_SEARCH_ENTRIES: SettingSearchEntry[] = [
  { tab: 'basic', tabLabel: '界面' },
  { tab: 'basic', tabLabel: '界面', section: '外观' },
  { tab: 'basic', tabLabel: '界面', section: '性能' },
  { tab: 'basic', tabLabel: '界面', section: '系统托盘' },
  { tab: 'basic', tabLabel: '界面', section: '窗口控制' },
  { tab: 'basic', tabLabel: '界面', section: '日志样式' },
  { tab: 'function', tabLabel: '功能' },
  { tab: 'function', tabLabel: '功能', section: '启动' },
  { tab: 'function', tabLabel: '功能', section: '功能' },
  { tab: 'function', tabLabel: '功能', section: '语音' },
  { tab: 'notify', tabLabel: '通知' },
  { tab: 'notify', tabLabel: '通知', section: '通知内容' },
  { tab: 'notify', tabLabel: '通知', section: '系统通知' },
  { tab: 'notify', tabLabel: '通知', section: '邮件通知' },
  { tab: 'notify', tabLabel: '通知', section: 'Server酱通知' },
  { tab: 'notify', tabLabel: '通知', section: 'Koishi 通知' },
  { tab: 'notify', tabLabel: '通知', section: '自定义 Webhook 通知' },
  { tab: 'advanced', tabLabel: '日志' },
  { tab: 'advanced', tabLabel: '日志', section: '日志导出' },
  { tab: 'advanced', tabLabel: '日志', section: '开发者选项' },
  { tab: 'others', tabLabel: '关于' },
  { tab: 'others', tabLabel: '关于', section: '更新配置' },
  { tab: 'others', tabLabel: '关于', section: '项目链接' },
  { tab: 'others', tabLabel: '关于', section: '应用信息' },
]

/** 每个分组最多展示的条目数，避免下拉过长 */
export const GLOBAL_SEARCH_GROUP_LIMIT = 8

/** 模糊匹配：不区分大小写的子串匹配 */
export function matchesKeyword(text: string, keyword: string): boolean {
  const needle = keyword.trim().toLowerCase()
  if (!needle) return false
  return text.toLowerCase().includes(needle)
}

const itemMatches = (item: GlobalSearchItem, keyword: string): boolean => {
  if (matchesKeyword(item.label, keyword)) return true
  return (item.keywords || []).some(text => matchesKeyword(text, keyword))
}

const buildPageItems = (pages: PageDeclaration[]): GlobalSearchItem[] => {
  const seenPaths = new Set<string>()
  const items: GlobalSearchItem[] = []
  for (const page of pages) {
    if (!page || page.visible === false || !page.path) continue
    if (seenPaths.has(page.path)) continue
    seenPaths.add(page.path)
    items.push({
      key: `page:${page.path}`,
      label: page.menu_label || page.title,
      note: '页面',
      keywords: [page.title, page.path, page.id].filter(Boolean),
      target: { path: page.path },
    })
  }
  return items
}

const buildSettingItems = (): GlobalSearchItem[] =>
  SETTING_SEARCH_ENTRIES.map(entry => {
    const isSection = Boolean(entry.section)
    const query: Record<string, string> = { tab: entry.tab }
    if (entry.section) query.section = entry.section
    return {
      key: `setting:${entry.tab}${entry.section ? `:${entry.section}` : ''}`,
      label: entry.section || entry.tabLabel,
      note: isSection ? `设置 · ${entry.tabLabel}` : '设置',
      keywords: isSection ? [entry.tabLabel, '设置'] : ['设置'],
      target: { path: '/settings', query },
    }
  })

const buildPluginItems = (instances: PluginInstanceLike[]): GlobalSearchItem[] =>
  instances
    .filter(instance => instance && instance.id && instance.name)
    .map(instance => ({
      key: `plugin:${instance.id}`,
      label: instance.name,
      note: instance.plugin ? `插件 · ${instance.plugin}` : '插件',
      keywords: instance.plugin ? [instance.plugin] : [],
      target: { path: '/plugins', query: { instance: instance.id } },
    }))

export const SCRIPT_SEARCH_ITEM_KEY = 'scripts:search'

/**
 * 构建分组后的搜索结果。空关键字返回空数组。
 * 分组顺序：页面 → 设置 → 插件 → 脚本。
 * 「脚本」分组保留原有行为：始终提供跳转脚本管理搜索的入口。
 */
export function buildGlobalSearchGroups(
  keyword: string,
  pages: PageDeclaration[],
  pluginInstances: PluginInstanceLike[]
): GlobalSearchGroup[] {
  const trimmed = keyword.trim()
  if (!trimmed) return []

  const groups: GlobalSearchGroup[] = []
  const pushGroup = (key: GlobalSearchGroupKey, label: string, items: GlobalSearchItem[]) => {
    const matched = items
      .filter(item => itemMatches(item, trimmed))
      .slice(0, GLOBAL_SEARCH_GROUP_LIMIT)
    if (matched.length > 0) {
      groups.push({ key, label, items: matched })
    }
  }

  pushGroup('pages', '页面', buildPageItems(pages))
  pushGroup('settings', '设置', buildSettingItems())
  pushGroup('plugins', '插件', buildPluginItems(pluginInstances))

  groups.push({
    key: 'scripts',
    label: '脚本',
    items: [
      {
        key: SCRIPT_SEARCH_ITEM_KEY,
        label: `在脚本管理中搜索「${trimmed}」`,
        note: '脚本',
        target: { path: '/scripts', query: { search: trimmed } },
      },
    ],
  })

  return groups
}

// ═══════════════════════════════════════════════════════════════
// 搜索会话状态机（展开态内联输入框 + 折叠态弹层共用）
// ═══════════════════════════════════════════════════════════════

export interface GlobalSearchSessionOptions {
  /** 读取侧栏折叠态（传 getter 以保持响应式） */
  isCollapsed: () => boolean
}

export interface GlobalSearchSession {
  keyword: Ref<string>
  activeIndex: Ref<number>
  /** 折叠态：右侧弹层开关 */
  popoverOpen: Ref<boolean>
  /** 展开态：内联输入框是否展开 */
  inlineExpanded: Ref<boolean>
  /** 展开态：内联输入框是否持有焦点 */
  inlineFocused: Ref<boolean>
  hasKeyword: ComputedRef<boolean>
  /** 展开态结果弹层开关：展开 + 聚焦 + 有关键字 */
  inlinePanelOpen: ComputedRef<boolean>
  openInline: () => void
  focusInline: () => void
  blurInline: () => void
  /**
   * 结束一次搜索会话（激活条目跳转 / Enter 提交 / Esc）：
   * 收回内联输入框并清空关键字，下一次搜索从干净状态开始。
   * 这是「跳转后再搜索无结果」的修复核心——旧实现只清 inlineFocused
   * 标志位，而 mousedown.prevent 让输入框仍持有 DOM 焦点，再次点击
   * 不会触发 focus 事件，面板从此无法再打开。
   */
  reset: () => void
  /** 侧栏折叠时收回内联搜索，保持干净的导航层级 */
  handleCollapsedChange: (collapsed: boolean) => void
}

export function createGlobalSearchSession(
  options: GlobalSearchSessionOptions
): GlobalSearchSession {
  const keyword = ref('')
  const activeIndex = ref(-1)
  const popoverOpen = ref(false)
  const inlineExpanded = ref(false)
  const inlineFocused = ref(false)

  const hasKeyword = computed(() => keyword.value.trim() !== '')
  const inlinePanelOpen = computed(
    () => !options.isCollapsed() && inlineExpanded.value && inlineFocused.value && hasKeyword.value
  )

  watch(keyword, value => {
    activeIndex.value = -1
    // 自愈：非空关键字只可能来自用户键入，键入必然发生在持有焦点的输入框里。
    // 即便 focus 事件因状态失同步而丢失（如 mousedown.prevent 保焦后关闭面板），
    // 这里也会把 inlineFocused 拉回 true，保证「输入了就有下拉」。
    if (value.trim() !== '' && !options.isCollapsed() && inlineExpanded.value) {
      inlineFocused.value = true
    }
  })

  const openInline = () => {
    inlineExpanded.value = true
  }
  const focusInline = () => {
    inlineFocused.value = true
  }
  const blurInline = () => {
    inlineFocused.value = false
  }
  const reset = () => {
    popoverOpen.value = false
    inlineExpanded.value = false
    inlineFocused.value = false
    keyword.value = ''
    activeIndex.value = -1
  }
  const handleCollapsedChange = (collapsed: boolean) => {
    if (collapsed) {
      inlineExpanded.value = false
      inlineFocused.value = false
      keyword.value = ''
    }
  }

  return {
    keyword,
    activeIndex,
    popoverOpen,
    inlineExpanded,
    inlineFocused,
    hasKeyword,
    inlinePanelOpen,
    openInline,
    focusInline,
    blurInline,
    reset,
    handleCollapsedChange,
  }
}
