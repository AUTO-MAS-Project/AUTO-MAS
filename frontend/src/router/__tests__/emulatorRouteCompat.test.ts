/**
 * 旧 /emulators 路由兼容测试。
 *
 * Lane 10 要求：保留旧 `/emulators` 入口并重定向到 `/game-center?tab=emulators`，
 * 使旧书签/外部链接在迁移到游戏与模拟器中心后仍可用。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { RouteRecordRaw } from 'vue-router'

const routerCapture = vi.hoisted(() => ({ routes: [] as RouteRecordRaw[] }))

vi.mock('vue-router', () => ({
  createWebHashHistory: vi.fn(() => ({})),
  createRouter: vi.fn((options: { routes: RouteRecordRaw[] }) => {
    routerCapture.routes = options.routes
    return {
      beforeEach: vi.fn(),
      push: vi.fn(),
      replace: vi.fn(),
      back: vi.fn(),
      forward: vi.fn(),
    }
  }),
}))
vi.mock('@/composables/useAppInitialization', () => ({
  useAppInitialization: () => ({
    isInitialized: { value: true },
    isBootstrapping: { value: false },
    isAppReady: { value: true },
  }),
}))
vi.mock('@/utils/initializationDecision', () => ({
  getInitializationDecision: vi.fn(),
}))
vi.mock('@/utils/skippedInitializationStartup', () => ({
  startSkippedInitializationStartup: vi.fn(),
}))

describe('旧 /emulators 路由兼容 (FE-ROUTE-EMULATOR-*)', () => {
  let routes: RouteRecordRaw[]

  beforeEach(async () => {
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn() }) },
    })
    await import('../index')
    routes = routerCapture.routes
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('/emulators 路由存在且重定向到 /game-center?tab=emulators', () => {
    const emulatorRoute = routes.find(r => r.path === '/emulators')
    expect(emulatorRoute).toBeDefined()
    expect(typeof emulatorRoute!.redirect).toBe('function')
    const redirect = (
      emulatorRoute!.redirect as () => { path: string; query: Record<string, string> }
    )()
    expect(redirect.path).toBe('/game-center')
    expect(redirect.query).toEqual({ tab: 'emulators' })
  })

  it('/game-center 页面由 createPageRoutes 生成', () => {
    const gameCenterRoute = routes.find(r => r.path === '/game-center')
    expect(gameCenterRoute).toBeDefined()
    expect(gameCenterRoute!.name).toBe('GameCenter')
  })

  it('旧 /emulators 不会与 /game-center 产生路径冲突', () => {
    const paths = routes.map(r => r.path)
    const gameCenterCount = paths.filter(p => p === '/game-center').length
    const emulatorCount = paths.filter(p => p === '/emulators').length
    expect(gameCenterCount).toBe(1)
    expect(emulatorCount).toBe(1)
  })
})
