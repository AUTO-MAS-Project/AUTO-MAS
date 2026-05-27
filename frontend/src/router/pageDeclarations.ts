import type { RouteRecordRaw, Router } from 'vue-router'

export interface PageDeclaration {
  id: string
  path: string
  title: string
  menu_label: string
  icon: string
  component: string
  renderer: 'component' | 'iframe' | string
  url: string | null
  section: 'main' | 'bottom' | 'dev' | string
  order: number
  visible: boolean
  dev_only: boolean
  source: string
}

const SchedulerView = () => import('../views/scheduler/index.vue')
const PluginPageHostView = () => import('../views/PluginPageHost.vue')

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
  WSdev: () => import('../views/WSdev.vue'),
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
  'ws-dev': 'WSdev',
  'overlay-mask-dev': 'OverlayMaskDev',
}

export const FALLBACK_PAGE_DECLARATIONS: PageDeclaration[] = [
  {
    id: 'home',
    path: '/home',
    title: '\u4e3b\u9875',
    menu_label: '\u4e3b\u9875',
    icon: 'home',
    component: 'Home',
    renderer: 'component',
    url: null,
    section: 'main',
    order: 10,
    visible: true,
    dev_only: false,
    source: 'host:core',
  },
  {
    id: 'scripts',
    path: '/scripts',
    title: '\u811a\u672c\u7ba1\u7406',
    menu_label: '\u811a\u672c\u7ba1\u7406',
    icon: 'script',
    component: 'Scripts',
    renderer: 'component',
    url: null,
    section: 'main',
    order: 20,
    visible: true,
    dev_only: false,
    source: 'host:core',
  },
  {
    id: 'plans',
    path: '/plans',
    title: '\u8ba1\u5212\u7ba1\u7406',
    menu_label: '\u8ba1\u5212\u7ba1\u7406',
    icon: 'plan',
    component: 'Plans',
    renderer: 'component',
    url: null,
    section: 'main',
    order: 30,
    visible: true,
    dev_only: false,
    source: 'host:core',
  },
  {
    id: 'emulators',
    path: '/emulators',
    title: '\u6a21\u62df\u5668\u7ba1\u7406',
    menu_label: '\u6a21\u62df\u5668\u7ba1\u7406',
    icon: 'emulator',
    component: 'Emulators',
    renderer: 'component',
    url: null,
    section: 'main',
    order: 40,
    visible: true,
    dev_only: false,
    source: 'host:core',
  },
  {
    id: 'plugins',
    path: '/plugins',
    title: '\u63d2\u4ef6\u7ba1\u7406',
    menu_label: '\u63d2\u4ef6\u7ba1\u7406',
    icon: 'plugin',
    component: 'Plugin',
    renderer: 'component',
    url: null,
    section: 'main',
    order: 50,
    visible: true,
    dev_only: false,
    source: 'host:core',
  },
  {
    id: 'plugins-market',
    path: '/plugins-market',
    title: '\u63d2\u4ef6\u5e02\u573a',
    menu_label: '\u63d2\u4ef6\u5e02\u573a',
    icon: 'market',
    component: 'PluginMarket',
    renderer: 'component',
    url: null,
    section: 'main',
    order: 60,
    visible: true,
    dev_only: false,
    source: 'host:core',
  },
  {
    id: 'queue',
    path: '/queue',
    title: '\u8c03\u5ea6\u961f\u5217',
    menu_label: '\u8c03\u5ea6\u961f\u5217',
    icon: 'queue',
    component: 'Queue',
    renderer: 'component',
    url: null,
    section: 'main',
    order: 70,
    visible: true,
    dev_only: false,
    source: 'host:core',
  },
  {
    id: 'scheduler',
    path: '/scheduler',
    title: '\u8c03\u5ea6\u4e2d\u5fc3',
    menu_label: '\u8c03\u5ea6\u4e2d\u5fc3',
    icon: 'scheduler',
    component: 'Scheduler',
    renderer: 'component',
    url: null,
    section: 'main',
    order: 80,
    visible: true,
    dev_only: false,
    source: 'host:core',
  },
  {
    id: 'history',
    path: '/history',
    title: '\u5386\u53f2\u8bb0\u5f55',
    menu_label: '\u5386\u53f2\u8bb0\u5f55',
    icon: 'history',
    component: 'History',
    renderer: 'component',
    url: null,
    section: 'bottom',
    order: 10,
    visible: true,
    dev_only: false,
    source: 'host:core',
  },
  {
    id: 'tools',
    path: '/tools',
    title: '\u5de5\u5177',
    menu_label: '\u5de5\u5177',
    icon: 'tool',
    component: 'Tools',
    renderer: 'component',
    url: null,
    section: 'bottom',
    order: 20,
    visible: true,
    dev_only: false,
    source: 'host:core',
  },
  {
    id: 'settings',
    path: '/settings',
    title: '\u8bbe\u7f6e',
    menu_label: '\u8bbe\u7f6e',
    icon: 'settings',
    component: 'Settings',
    renderer: 'component',
    url: null,
    section: 'bottom',
    order: 30,
    visible: true,
    dev_only: false,
    source: 'host:core',
  },
  {
    id: 'test-router',
    path: '/TestRouter',
    title: '\u6d4b\u8bd5\u8def\u7531',
    menu_label: '\u6d4b\u8bd5\u8def\u7531',
    icon: 'dev',
    component: 'TestRouter',
    renderer: 'component',
    url: null,
    section: 'dev',
    order: 10,
    visible: true,
    dev_only: true,
    source: 'host:core',
  },
  {
    id: 'ocr-dev',
    path: '/OCRdev',
    title: 'OCR \u6d4b\u8bd5',
    menu_label: 'OCR\u6d4b\u8bd5',
    icon: 'dev',
    component: 'OCRdev',
    renderer: 'component',
    url: null,
    section: 'dev',
    order: 20,
    visible: true,
    dev_only: true,
    source: 'host:core',
  },
  {
    id: 'ws-dev',
    path: '/WSdev',
    title: 'WebSocket \u6d4b\u8bd5',
    menu_label: 'WebSocket\u6d4b\u8bd5',
    icon: 'api',
    component: 'WSdev',
    renderer: 'component',
    url: null,
    section: 'dev',
    order: 30,
    visible: true,
    dev_only: true,
    source: 'host:core',
  },
  {
    id: 'overlay-mask-dev',
    path: '/OverlayMaskDev',
    title: '\u906e\u7f69\u6d4b\u8bd5',
    menu_label: '\u906e\u7f69\u6d4b\u8bd5',
    icon: 'dev',
    component: 'OverlayMaskDev',
    renderer: 'component',
    url: null,
    section: 'dev',
    order: 40,
    visible: true,
    dev_only: true,
    source: 'host:core',
  },
]

export function normalizePageDeclarations(raw: unknown): PageDeclaration[] {
  if (!Array.isArray(raw)) return FALLBACK_PAGE_DECLARATIONS
  const result = raw
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    .map(item => ({
      id: String(item.id || '').trim(),
      path: normalizePath(String(item.path || '')),
      title: String(item.title || '').trim(),
      menu_label: String(item.menu_label || item.title || '').trim(),
      icon: String(item.icon || 'app').trim(),
      component: String(item.component || 'PluginPage').trim(),
      renderer: String(item.renderer || 'component').trim(),
      url: normalizeOptionalUrl(item.url),
      section: String(item.section || 'main').trim(),
      order: Number.isFinite(Number(item.order)) ? Number(item.order) : 1000,
      visible: item.visible !== false,
      dev_only: item.dev_only === true,
      source: String(item.source || '').trim(),
    }))
    .filter(item => item.id && item.path && item.title && item.menu_label && canRenderPage(item))
  return result.length > 0 ? sortPageDeclarations(result) : FALLBACK_PAGE_DECLARATIONS
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
  return pages.map(createPageRoute).filter((item): item is RouteRecordRaw => item !== null)
}

export function syncDeclaredPageRoutes(router: Router, pages: PageDeclaration[]): void {
  const routes = createPageRoutes(pages)
  const nextRouteNames = new Set(routes.map(route => String(route.name)))
  for (const existingRoute of router.getRoutes()) {
    const existingName = existingRoute.name ? String(existingRoute.name) : ''
    if (existingName.startsWith('page:') && !nextRouteNames.has(existingName)) {
      router.removeRoute(existingName)
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
      const existingName = existsByPath.name ? String(existsByPath.name) : ''
      if (existingName.startsWith('page:')) {
        router.removeRoute(existingName)
      } else {
        continue
      }
    }
    router.addRoute(route)
  }
}

function createPageRoute(page: PageDeclaration): RouteRecordRaw | null {
  const component = PAGE_COMPONENTS[page.component]
  const routeComponent = shouldUsePluginPageHost(page) ? PluginPageHostView : component
  if (!routeComponent) return null
  return {
    path: page.path,
    name: BUILTIN_ROUTE_NAMES[page.id] || `page:${page.id}`,
    component: routeComponent,
    props: shouldUsePluginPageHost(page) ? { page } : undefined,
    meta: {
      title: page.title,
      keepAlive: page.component === 'Scheduler',
      declaredPage: true,
      pageId: page.id,
      page,
    },
  }
}

function canRenderPage(page: PageDeclaration): boolean {
  if (PAGE_COMPONENTS[page.component]) return true
  return shouldUsePluginPageHost(page)
}

function shouldUsePluginPageHost(page: PageDeclaration): boolean {
  return page.renderer === 'iframe' || !PAGE_COMPONENTS[page.component]
}

function normalizeOptionalUrl(raw: unknown): string | null {
  if (raw === null || raw === undefined) return null
  const text = String(raw || '').trim()
  return text || null
}

function normalizePath(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) return ''
  return `/${trimmed.replace(/^\/+/, '')}`.replace(/\/+/g, '/').replace(/\/$/, '') || '/'
}

function sectionRank(section: string): number {
  if (section === 'main') return 0
  if (section === 'bottom') return 1
  if (section === 'dev') return 2
  return 3
}
