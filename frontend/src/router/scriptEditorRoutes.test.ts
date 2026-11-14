import { MAAFW_FLAVORS } from '@/composables/useMaaFWFlavor'
import { SCRIPT_PLUGIN_ROUTES } from '@/plugins/scriptAdapters'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { buildMaaFWRoutes, resolveMaaFWCanonicalLocation } from './maafwFlavorRoutes'
import { buildScriptEditorRoutes, scriptEditorLocation } from './scriptEditorRoutes'

const makeRouter = () =>
  createRouter({
    history: createMemoryHistory(),
    routes: [
      ...buildScriptEditorRoutes(),
      ...SCRIPT_PLUGIN_ROUTES,
      ...Object.values(buildMaaFWRoutes(MAAFW_FLAVORS, {})).flat(),
    ],
  })

// 既有链接是公开入口契约，预期不从新登记表生成。
const legacyEditors = [
  ['MAA', 'maa'],
  ['SRC', 'src'],
  ['MaaEnd', 'maaend'],
  ['HSR', 'hsr'],
  ['General', 'general'],
  ['BAAH', 'baah'],
  ['Okww', 'okww'],
  ['OkNte', 'oknte'],
  ['BetterGI', 'bettergi'],
  ['ZzzOd', 'zzzod'],
  ['Whimbox', 'whimbox'],
] as const

describe('script editor navigation contract', () => {
  it('resolves ordinary edit and add links to their original names and parameters', () => {
    const router = makeRouter()
    for (const [type, suffix] of legacyEditors) {
      for (const [kind, url, params, name] of [
        ['script', `/scripts/script-1/edit/${suffix}`, { id: 'script-1' }, `${type}ScriptEdit`],
        [
          'userAdd',
          `/scripts/script-1/users/add/${suffix}`,
          { scriptId: 'script-1' },
          `${type}UserAdd`,
        ],
        [
          'userEdit',
          `/scripts/script-1/users/user-1/edit/${suffix}`,
          { scriptId: 'script-1', userId: 'user-1' },
          `${type}UserEdit`,
        ],
      ] as const) {
        const linked = router.resolve(url)
        expect(linked.name).toBe(name)
        expect(linked.params).toEqual(params)
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

  it('retains the MAA cultivation entry', () => {
    const router = makeRouter()
    const route = router.resolve('/scripts/script-1/users/user-1/cultivate/maa')
    expect(route.name).toBe('MAACultivate')
    expect(route.matched[0]?.props.default).toEqual({ cultivationPage: true })
  })
})
