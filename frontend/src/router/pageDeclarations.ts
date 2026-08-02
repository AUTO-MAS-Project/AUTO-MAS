import type { RouteRecordRaw, Router } from 'vue-router'

export interface PageDeclaration {
  id: string
  path: string
  title: string
  menu_label: string
  icon: string
  component: string
  renderer: 'component' | 'iframe' | 'custom-element' | string
  url: string | null
  frontend_plugin: string | null
  element_tag: string | null
  entry_asset_url: string | null
  style_asset_urls: string[]
  manifest_version: number | null
  dev_frontend_command?: string | null
  dev_frontend_error?: string | null
  section: 'main' | 'bottom' | 'dev' | string
  order: number
  visible: boolean
  dev_only: boolean
  source: string
}

const SchedulerView = () => import('../views/scheduler/index.vue')
const PluginPageHostView = () => import('../views/PluginPageHost.vue')
const PluginElementHostView = () => import('../views/PluginElementHost.vue')

export const PAGE_COMPONENTS: Record<string, RouteRecordRaw['component']> = {
  Home: () => import('../views/Home.vue'),
  Scripts: () => import('../views/Scripts.vue'),
  Plans: () => import('../views/plan/index.vue'),
  Emulators: () => import('../views/Emulator.vue'),
  Plugin: () => import('../views/Plugin.vue'),
  PluginMarket: () => import('../views/PluginMarket.vue'),
  Queue: () => import('../views/queue/index.vue'),
  Scheduler: SchedulerView,
  History: () => import('../views/history/index.vue'),
  Tools: () => import('../views/tools/index.vue'),
  Settings: () => import('../views/setting/index.vue'),
  TestRouter: () => import('../views/TestRouter.vue'),
  OCRdev: () => import('../views/OCRdev.vue'),
  OverlayMaskDev: () => import('../views/OverlayMaskDev.vue'),
}

const BUILTIN_ROUTE_NAMES: Record<string, string> = {
  home: 'Home',
  scripts: 'Scripts',
  plans: 'Plans',
  emulators: 'Emulators',
  plugins: 'Plugin',
  'plugins-market': 'PluginMarket',
  queue: 'Queue',
  scheduler: 'Scheduler',
  history: 'History',
  tools: 'Tools',
  settings: 'Settings',
  'test-router': 'TestRouter',
  'ocr-dev': 'OCRdev',
  'overlay-mask-dev': 'OverlayMaskDev',
}

function hostPage(
  id: string,
  path: string,
  title: string,
  icon: string,
  component: string,
  section: 'main' | 'bottom' | 'dev',
  order: number,
  devOnly = false
): PageDeclaration {
  return {
    id,
    path,
    title,
    menu_label: title,
    icon,
    component,
    renderer: 'component',
    url: null,
    frontend_plugin: null,
    element_tag: null,
    entry_asset_url: null,
    style_asset_urls: [],
    manifest_version: null,
    dev_frontend_command: null,
    dev_frontend_error: null,
    section,
    order,
    visible: true,
    dev_only: devOnly,
    source: 'host:core',
  }
}

export const FALLBACK_PAGE_DECLARATIONS: PageDeclaration[] = [
  hostPage('home', '/home', '主页', 'home', 'Home', 'main', 10),
  hostPage('scripts', '/scripts', '脚本管理', 'script', 'Scripts', 'main', 20),
  hostPage('plans', '/plans', '计划管理', 'plan', 'Plans', 'main', 30),
  hostPage('plugins', '/plugins', '插件管理', 'plugin', 'Plugin', 'main', 50),
  hostPage('plugins-market', '/plugins-market', '插件市场', 'market', 'PluginMarket', 'main', 60),
  hostPage('queue', '/queue', '调度队列', 'queue', 'Queue', 'main', 70),
  hostPage('scheduler', '/scheduler', '调度中心', 'scheduler', 'Scheduler', 'main', 80),
  hostPage('history', '/history', '历史记录', 'history', 'History', 'bottom', 10),
  hostPage('tools', '/tools', '工具', 'tool', 'Tools', 'bottom', 20),
  hostPage('settings', '/settings', '设置', 'settings', 'Settings', 'bottom', 30),
  hostPage('test-router', '/TestRouter', '测试路由', 'dev', 'TestRouter', 'dev', 10, true),
  hostPage('ocr-dev', '/OCRdev', 'OCR 测试', 'dev', 'OCRdev', 'dev', 20, true),
  hostPage(
    'overlay-mask-dev',
    '/OverlayMaskDev',
    '遮罩测试',
    'dev',
    'OverlayMaskDev',
    'dev',
    40,
    true
  ),
]

export function normalizePageDeclarations(raw: unknown): PageDeclaration[] {
  if (!Array.isArray(raw)) {
    return FALLBACK_PAGE_DECLARATIONS
  }

  const pages = raw
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    .map(item => ({
      id: String(item.id || '').trim(),
      path: normalizePath(String(item.path || '')),
      title: String(item.title || '').trim(),
      menu_label: String(item.menu_label || item.title || '').trim(),
      icon: String(item.icon || 'app').trim(),
      component: String(item.component || 'PluginPage').trim(),
      renderer: String(item.renderer || 'component').trim(),
      url: normalizeOptionalText(item.url),
      frontend_plugin: normalizeOptionalText(item.frontend_plugin),
      element_tag: normalizeOptionalText(item.element_tag),
      entry_asset_url: normalizeOptionalText(item.entry_asset_url),
      style_asset_urls: normalizeStringList(item.style_asset_urls),
      manifest_version: normalizeOptionalNumber(item.manifest_version),
      dev_frontend_command: normalizeOptionalText(item.dev_frontend_command),
      dev_frontend_error: normalizeOptionalText(item.dev_frontend_error),
      section: String(item.section || 'main').trim(),
      order: Number.isFinite(Number(item.order)) ? Number(item.order) : 1000,
      visible: item.visible !== false,
      dev_only: item.dev_only === true,
      source: String(item.source || '').trim(),
    }))
    .filter(page => page.id && page.path && page.title && page.menu_label && canRenderPage(page))

  return pages.length > 0 ? sortPageDeclarations(pages) : FALLBACK_PAGE_DECLARATIONS
}

export function sortPageDeclarations(pages: PageDeclaration[]): PageDeclaration[] {
  return [...pages].sort((a, b) => {
    const sectionOrder = sectionRank(a.section) - sectionRank(b.section)
    if (sectionOrder !== 0) return sectionOrder
    const orderDelta = a.order - b.order
    if (orderDelta !== 0) return orderDelta
    return a.menu_label.localeCompare(b.menu_label)
  })
}

export function createPageRoutes(pages: PageDeclaration[]): RouteRecordRaw[] {
  return pages.map(createPageRoute).filter((route): route is RouteRecordRaw => route !== null)
}

export function syncDeclaredPageRoutes(router: Router, pages: PageDeclaration[]): void {
  const routes = createPageRoutes(pages)
  const nextRouteNames = new Set(routes.map(route => String(route.name)))

  for (const existingRoute of router.getRoutes()) {
    const routeName = existingRoute.name ? String(existingRoute.name) : ''
    if (routeName.startsWith('page:') && !nextRouteNames.has(routeName)) {
      router.removeRoute(routeName)
    }
  }

  for (const route of routes) {
    const routeName = String(route.name)
    if (router.hasRoute(routeName)) {
      if (routeName.startsWith('page:')) {
        router.removeRoute(routeName)
      } else {
        continue
      }
    }

    const existsByPath = router.getRoutes().find(item => item.path === route.path)
    if (existsByPath) {
      const existsName = existsByPath.name ? String(existsByPath.name) : ''
      if (existsName.startsWith('page:')) {
        router.removeRoute(existsName)
      } else {
        continue
      }
    }

    router.addRoute(route)
  }
}

function createPageRoute(page: PageDeclaration): RouteRecordRaw | null {
  const routeComponent = resolveRouteComponent(page)
  if (!routeComponent) {
    return null
  }

  const usesHostProps = page.renderer === 'iframe' || page.renderer === 'custom-element'
  return {
    path: page.path,
    name: BUILTIN_ROUTE_NAMES[page.id] || `page:${page.id}`,
    component: routeComponent,
    props: usesHostProps ? { page } : undefined,
    meta: {
      title: page.title,
      keepAlive: page.component === 'Scheduler',
      declaredPage: true,
      pageId: page.id,
      page,
    },
  }
}

function resolveRouteComponent(page: PageDeclaration): RouteRecordRaw['component'] | null {
  if (page.renderer === 'iframe') {
    return PluginPageHostView
  }
  if (page.renderer === 'custom-element') {
    return PluginElementHostView
  }
  return PAGE_COMPONENTS[page.component] || null
}

function canRenderPage(page: PageDeclaration): boolean {
  if (page.renderer === 'iframe') {
    return true
  }
  if (page.renderer === 'custom-element') {
    return true
  }
  return Boolean(PAGE_COMPONENTS[page.component])
}

function normalizeOptionalText(raw: unknown): string | null {
  if (raw === null || raw === undefined) {
    return null
  }
  const text = String(raw || '').trim()
  return text || null
}

function normalizeOptionalNumber(raw: unknown): number | null {
  if (raw === null || raw === undefined || raw === '') {
    return null
  }
  const value = Number(raw)
  return Number.isFinite(value) ? value : null
}

function normalizeStringList(raw: unknown): string[] {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw.map(item => String(item || '').trim()).filter(Boolean)
}

function normalizePath(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) {
    return ''
  }
  const normalized = `/${trimmed.replace(/^\/+/, '')}`.replace(/\/+/g, '/')
  if (normalized !== '/' && normalized.endsWith('/')) {
    return normalized.slice(0, -1)
  }
  return normalized
}

function sectionRank(section: string): number {
  if (section === 'main') return 0
  if (section === 'bottom') return 1
  if (section === 'dev') return 2
  return 3
}
