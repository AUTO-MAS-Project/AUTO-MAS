import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { MAAFW_FLAVORS } from '@/composables/useMaaFWFlavor'
import { buildMaaFWRoutes, resolveMaaFWCanonicalLocation } from './maafwFlavorRoutes'
import {
  buildScriptEditorRoutes,
  MAA_CULTIVATE_ROUTE,
  scriptEditorLocation,
} from './scriptEditorRoutes'

const makeRouter = () =>
  createRouter({
    history: createMemoryHistory(),
    routes: [
      ...buildScriptEditorRoutes(),
      ...Object.values(buildMaaFWRoutes(MAAFW_FLAVORS, {})).flat(),
      MAA_CULTIVATE_ROUTE,
    ],
  })

// 既有链接与标题是公开入口契约，预期不从新登记表生成。
const legacyEditors = [
  ['MAA', 'maa', 'MAA'],
  ['SRC', 'src', 'SRC'],
  ['MaaEnd', 'maaend', 'MaaEnd'],
  ['HSR', 'hsr', 'HSR'],
  ['General', 'general', '通用'],
  ['BAAH', 'baah', 'BAAH'],
  ['Okww', 'okww', 'ok-ww'],
  ['OkNte', 'oknte', 'ok-nte'],
  ['BetterGI', 'bettergi', 'BetterGI'],
  ['ZzzOd', 'zzzod', 'ZZZ-OD'],
  ['Whimbox', 'whimbox', '奇想盒'],
] as const

describe('script editor navigation contract', () => {
  it('resolves all ordinary edit and add links to their original names, parameters and titles', () => {
    const router = makeRouter()
    for (const [type, suffix, title] of legacyEditors) {
      for (const [kind, url, params, name, pageTitle] of [
        [
          'script',
          `/scripts/script-1/edit/${suffix}`,
          { id: 'script-1' },
          `${type}ScriptEdit`,
          `编辑${title}脚本`,
        ],
        [
          'userAdd',
          `/scripts/script-1/users/add/${suffix}`,
          { scriptId: 'script-1' },
          `${type}UserAdd`,
          `添加${title}用户`,
        ],
        [
          'userEdit',
          `/scripts/script-1/users/user-1/edit/${suffix}`,
          { scriptId: 'script-1', userId: 'user-1' },
          `${type}UserEdit`,
          `编辑${title}用户`,
        ],
      ] as const) {
        const linked = router.resolve(url)
        expect(linked.name).toBe(name)
        expect(linked.params).toEqual(params)
        expect(linked.meta.title).toBe(pageTitle)
        expect(router.resolve(scriptEditorLocation(type, kind, params)).fullPath).toBe(url)
      }
    }
  })

  it('keeps MFW setup, family navigation and canonical query/hash', () => {
    const router = makeRouter()
    for (const [type, suffix] of [
      ['MaaFW', 'maafw'],
      ['M9A', 'm9a'],
      ['MSS', 'mss'],
    ] as const) {
      expect(router.resolve(`/scripts/script-1/setup/${suffix}`).name).toBe(`${type}SetupWizard`)
      expect(router.resolve(scriptEditorLocation(type, 'script', { id: 'script-1' })).path).toBe(
        `/scripts/script-1/edit/${suffix}`
      )
      expect(
        router.resolve(scriptEditorLocation(type, 'userAdd', { scriptId: 'script-1' })).path
      ).toBe(`/scripts/script-1/users/add/${suffix}`)
      expect(
        router.resolve(
          scriptEditorLocation(type, 'userEdit', { scriptId: 'script-1', userId: 'user-1' })
        ).path
      ).toBe(`/scripts/script-1/users/user-1/edit/${suffix}`)
    }
    const oldLink = router.resolve('/scripts/script-1/users/user-1/edit/maafw?tab=task#queue')
    const canonical = resolveMaaFWCanonicalLocation(oldLink, 'M9A')
    expect(canonical).not.toBeNull()
    expect(router.resolve(canonical!).fullPath).toBe(
      '/scripts/script-1/users/user-1/edit/m9a?tab=task#queue'
    )
    expect(resolveMaaFWCanonicalLocation(oldLink, 'MaaFW')).toBeNull()
  })

  it('retains the MAA cultivation entry and unique route identities', () => {
    const router = makeRouter()
    const route = router.resolve('/scripts/script-1/users/user-1/cultivate/maa')
    expect(route.name).toBe('MAACultivate')
    expect(route.matched[0]?.props.default).toEqual({ cultivationPage: true })
    const routes = router.getRoutes()
    expect(routes).toHaveLength(46)
    expect(new Set(routes.map(item => item.path)).size).toBe(46)
    expect(new Set(routes.map(item => item.name)).size).toBe(46)
  })
})
