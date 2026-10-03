import { describe, expect, it } from 'vitest'
import { MAAFW_FLAVORS } from '@/composables/useMaaFWFlavor'
import type { MaaFWPageKind } from '@/composables/maafwFlavorTypes'
import {
  MAAFW_PAGE_KINDS,
  buildMaaFWRoutes,
  maafwRouteLocation,
  maafwRouteName,
  resolveMaaFWCanonicalLocation,
} from './maafwFlavorRoutes'

const host = () => Promise.resolve({ default: {} })

describe('MaaFW 家族路由按注册表生成', () => {
  const routes = buildMaaFWRoutes(MAAFW_FLAVORS, host)
  const all = Object.values(routes).flat()
  const shape = (kind: MaaFWPageKind) =>
    routes[kind].map(route => ({ path: route.path, name: route.name, meta: route.meta }))

  it('三个类型各四条，共 12 条，路由名与路径都不重复', () => {
    expect(MAAFW_PAGE_KINDS).toEqual(['script', 'setup', 'userAdd', 'userEdit'])
    expect(all).toHaveLength(12)
    expect(new Set(all.map(route => route.name)).size).toBe(12)
    expect(new Set(all.map(route => route.path)).size).toBe(12)
    for (const flavor of MAAFW_FLAVORS) {
      expect(all.filter(route => route.meta?.scriptType === flavor.type)).toHaveLength(4)
    }
  })

  it('MaaFW 的四条与原先手写的路由名、路径、标题一字不差（老链接照常可用）', () => {
    const maafw = all.filter(route => route.meta?.scriptType === 'MaaFW')
    expect(maafw.map(route => [route.name, route.path, route.meta?.title])).toEqual([
      ['MaaFWScriptEdit', '/scripts/:id/edit/maafw', '编辑MFW脚本'],
      ['MaaFWSetupWizard', '/scripts/:id/setup/maafw', 'MaaFramework项目引导'],
      ['MaaFWUserAdd', '/scripts/:scriptId/users/add/maafw', '添加 MFW 用户'],
      ['MaaFWUserEdit', '/scripts/:scriptId/users/:userId/edit/maafw', '编辑 MFW 用户'],
    ])
  })

  it('M9A / MSS 的脚本页与用户页路由与原先生成的一致，另各多一条引导路由', () => {
    expect(shape('script')).toEqual([
      {
        path: '/scripts/:id/edit/maafw',
        name: 'MaaFWScriptEdit',
        meta: { title: '编辑MFW脚本', scriptType: 'MaaFW', maafwPage: 'script' },
      },
      {
        path: '/scripts/:id/edit/m9a',
        name: 'M9AScriptEdit',
        meta: { title: '编辑M9A脚本', scriptType: 'M9A', maafwPage: 'script' },
      },
      {
        path: '/scripts/:id/edit/mss',
        name: 'MSSScriptEdit',
        meta: { title: '编辑MSS脚本', scriptType: 'MSS', maafwPage: 'script' },
      },
    ])
    expect(shape('setup')).toEqual([
      {
        path: '/scripts/:id/setup/maafw',
        name: 'MaaFWSetupWizard',
        meta: { title: 'MaaFramework项目引导', scriptType: 'MaaFW', maafwPage: 'setup' },
      },
      {
        path: '/scripts/:id/setup/m9a',
        name: 'M9ASetupWizard',
        meta: { title: 'M9A项目引导', scriptType: 'M9A', maafwPage: 'setup' },
      },
      {
        path: '/scripts/:id/setup/mss',
        name: 'MSSSetupWizard',
        meta: { title: 'MSS项目引导', scriptType: 'MSS', maafwPage: 'setup' },
      },
    ])
    expect(shape('userAdd').slice(1)).toEqual([
      {
        path: '/scripts/:scriptId/users/add/m9a',
        name: 'M9AUserAdd',
        meta: { title: '添加M9A用户', scriptType: 'M9A', maafwPage: 'userAdd' },
      },
      {
        path: '/scripts/:scriptId/users/add/mss',
        name: 'MSSUserAdd',
        meta: { title: '添加MSS用户', scriptType: 'MSS', maafwPage: 'userAdd' },
      },
    ])
    expect(shape('userEdit').slice(1)).toEqual([
      {
        path: '/scripts/:scriptId/users/:userId/edit/m9a',
        name: 'M9AUserEdit',
        meta: { title: '编辑M9A用户', scriptType: 'M9A', maafwPage: 'userEdit' },
      },
      {
        path: '/scripts/:scriptId/users/:userId/edit/mss',
        name: 'MSSUserEdit',
        meta: { title: '编辑MSS用户', scriptType: 'MSS', maafwPage: 'userEdit' },
      },
    ])
  })

  it('12 条的组件都是页面宿主（由它按脚本实际类型选页面）', () => {
    for (const route of all) expect(route.component).toBe(host)
  })

  it('maafwRouteLocation 与生成的路由同一张名字表；未知类型按通用 MaaFW', () => {
    for (const route of all) {
      expect(maafwRouteName(route.meta!.scriptType, route.meta!.maafwPage!)).toBe(route.name)
    }
    expect(maafwRouteLocation('M9A', 'script', { id: 's1' })).toEqual({
      name: 'M9AScriptEdit',
      params: { id: 's1' },
    })
    expect(maafwRouteLocation('MSS', 'setup', { id: 's1' })).toEqual({
      name: 'MSSSetupWizard',
      params: { id: 's1' },
    })
    expect(maafwRouteLocation('MaaFW', 'userAdd', { scriptId: 's1' })).toEqual({
      name: 'MaaFWUserAdd',
      params: { scriptId: 's1' },
    })
    expect(maafwRouteLocation('M9A', 'userEdit', { scriptId: 's1', userId: 'u1' })).toEqual({
      name: 'M9AUserEdit',
      params: { scriptId: 's1', userId: 'u1' },
    })
    for (const type of ['MAA', 'General', '', null, undefined]) {
      expect(maafwRouteLocation(type, 'userAdd', { scriptId: 's1' }).name).toBe('MaaFWUserAdd')
    }
  })
})

describe('resolveMaaFWCanonicalLocation：路由登记的类型与脚本实际类型不符时纠正', () => {
  const route = (meta: Record<string, unknown>) => ({
    meta,
    params: { scriptId: 's1', userId: 'u1' },
    query: { from: 'list' },
    hash: '#queue',
  })

  it('同一个类型：不用纠正', () => {
    expect(
      resolveMaaFWCanonicalLocation(route({ scriptType: 'M9A', maafwPage: 'userEdit' }), 'M9A')
    ).toBeNull()
  })

  it('不符：同一种页面、实际类型那条线，参数 / query / hash 照带', () => {
    expect(
      resolveMaaFWCanonicalLocation(route({ scriptType: 'MaaFW', maafwPage: 'userEdit' }), 'MSS')
    ).toEqual({
      name: 'MSSUserEdit',
      params: { scriptId: 's1', userId: 'u1' },
      query: { from: 'list' },
      hash: '#queue',
    })
    expect(
      resolveMaaFWCanonicalLocation(
        {
          meta: { scriptType: 'M9A', maafwPage: 'setup' },
          params: { id: 's1' },
          query: {},
          hash: '',
        },
        'MaaFW'
      )
    ).toEqual({ name: 'MaaFWSetupWizard', params: { id: 's1' }, query: {}, hash: '' })
  })

  it('脚本不是 MaaFW 家族：不纠正（页面照常给出现有的报错）', () => {
    for (const type of ['MAA', 'General', '', null, undefined]) {
      expect(
        resolveMaaFWCanonicalLocation(route({ scriptType: 'MaaFW', maafwPage: 'userAdd' }), type)
      ).toBeNull()
    }
  })

  it('路由没有 MaaFW 的 meta（不是生成的那几条）：不纠正', () => {
    expect(resolveMaaFWCanonicalLocation(route({}), 'M9A')).toBeNull()
    expect(resolveMaaFWCanonicalLocation(route({ scriptType: 'MaaFW' }), 'M9A')).toBeNull()
    expect(resolveMaaFWCanonicalLocation(route({ maafwPage: 'script' }), 'M9A')).toBeNull()
  })
})
