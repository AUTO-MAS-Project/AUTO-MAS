/**
 * B1 发布阻断回归：官方插件声明的 editor_kind 必须解析到专属编辑页，
 * 且解析出的路由段必须与 router 真实注册的路由一致（防止映射表与路由表再次脱节）。
 *
 * 官方插件真实声明（已从 plugins/wheels 内各 plugin.py 核对）：
 * - automas_script_maa               type_key=MAA      editor_kind=plugin:script_maa
 * - automas_plugin_maaend_adapter    type_key=MaaEnd   editor_kind=plugin:maaend_adapter
 * - automas_plugin_ok_script_adapter type_key=OkScript editor_kind=plugin:ok_script_adapter
 *
 * 宿主 fallback（app/core/script_types.py LEGACY_SCRIPT_TYPE_METADATA）在插件缺席时
 * 仍会产出 builtin:src / builtin:maaend / builtin:m9a，前端同样要接住。
 */
import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest'
import type { RouteRecordRaw } from 'vue-router'
import { getScriptEditPath, getUserCreatePath, getUserEditPath } from './scriptRegistry'

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

let routePaths: Set<string>

beforeAll(async () => {
  vi.stubGlobal('window', {
    electronAPI: { getLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn() }) },
  })
  await import('@/router')
  routePaths = new Set(routerCapture.routes.map(route => route.path))
})

afterAll(() => {
  vi.unstubAllGlobals()
})

const OFFICIAL_PLUGIN_CASES = [
  { type: 'MAA', editorKind: 'plugin:script_maa', segment: 'maa' },
  { type: 'MaaEnd', editorKind: 'plugin:maaend_adapter', segment: 'maaend' },
  { type: 'OkScript', editorKind: 'plugin:ok_script_adapter', segment: 'ok-script' },
] as const

describe('scriptRegistry 编辑页路由解析 (B1)', () => {
  it.each(OFFICIAL_PLUGIN_CASES)(
    '$type 插件声明 $editorKind 解析到专属编辑页且路由已注册',
    ({ type, editorKind, segment }) => {
      const script = { id: 's1', type, editorKind }

      expect(getScriptEditPath(script)).toBe(`/scripts/s1/edit/${segment}`)
      expect(routePaths.has(`/scripts/:id/edit/${segment}`)).toBe(true)

      expect(getUserCreatePath(script)).toBe(`/scripts/s1/users/add/${segment}`)
      expect(routePaths.has(`/scripts/:scriptId/users/add/${segment}`)).toBe(true)

      expect(getUserEditPath(script, { id: 'u1' })).toBe(`/scripts/s1/users/u1/edit/${segment}`)
      expect(routePaths.has(`/scripts/:scriptId/users/:userId/edit/${segment}`)).toBe(true)
    }
  )

  it.each(OFFICIAL_PLUGIN_CASES)(
    '$type 类型级兜底：editor_kind 未命中映射时仍落到专属编辑页',
    ({ type, segment }) => {
      expect(getScriptEditPath({ id: 's1', type, editorKind: 'plugin:unknown-future' })).toBe(
        `/scripts/s1/edit/${segment}`
      )
      expect(getScriptEditPath({ id: 's1', type, editorKind: undefined })).toBe(
        `/scripts/s1/edit/${segment}`
      )
    }
  )

  it('接住宿主 fallback 仍会产出的 builtin:* editor_kind', () => {
    // app/core/script_types.py：MaaEnd fallback 写的是 builtin:maaend（与插件声明不一致）
    expect(getScriptEditPath({ id: 's1', type: 'MaaEnd', editorKind: 'builtin:maaend' })).toBe(
      '/scripts/s1/edit/maaend'
    )
    expect(getScriptEditPath({ id: 's1', type: 'SRC', editorKind: 'builtin:src' })).toBe(
      '/scripts/s1/edit/src'
    )
    expect(routePaths.has('/scripts/:id/edit/src')).toBe(true)
    // builtin:m9a → /edit/m9a 为注册的 redirect 路由（→ /edit/maafw）
    expect(getScriptEditPath({ id: 's1', type: 'M9A', editorKind: 'builtin:m9a' })).toBe(
      '/scripts/s1/edit/m9a'
    )
    expect(routePaths.has('/scripts/:id/edit/m9a')).toBe(true)
    expect(routePaths.has('/scripts/:id/edit/maafw')).toBe(true)
  })

  it('MaaFWManaged（editor_kind=schema）仍落通用 Schema 编辑页', () => {
    const script = { id: 's1', type: 'MaaFWManaged', editorKind: 'schema' }

    expect(getScriptEditPath(script)).toBe('/scripts/s1/edit/schema')
    expect(routePaths.has('/scripts/:id/edit/schema')).toBe(true)
    expect(getUserCreatePath(script)).toBe('/scripts/s1/users/add/schema')
    expect(getUserEditPath(script, { id: 'u1' })).toBe('/scripts/s1/users/u1/edit/schema')
  })

  it('未知 plugin:* 且类型无兜底时回落通用插件编辑页', () => {
    const script = { id: 's1', type: 'ThirdPartyScript', editorKind: 'plugin:third_party' }

    expect(getScriptEditPath(script)).toBe('/scripts/s1/edit/plugin')
    expect(routePaths.has('/scripts/:id/edit/plugin')).toBe(true)
    expect(getUserCreatePath(script)).toBe('/scripts/s1/users/add/plugin')
    expect(routePaths.has('/scripts/:scriptId/users/add/plugin')).toBe(true)
    expect(getUserEditPath(script, { id: 'u1' })).toBe('/scripts/s1/users/u1/edit/plugin')
    expect(routePaths.has('/scripts/:scriptId/users/:userId/edit/plugin')).toBe(true)
  })

  it('editor_kind 缺失且类型未知时回落通用 Schema 编辑页', () => {
    expect(getScriptEditPath({ id: 's1', type: 'General', editorKind: undefined })).toBe(
      '/scripts/s1/edit/schema'
    )
  })

  it('HSR 插件声明与 Okww 类型兜底解析到各自专属编辑页', () => {
    expect(
      getScriptEditPath({ id: 's1', type: 'HSR', editorKind: 'plugin:automas_script_hsr' })
    ).toBe('/scripts/s1/edit/hsr')
    expect(routePaths.has('/scripts/:id/edit/hsr')).toBe(true)
    expect(getScriptEditPath({ id: 's1', type: 'Okww', editorKind: 'plugin:okww_adapter' })).toBe(
      '/scripts/s1/edit/okww'
    )
    expect(routePaths.has('/scripts/:id/edit/okww')).toBe(true)
  })
})
