import { describe, expect, it } from 'vitest'

import {
  FALLBACK_PAGE_DECLARATIONS,
  normalizePageDeclarations,
  sortPageDeclarations,
  dedupePageDeclarations,
  createPageRoutes,
  syncDeclaredPageRoutes,
  type PageDeclaration,
} from './pageDeclarations'

describe('pageDeclarations', () => {
  describe('FALLBACK_PAGE_DECLARATIONS', () => {
    it('包含 15 项且每项具有必填字段（id/path/title/menu_label/component/renderer/section）', () => {
      expect(FALLBACK_PAGE_DECLARATIONS).toHaveLength(15)
      for (const page of FALLBACK_PAGE_DECLARATIONS) {
        expect(page.id).toBeTruthy()
        expect(page.path).toMatch(/^\//)
        expect(page.title).toBeTruthy()
        expect(page.menu_label).toBeTruthy()
        expect(page.component).toBeTruthy()
        expect(page.renderer).toBe('component')
        expect(['main', 'bottom', 'dev']).toContain(page.section)
        expect(typeof page.order).toBe('number')
        expect(typeof page.visible).toBe('boolean')
        expect(typeof page.dev_only).toBe('boolean')
        expect(page.source).toBe('host:core')
      }
    })

    it('内置页面 id 覆盖 home/scripts/plans/game-center/plugins/settings 等', () => {
      const ids = FALLBACK_PAGE_DECLARATIONS.map(p => p.id)
      expect(ids).toContain('home')
      expect(ids).toContain('scripts')
      expect(ids).toContain('plans')
      expect(ids).toContain('game-center')
      expect(ids).not.toContain('emulators')
      expect(ids).toContain('plugins')
      expect(ids).toContain('plugins-market')
      expect(ids).toContain('queue')
      expect(ids).toContain('scheduler')
      expect(ids).toContain('history')
      expect(ids).toContain('tools')
      expect(ids).toContain('settings')
    })

    it('把旧模拟器页面声明归一化到唯一的游戏与模拟器入口', () => {
      const [page] = normalizePageDeclarations([
        {
          id: 'emulators',
          path: '/emulators',
          title: '模拟器管理',
          component: 'Emulators',
          renderer: 'component',
        },
      ])

      expect(page).toMatchObject({
        id: 'game-center',
        path: '/game-center',
        title: '游戏与模拟器',
        component: 'GameCenter',
      })
    })

    it('dev_only 页面仅出现在 dev section', () => {
      for (const page of FALLBACK_PAGE_DECLARATIONS) {
        if (page.dev_only) {
          expect(page.section).toBe('dev')
        }
      }
    })
  })

  describe('normalizePageDeclarations', () => {
    it('对非数组输入返回 FALLBACK_PAGE_DECLARATIONS', () => {
      expect(normalizePageDeclarations(null)).toBe(FALLBACK_PAGE_DECLARATIONS)
      expect(normalizePageDeclarations(undefined)).toBe(FALLBACK_PAGE_DECLARATIONS)
      expect(normalizePageDeclarations('not an array')).toBe(FALLBACK_PAGE_DECLARATIONS)
      expect(normalizePageDeclarations({})).toBe(FALLBACK_PAGE_DECLARATIONS)
    })

    it('对空数组或全部无效项返回 FALLBACK_PAGE_DECLARATIONS', () => {
      expect(normalizePageDeclarations([])).toBe(FALLBACK_PAGE_DECLARATIONS)
      // 缺少 id 的项被过滤
      expect(normalizePageDeclarations([{ path: '/x', title: 'X' }])).toBe(
        FALLBACK_PAGE_DECLARATIONS
      )
    })

    it('正确规范化原始数据：路径前缀斜杠、类型转换、默认值填充', () => {
      const raw = [
        {
          id: 'plugin1',
          path: 'plugin/foo',
          title: '插件1',
          renderer: 'iframe',
          url: '/plugin/foo',
          frontend_plugin: 'demo',
          element_tag: null,
          entry_asset_url: null,
          style_asset_urls: [' /a.css ', '', 'b.css'],
          manifest_version: '2',
          section: 'main',
          order: '50',
          visible: false,
          dev_only: true,
          source: 'manifest',
        },
      ]
      const result = normalizePageDeclarations(raw)
      expect(result).toHaveLength(1)
      const page = result[0]
      // 路径规范化：补前缀 /
      expect(page.path).toBe('/plugin/foo')
      // manifest_version 字符串 → 数字
      expect(page.manifest_version).toBe(2)
      // order 字符串 → 数字
      expect(page.order).toBe(50)
      // visible: false 保留
      expect(page.visible).toBe(false)
      // dev_only: true 保留
      expect(page.dev_only).toBe(true)
      // style_asset_urls 去空白、过滤空值
      expect(page.style_asset_urls).toEqual(['/a.css', 'b.css'])
      // menu_label 默认取 title
      expect(page.menu_label).toBe('插件1')
      // icon 默认 'app'
      expect(page.icon).toBe('app')
      // component 默认 'PluginPage'
      expect(page.component).toBe('PluginPage')
    })

    it('过滤缺少 id/path/title/menu_label 的项', () => {
      const raw = [
        { id: 'valid', path: '/valid', title: 'Valid', renderer: 'iframe' },
        { id: '', path: '/no-id', title: 'No ID' },
        { id: 'no-path', path: '', title: 'No Path' },
        { id: 'no-title', path: '/no-title', title: '' },
      ]
      const result = normalizePageDeclarations(raw)
      expect(result).toHaveLength(1)
      expect(result[0].id).toBe('valid')
    })

    it('未知 component 且非 iframe/custom-element 的项被过滤', () => {
      const raw = [
        { id: 'p1', path: '/p1', title: 'P1', renderer: 'component', component: 'UnknownComp' },
        { id: 'p2', path: '/p2', title: 'P2', renderer: 'iframe', component: 'PluginPage' },
        {
          id: 'p3',
          path: '/p3',
          title: 'P3',
          renderer: 'custom-element',
          component: 'PluginElement',
        },
      ]
      const result = normalizePageDeclarations(raw)
      const ids = result.map(p => p.id)
      expect(ids).not.toContain('p1')
      expect(ids).toContain('p2')
      expect(ids).toContain('p3')
    })
  })

  describe('sortPageDeclarations', () => {
    it('按 section rank → order → menu_label 排序', () => {
      const pages: PageDeclaration[] = [
        {
          id: 'b1',
          path: '/b1',
          title: 'B1',
          menu_label: 'B',
          icon: 'app',
          component: 'Home',
          renderer: 'component',
          url: null,
          frontend_plugin: null,
          element_tag: null,
          entry_asset_url: null,
          style_asset_urls: [],
          manifest_version: null,
          dev_frontend_command: null,
          dev_frontend_error: null,
          section: 'bottom',
          order: 10,
          visible: true,
          dev_only: false,
          source: 'test',
        },
        {
          id: 'a2',
          path: '/a2',
          title: 'A2',
          menu_label: 'A',
          icon: 'app',
          component: 'Home',
          renderer: 'component',
          url: null,
          frontend_plugin: null,
          element_tag: null,
          entry_asset_url: null,
          style_asset_urls: [],
          manifest_version: null,
          dev_frontend_command: null,
          dev_frontend_error: null,
          section: 'main',
          order: 20,
          visible: true,
          dev_only: false,
          source: 'test',
        },
        {
          id: 'a1',
          path: '/a1',
          title: 'A1',
          menu_label: 'A',
          icon: 'app',
          component: 'Home',
          renderer: 'component',
          url: null,
          frontend_plugin: null,
          element_tag: null,
          entry_asset_url: null,
          style_asset_urls: [],
          manifest_version: null,
          dev_frontend_command: null,
          dev_frontend_error: null,
          section: 'main',
          order: 10,
          visible: true,
          dev_only: false,
          source: 'test',
        },
        {
          id: 'a1b',
          path: '/a1b',
          title: 'A1B',
          menu_label: 'A',
          icon: 'app',
          component: 'Home',
          renderer: 'component',
          url: null,
          frontend_plugin: null,
          element_tag: null,
          entry_asset_url: null,
          style_asset_urls: [],
          manifest_version: null,
          dev_frontend_command: null,
          dev_frontend_error: null,
          section: 'main',
          order: 10,
          visible: true,
          dev_only: false,
          source: 'test',
        },
      ]
      const sorted = sortPageDeclarations(pages)
      // main (rank 0) 在 bottom (rank 1) 之前
      expect(sorted[0].section).toBe('main')
      expect(sorted[sorted.length - 1].section).toBe('bottom')
      // main section 内按 order 升序
      const mainPages = sorted.filter(p => p.section === 'main')
      expect(mainPages[0].order).toBe(10)
      expect(mainPages[mainPages.length - 1].order).toBe(20)
      // 同 section 同 order 按 menu_label localeCompare
      const sameOrder = mainPages.filter(p => p.order === 10)
      expect(sameOrder.length).toBeGreaterThanOrEqual(2)
      expect(sameOrder[0].menu_label.localeCompare(sameOrder[1].menu_label)).toBeLessThanOrEqual(0)
    })
  })

  describe('createPageRoutes', () => {
    it('为 iframe 和 custom-element 渲染器生成路由并设置 props={page}', () => {
      const pages: PageDeclaration[] = [
        {
          id: 'iframe1',
          path: '/iframe1',
          title: 'Iframe1',
          menu_label: 'I1',
          icon: 'app',
          component: 'PluginPage',
          renderer: 'iframe',
          url: '/iframe',
          frontend_plugin: 'demo',
          element_tag: null,
          entry_asset_url: null,
          style_asset_urls: [],
          manifest_version: null,
          dev_frontend_command: null,
          dev_frontend_error: null,
          section: 'main',
          order: 10,
          visible: true,
          dev_only: false,
          source: 'test',
        },
        {
          id: 'element1',
          path: '/element1',
          title: 'Element1',
          menu_label: 'E1',
          icon: 'app',
          component: 'PluginElement',
          renderer: 'custom-element',
          url: null,
          frontend_plugin: 'demo',
          element_tag: 'demo-tag',
          entry_asset_url: '/demo.js',
          style_asset_urls: [],
          manifest_version: 1,
          dev_frontend_command: null,
          dev_frontend_error: null,
          section: 'main',
          order: 20,
          visible: true,
          dev_only: false,
          source: 'test',
        },
      ]
      const routes = createPageRoutes(pages)
      expect(routes).toHaveLength(2)
      const iframeRoute = routes.find(r => r.path === '/iframe1')
      expect(iframeRoute).toBeDefined()
      expect(iframeRoute!.name).toBe('page:iframe1')
      expect(iframeRoute!.props).toEqual({ page: pages[0] })
      expect(iframeRoute!.meta).toMatchObject({
        title: 'Iframe1',
        pageId: 'iframe1',
        declaredPage: true,
      })

      const elementRoute = routes.find(r => r.path === '/element1')
      expect(elementRoute).toBeDefined()
      expect(elementRoute!.name).toBe('page:element1')
      expect(elementRoute!.props).toEqual({ page: pages[1] })
    })

    it('为内置页面 id 使用 BUILTIN_ROUTE_NAMES 映射路由名', () => {
      const pages: PageDeclaration[] = [
        {
          id: 'home',
          path: '/home',
          title: '主页',
          menu_label: '主页',
          icon: 'home',
          component: 'Home',
          renderer: 'component',
          url: null,
          frontend_plugin: null,
          element_tag: null,
          entry_asset_url: null,
          style_asset_urls: [],
          manifest_version: null,
          dev_frontend_command: null,
          dev_frontend_error: null,
          section: 'main',
          order: 10,
          visible: true,
          dev_only: false,
          source: 'test',
        },
      ]
      const routes = createPageRoutes(pages)
      expect(routes).toHaveLength(1)
      // BUILTIN_ROUTE_NAMES['home'] = 'Home'
      expect(routes[0].name).toBe('Home')
      // 非 iframe/custom-element 不设置 props
      expect(routes[0].props).toBeUndefined()
    })

    it('跳过无法渲染的页面（未知 component 且非 iframe/custom-element）', () => {
      const pages: PageDeclaration[] = [
        {
          id: 'unknown',
          path: '/unknown',
          title: 'Unknown',
          menu_label: 'U',
          icon: 'app',
          component: 'NonExistent',
          renderer: 'component',
          url: null,
          frontend_plugin: null,
          element_tag: null,
          entry_asset_url: null,
          style_asset_urls: [],
          manifest_version: null,
          dev_frontend_command: null,
          dev_frontend_error: null,
          section: 'main',
          order: 10,
          visible: true,
          dev_only: false,
          source: 'test',
        },
        {
          id: 'known',
          path: '/known',
          title: 'Known',
          menu_label: 'K',
          icon: 'app',
          component: 'Home',
          renderer: 'component',
          url: null,
          frontend_plugin: null,
          element_tag: null,
          entry_asset_url: null,
          style_asset_urls: [],
          manifest_version: null,
          dev_frontend_command: null,
          dev_frontend_error: null,
          section: 'main',
          order: 20,
          visible: true,
          dev_only: false,
          source: 'test',
        },
      ]
      const routes = createPageRoutes(pages)
      expect(routes).toHaveLength(1)
      expect(routes[0].path).toBe('/known')
    })

    it('生产策略排除 dev_only 页面，开发策略允许注册', () => {
      const devPage = FALLBACK_PAGE_DECLARATIONS.find(page => page.dev_only)!

      expect(createPageRoutes([devPage], { includeDevOnly: false })).toEqual([])
      expect(createPageRoutes([devPage], { includeDevOnly: true })).toHaveLength(1)
    })

    it('同名或同路径声明冲突时保留第一项', () => {
      const first = {
        ...FALLBACK_PAGE_DECLARATIONS[0],
        id: 'plugin-one',
        path: '/plugin-shared',
      }
      const duplicateName = {
        ...first,
        path: '/plugin-other',
      }
      const duplicatePath = {
        ...first,
        id: 'plugin-two',
      }

      const routes = createPageRoutes([first, duplicateName, duplicatePath])

      expect(routes).toHaveLength(1)
      expect(routes[0].name).toBe('page:plugin-one')
      expect(routes[0].path).toBe('/plugin-shared')
    })

    it('菜单消费者可复用同一首项优先规则，避免生成无对应路由的重复项', () => {
      const first = {
        ...FALLBACK_PAGE_DECLARATIONS[0],
        id: 'plugin-one',
        path: '/plugin-shared',
      }
      const duplicateId = {
        ...first,
        path: '/plugin-other',
      }
      const duplicatePath = {
        ...first,
        id: 'plugin-two',
      }

      expect(dedupePageDeclarations([first, duplicateId, duplicatePath])).toEqual([first])
    })
  })

  describe('syncDeclaredPageRoutes', () => {
    it('移除过期动态路由、更新同名动态路由，并保留宿主路径冲突路由', () => {
      const routes = new Map<string, { name: string; path: string }>([
        ['HostSettings', { name: 'HostSettings', path: '/settings' }],
        ['page:stale', { name: 'page:stale', path: '/stale' }],
        ['page:update', { name: 'page:update', path: '/old-path' }],
      ])
      const router = {
        getRoutes: () => [...routes.values()],
        hasRoute: (name: string) => routes.has(String(name)),
        removeRoute: (name: string) => {
          routes.delete(String(name))
        },
        addRoute: (route: { name?: unknown; path: string }) => {
          routes.set(String(route.name), { name: String(route.name), path: route.path })
        },
      }
      const pages = [
        {
          ...FALLBACK_PAGE_DECLARATIONS[0],
          id: 'update',
          path: '/new-path',
        },
        {
          ...FALLBACK_PAGE_DECLARATIONS[0],
          id: 'conflict',
          path: '/settings',
        },
      ]

      syncDeclaredPageRoutes(router as never, pages, { includeDevOnly: false })

      expect(routes.has('page:stale')).toBe(false)
      expect(routes.get('page:update')?.path).toBe('/new-path')
      expect(routes.has('page:conflict')).toBe(false)
      expect(routes.get('HostSettings')?.path).toBe('/settings')
    })
  })
})
