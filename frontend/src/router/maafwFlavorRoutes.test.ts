import { describe, expect, it } from 'vitest'
import { MAAFW_SPECIAL_FLAVORS } from '@/composables/useMaaFWFlavor'
import { buildMaaFWFlavorRoutes } from './maafwFlavorRoutes'

const scriptPage = () => Promise.resolve({ default: {} })
const userPage = () => Promise.resolve({ default: {} })

describe('特调路由按注册表生成', () => {
  const routes = buildMaaFWFlavorRoutes(MAAFW_SPECIAL_FLAVORS, {
    script: scriptPage,
    user: userPage,
  })
  const shape = (list: typeof routes.scriptEdit) =>
    list.map(route => ({ path: route.path, name: route.name, meta: route.meta }))

  it('路由名、路径、meta 与原先手写的六条一致', () => {
    expect(shape(routes.scriptEdit)).toEqual([
      {
        path: '/scripts/:id/edit/m9a',
        name: 'M9AScriptEdit',
        meta: { title: '编辑M9A脚本', scriptType: 'M9A' },
      },
      {
        path: '/scripts/:id/edit/mss',
        name: 'MSSScriptEdit',
        meta: { title: '编辑MSS脚本', scriptType: 'MSS' },
      },
    ])
    expect(shape(routes.userAdd)).toEqual([
      {
        path: '/scripts/:scriptId/users/add/m9a',
        name: 'M9AUserAdd',
        meta: { title: '添加M9A用户', scriptType: 'M9A' },
      },
      {
        path: '/scripts/:scriptId/users/add/mss',
        name: 'MSSUserAdd',
        meta: { title: '添加MSS用户', scriptType: 'MSS' },
      },
    ])
    expect(shape(routes.userEdit)).toEqual([
      {
        path: '/scripts/:scriptId/users/:userId/edit/m9a',
        name: 'M9AUserEdit',
        meta: { title: '编辑M9A用户', scriptType: 'M9A' },
      },
      {
        path: '/scripts/:scriptId/users/:userId/edit/mss',
        name: 'MSSUserEdit',
        meta: { title: '编辑MSS用户', scriptType: 'MSS' },
      },
    ])
  })

  it('脚本页与用户页都指向 MaaFW 的公共组件', () => {
    for (const route of routes.scriptEdit) expect(route.component).toBe(scriptPage)
    for (const route of [...routes.userAdd, ...routes.userEdit]) {
      expect(route.component).toBe(userPage)
    }
  })

  it('用户页「加用户 → 编辑」按路由名成对切换（UserAdd → UserEdit）仍然成立', () => {
    const editNames = new Set(routes.userEdit.map(route => route.name))
    for (const route of routes.userAdd) {
      expect(editNames.has(String(route.name).replace(/UserAdd$/, 'UserEdit'))).toBe(true)
    }
  })
})
