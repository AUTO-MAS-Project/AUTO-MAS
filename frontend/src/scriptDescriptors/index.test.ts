import { describe, expect, it, vi } from 'vite-plus/test'
import { computed, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ScriptCreateIn, ScriptIndexItem } from '@/api'
import type { ScriptType } from '@/types/script'
import {
  MAAFW_FLAVORS,
  resolveMaaFWFlavor,
  useMaaFWFlavor,
  usesMaaFWProjectIcon,
} from '@/composables/useMaaFWFlavor'
import { maafwRouteLocation, resolveMaaFWCanonicalLocation } from '@/router/maafwFlavorRoutes'
import {
  buildCreateRequest,
  buildCreateSteps,
  filterScriptTypeOptions,
  getScriptEditSegment,
  SCRIPT_TYPE_OPTIONS,
  splitScriptTypeOptions,
} from '@/views/scripts/components/scriptCreateFlow'
import { SCRIPT_LABELS, SCRIPT_LOGOS } from '@/utils/scriptLogos'
import { indexScriptDescriptors, orderScriptDescriptors } from './assembly'
import {
  findScriptDescriptorByConfigType,
  getScriptDescriptor,
  resolveScriptType,
  SCRIPT_DESCRIPTORS,
  SCRIPT_ROUTES,
  scriptRouteLocation,
} from './index'
import baseline from './baseline.fixture.json'

const loaded = vi.hoisted(() => ({ script: vi.fn(), user: vi.fn(), host: vi.fn() }))
vi.mock('@/views/EditView/Script/MAAScriptEdit.vue', () => {
  loaded.script()
  return { default: { render: () => null } }
})
vi.mock('@/views/EditView/User/MAAUserEdit.vue', () => {
  loaded.user()
  return { default: { render: () => null } }
})
vi.mock('@/views/EditView/MaaFWFlavor/MaaFWPageHost.vue', () => {
  loaded.host()
  return { default: { render: () => null } }
})

describe('script identity and entry contracts', () => {
  it('covers generated types and keeps the exact forward and reverse config mapping', () => {
    expect(SCRIPT_DESCRIPTORS.map(item => item.type).sort()).toEqual(
      Object.values(ScriptCreateIn.type).sort()
    )
    expect(SCRIPT_DESCRIPTORS.map(item => item.configType).sort()).toEqual(
      Object.values(ScriptIndexItem.type).sort()
    )
    const expected = {
      General: 'GeneralConfig',
      MAA: 'MaaConfig',
      SRC: 'SrcConfig',
      MaaEnd: 'MaaEndConfig',
      Okww: 'OkwwConfig',
      OkNte: 'OkNteConfig',
      HSR: 'HSRConfig',
      BetterGI: 'BetterGIConfig',
      ZzzOd: 'ZzzOdConfig',
      BAAH: 'BAAHConfig',
      Whimbox: 'WhimboxConfig',
      MaaFW: 'MaaFWConfig',
      M9A: 'M9AConfig',
      MSS: 'MSSConfig',
    }
    expect(
      Object.fromEntries(SCRIPT_DESCRIPTORS.map(item => [item.type, item.configType]))
    ).toEqual(expected)
    for (const descriptor of SCRIPT_DESCRIPTORS) {
      expect(resolveScriptType(descriptor.configType)).toBe(descriptor.type)
      expect(findScriptDescriptorByConfigType(descriptor.configType)).toBe(descriptor)
      expect(SCRIPT_LOGOS[descriptor.type]).toBe(descriptor.logo)
      expect(SCRIPT_LABELS[descriptor.type]).toBe(descriptor.label)
    }
    expect(SCRIPT_LABELS).toEqual({
      General: 'AUTO-MAS',
      MAA: 'MAA',
      SRC: 'SRC',
      MaaEnd: 'MaaEnd',
      Okww: 'ok-ww',
      OkNte: 'OK-NTE',
      HSR: 'HSR',
      BetterGI: 'BetterGI',
      ZzzOd: 'ZZZ-OD',
      BAAH: 'BAAH',
      Whimbox: 'Whimbox',
      MaaFW: 'MFW',
      M9A: 'M9A',
      MSS: 'MSS',
    })
  })

  it('rejects duplicate type, config type, route name and route path instead of overwriting', () => {
    const maa = getScriptDescriptor('MAA')
    const src = getScriptDescriptor('SRC')
    expect(() => indexScriptDescriptors([maa, maa])).toThrow('重复脚本类型')
    expect(() => indexScriptDescriptors([maa, { ...src, configType: maa.configType }])).toThrow(
      '重复脚本配置类型'
    )
    const replaceScript = (route: typeof src.routes.script) => ({
      ...src,
      routes: { ...src.routes, script: route },
    })
    expect(() =>
      indexScriptDescriptors([
        maa,
        replaceScript({ ...src.routes.script, name: maa.routes.script.name }),
      ])
    ).toThrow('重复脚本路由名称')
    expect(() =>
      indexScriptDescriptors([
        maa,
        replaceScript({ ...src.routes.script, path: maa.routes.script.path }),
      ])
    ).toThrow('重复脚本路由路径')
  })

  it('preserves every card, ordering, grouping, search alias and live translation', () => {
    expect(
      orderScriptDescriptors([...SCRIPT_DESCRIPTORS].reverse()).map(item => item.type)
    ).toEqual(SCRIPT_TYPE_OPTIONS.map(item => item.value))
    expect(SCRIPT_TYPE_OPTIONS.map(({ icon: _icon, ...card }) => card)).toEqual(baseline.cards)
    const groups = splitScriptTypeOptions(SCRIPT_TYPE_OPTIONS)
    expect(groups.general.map(item => item.value)).toEqual(['General', 'MaaFW'])
    expect(groups.specialized.map(item => item.value)).toEqual([
      'MAA',
      'SRC',
      'MaaEnd',
      'M9A',
      'Okww',
      'OkNte',
      'HSR',
      'BetterGI',
      'ZzzOd',
      'BAAH',
      'Whimbox',
      'MSS',
    ])
    for (const card of baseline.cards) {
      for (const alias of card.keywords) {
        expect(
          filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, ` ${alias.toUpperCase()} `).map(
            item => item.value
          )
        ).toContain(card.value)
      }
    }
    let translated = '译文甲'
    const translate = (key: string) => (key === 'core.scripts.type.MAA' ? translated : key)
    expect(
      filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, '译文甲', translate).map(item => item.value)
    ).toEqual(['MAA'])
    translated = '译文乙'
    expect(filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, '译文甲', translate)).toEqual([])
    expect(
      filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, '译文乙', translate).map(item => item.value)
    ).toEqual(['MAA'])
    expect(filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, 'no-such-script')).toEqual([])
  })

  it('keeps all baseline route records including metadata and cultivation props', () => {
    expect(
      Object.fromEntries(
        SCRIPT_ROUTES.map(route => [
          route.name,
          {
            path: route.path,
            title: route.meta?.title,
            props: route.props ?? false,
            ...(route.meta?.scriptType
              ? { scriptType: route.meta.scriptType, maafwPage: route.meta.maafwPage }
              : {}),
          },
        ])
      )
    ).toEqual(baseline.routes)
    for (const route of SCRIPT_ROUTES) {
      expect(route.redirect).toBeUndefined()
      expect(route.beforeEnter).toBeUndefined()
      expect(route.children).toBeUndefined()
      expect(route.alias).toBeUndefined()
    }
    const router = createRouter({ history: createMemoryHistory(), routes: SCRIPT_ROUTES })
    for (const descriptor of SCRIPT_DESCRIPTORS) {
      const params = {
        script: { id: 'script-one' },
        userAdd: { scriptId: 'script-one' },
        userEdit: { scriptId: 'script-one', userId: 'user-one' },
      }
      for (const kind of ['script', 'userAdd', 'userEdit'] as const) {
        const target = scriptRouteLocation(descriptor.type, kind, params[kind])
        const resolved = router.resolve(target)
        expect(resolved.name).toBe(descriptor.routes[kind].name)
        expect(resolved.params).toEqual(params[kind])
        expect(resolved.path.endsWith(`/${getScriptEditSegment(descriptor.type)}`)).toBe(true)
        expect(typeof target).toBe(descriptor.flavor ? 'object' : 'string')
      }
    }
    expect(
      router.resolve({ name: 'MAACultivate', params: { scriptId: 's', userId: 'u' } }).path
    ).toBe('/scripts/s/users/u/cultivate/maa')
  })

  it('retains flavor identity, setup and canonical correction without conflating fallbacks', () => {
    const router = createRouter({ history: createMemoryHistory(), routes: SCRIPT_ROUTES })
    for (const flavor of MAAFW_FLAVORS) {
      expect(getScriptDescriptor(flavor.type).flavor).toBe(flavor)
      expect(usesMaaFWProjectIcon(flavor)).toBe(flavor.type === 'MaaFW')
      expect(router.resolve(maafwRouteLocation(flavor.type, 'setup', { id: 's' })).path).toBe(
        `/scripts/s/setup/${flavor.routes.suffix}`
      )
    }
    expect(resolveScriptType('UnknownConfig')).toBe('General')
    expect(findScriptDescriptorByConfigType('UnknownConfig')).toBeUndefined()
    expect(resolveMaaFWFlavor('Unknown')).toBe(resolveMaaFWFlavor('MaaFW'))
    const route = router.resolve('/scripts/s/users/u/edit/maafw?tab=tasks&tag=a&tag=b#task')
    const canonical = resolveMaaFWCanonicalLocation(route, 'M9A')
    expect(canonical).toEqual({
      name: 'M9AUserEdit',
      params: { scriptId: 's', userId: 'u' },
      query: { tab: 'tasks', tag: ['a', 'b'] },
      hash: '#task',
    })
    expect(router.resolve(canonical!).fullPath).toBe(
      '/scripts/s/users/u/edit/m9a?tab=tasks&tag=a&tag=b#task'
    )
    expect(resolveMaaFWCanonicalLocation(route, 'General')).toBeNull()
    expect(resolveMaaFWCanonicalLocation(route, 'Unknown')).toBeNull()
    expect(resolveMaaFWCanonicalLocation(route, 'MaaFW')).toBeNull()
    const type = ref<ScriptType>('MaaFW')
    const flavor = useMaaFWFlavor(type)
    const location = computed(() => scriptRouteLocation(type.value, 'script', { id: 's' }))
    type.value = 'M9A'
    expect(flavor.value).toBe(getScriptDescriptor('M9A').flavor)
    expect(router.resolve(location.value).path).toBe('/scripts/s/edit/m9a')
  })

  it('retains entry selection for custom, template, new project and project reuse', () => {
    expect(buildCreateSteps({ type: 'General' }).map(item => item.key)).toEqual(['type', 'config'])
    expect(buildCreateSteps({ type: 'M9A' }).map(item => item.key)).toEqual(['type', 'config'])
    expect(buildCreateSteps({ type: 'MAA' }).map(item => item.key)).toEqual(['type'])
    expect(buildCreateRequest({ type: 'General', configMode: 'custom', template: null })).toEqual({
      kind: 'general-custom',
    })
    expect(
      buildCreateRequest({ type: 'General', configMode: 'template', template: null })
    ).toBeNull()
    const template = {
      projectKey: 'project',
      categoryKey: 'category',
      configKey: 'config',
      displayName: 'template',
    }
    expect(buildCreateRequest({ type: 'General', configMode: 'template', template })).toEqual({
      kind: 'general-template',
      template,
    })
    expect(buildCreateRequest({ type: 'MAA', configMode: 'custom', template: null })).toEqual({
      kind: 'new',
      type: 'MAA',
    })
    expect(
      buildCreateRequest({
        type: 'M9A',
        configMode: 'custom',
        template: null,
        mfwSourceMode: 'reuse',
        mfwSourceScriptId: 'source',
      })
    ).toEqual({ kind: 'mfw-reuse', type: 'M9A', sourceScriptId: 'source' })
    expect(
      buildCreateRequest({
        type: 'M9A',
        configMode: 'custom',
        template: null,
        mfwSourceMode: 'reuse',
      })
    ).toBeNull()
    expect(
      buildCreateRequest({
        type: 'MaaFW',
        configMode: 'custom',
        template: null,
        mfwSourceMode: 'new',
      })
    ).toEqual({ kind: 'new', type: 'MaaFW' })
  })

  it('does not load editors on lookup or resolve; navigation loads only its page and reuses it across params', async () => {
    expect(loaded.script).not.toHaveBeenCalled()
    expect(loaded.user).not.toHaveBeenCalled()
    expect(loaded.host).not.toHaveBeenCalled()
    const router = createRouter({ history: createMemoryHistory(), routes: SCRIPT_ROUTES })
    router.resolve(scriptRouteLocation('MAA', 'script', { id: 'first' }))
    expect(loaded.script).not.toHaveBeenCalled()
    await router.push(scriptRouteLocation('MAA', 'script', { id: 'first' }))
    expect(loaded.script).toHaveBeenCalledTimes(1)
    expect(loaded.user).not.toHaveBeenCalled()
    expect(loaded.host).not.toHaveBeenCalled()
    const component = router.currentRoute.value.matched[0].components?.default
    await router.push(scriptRouteLocation('MAA', 'script', { id: 'second' }))
    expect(router.currentRoute.value.params).toEqual({ id: 'second' })
    expect(router.currentRoute.value.matched[0].components?.default).toBe(component)
    await router.push(scriptRouteLocation('MAA', 'userEdit', { scriptId: 'second', userId: 'u1' }))
    await router.push(scriptRouteLocation('MAA', 'userEdit', { scriptId: 'second', userId: 'u2' }))
    expect(router.currentRoute.value.params).toEqual({ scriptId: 'second', userId: 'u2' })
    expect(loaded.user).toHaveBeenCalledTimes(1)
    expect(loaded.host).not.toHaveBeenCalled()
  })
})
