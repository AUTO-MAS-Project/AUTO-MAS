import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h, type Component } from 'vue'
import { renderToString } from '@vue/server-renderer'
import type { RouteMeta } from 'vue-router'
import { defineMaaFWLazyComponent, type MaaFWLazyComponent } from '@/composables/maafwFlavorTypes'

// 页面宿主：按脚本实际类型选页面、纠正后缀写错的地址、把上下文交给页面。仓库没有 DOM 环境，
// 用 SSR 渲染（async setup 会被等完）；MFW 的两个默认页换成会记录自己被建了几次的 stub。

const mocks = vi.hoisted(() => {
  const logger = { debug: () => {}, info: () => {}, warn: () => {}, error: () => {} }
  ;(globalThis as { window?: unknown }).window = { electronAPI: { getLogger: () => logger } }
  return {
    route: {
      fullPath: '',
      meta: {} as Record<string, unknown>,
      params: {} as Record<string, string>,
      query: {} as Record<string, string>,
      hash: '',
    },
    currentFullPath: '',
    replace: vi.fn(),
    getScript: vi.fn(),
    /** 页面 stub 在 setup 里替页面做的事：记下取到的上下文；用户页 stub 照用户页的样子建一个用户 */
    pageSetups: [] as Array<{ page: string; mode?: string; initial: unknown; again: unknown }>,
    addUser: vi.fn(),
    /** 类型 → 该类型的整页替换（脚本页与用户页同一个），测试里按需挂 */
    pageOverrides: {} as Record<string, MaaFWLazyComponent>,
  }
})

/** 页面 stub：在 setup 里取宿主上下文与读好的脚本详情（第二次取应为空） */
const pageStub = (page: string) =>
  defineComponent({
    name: page,
    setup() {
      const context = useMaaFWPageHostContext()
      const initial = context?.takeInitialScript()
      mocks.pageSetups.push({
        page,
        mode: context?.mode,
        initial,
        again: context?.takeInitialScript(),
      })
      if (page === 'default:userPage' && context?.mode === 'userAdd') mocks.addUser()
      return () => h('main', { 'data-page': page })
    },
  })

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({
    replace: mocks.replace,
    currentRoute: {
      get value() {
        return { fullPath: mocks.currentFullPath }
      },
    },
  }),
}))
vi.mock('@/composables/useScriptApi', () => ({
  useScriptApi: () => ({ getScript: mocks.getScript }),
}))
vi.mock('@/composables/useMaaFWFlavor', async original => {
  const actual = await original<typeof import('@/composables/useMaaFWFlavor')>()
  return {
    ...actual,
    resolveMaaFWFlavor: (type: string | null | undefined) => {
      const flavor = actual.resolveMaaFWFlavor(type)
      const page = mocks.pageOverrides[flavor.type]
      return page
        ? {
            ...flavor,
            scriptPage: { ...flavor.scriptPage, page },
            userPage: { ...flavor.userPage, page },
          }
        : flavor
    },
  }
})
// __esModule：mock 出来的模块对象没有 Symbol.toStringTag，defineAsyncComponent 靠它认出 default
vi.mock('../Script/MaaFWScriptEdit.vue', () => ({
  __esModule: true,
  default: pageStub('default:scriptPage'),
}))
vi.mock('../User/MaaFWUserEdit.vue', () => ({
  __esModule: true,
  default: pageStub('default:userPage'),
}))

import { MAAFW_DEFAULT_PAGES, useMaaFWPageHost } from './useMaaFWPageHost'
import { useMaaFWPageHostContext } from './pageHostContext'
import MaaFWPageHost from './MaaFWPageHost.vue'

const script = (type: string) => ({ uid: 's1', type, name: 'demo', config: { Info: {} } })

const setRoute = (
  meta: RouteMeta,
  params: Record<string, string>,
  extra: { query?: Record<string, string>; hash?: string } = {}
) => {
  const fullPath = `/scripts/${JSON.stringify(params)}/${String(meta.maafwPage)}`
  Object.assign(mocks.route, {
    fullPath,
    meta,
    params,
    query: extra.query ?? {},
    hash: extra.hash ?? '',
  })
  mocks.currentFullPath = fullPath
}

/** 渲染宿主（等它读完脚本），返回 HTML 与宿主状态 */
const renderHost = async () => {
  let host!: ReturnType<typeof useMaaFWPageHost>
  const Root = defineComponent({
    async setup() {
      host = useMaaFWPageHost()
      await host.loaded
      return () => (host.page.value ? h(host.page.value) : null)
    },
  })
  const html = (await renderToString(createSSRApp(Root))).replace(/<!--[\s\S]*?-->/g, '')
  return { html, host }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.pageSetups.length = 0
  mocks.pageOverrides = {}
  mocks.replace.mockResolvedValue(undefined)
})

describe('页面宿主', () => {
  it('类型相符：渲染默认页，读好的脚本详情只交一次，不纠正地址', async () => {
    setRoute({ scriptType: 'MaaFW', maafwPage: 'setup' }, { id: 's1' })
    mocks.getScript.mockResolvedValue(script('MaaFW'))
    const { html, host } = await renderHost()
    expect(mocks.getScript).toHaveBeenCalledExactlyOnceWith('s1')
    expect(mocks.replace).not.toHaveBeenCalled()
    expect(html).toBe('<main data-page="default:scriptPage"></main>')
    expect(host.page.value).toBe(MAAFW_DEFAULT_PAGES.scriptPage.component)
    expect(mocks.pageSetups).toEqual([
      { page: 'default:scriptPage', mode: 'setup', initial: script('MaaFW'), again: undefined },
    ])
  })

  it('类型不符：replace 到实际类型那条线（带 query / hash），自己什么都不渲染', async () => {
    setRoute(
      { scriptType: 'MaaFW', maafwPage: 'script' },
      { id: 's1' },
      { query: { tab: 'x' }, hash: '#h' }
    )
    mocks.getScript.mockResolvedValue(script('M9A'))
    const { html, host } = await renderHost()
    expect(mocks.replace).toHaveBeenCalledExactlyOnceWith({
      name: 'M9AScriptEdit',
      params: { id: 's1' },
      query: { tab: 'x' },
      hash: '#h',
    })
    expect(html).toBe('')
    expect(host.page.value).toBeNull()
    expect(mocks.pageSetups).toEqual([])
  })

  it('加用户地址的后缀写错：纠正前不建页面（不建用户），纠正后的实例只建一个用户', async () => {
    setRoute({ scriptType: 'MaaFW', maafwPage: 'userAdd' }, { scriptId: 's1' })
    mocks.getScript.mockResolvedValue(script('MSS'))
    await renderHost()
    expect(mocks.replace).toHaveBeenCalledExactlyOnceWith({
      name: 'MSSUserAdd',
      params: { scriptId: 's1' },
      query: {},
      hash: '',
    })
    expect(mocks.addUser).not.toHaveBeenCalled()

    // 路径变了，AppLayout 重建出纠正后地址上的宿主
    setRoute({ scriptType: 'MSS', maafwPage: 'userAdd' }, { scriptId: 's1' })
    const { html } = await renderHost()
    expect(html).toBe('<main data-page="default:userPage"></main>')
    expect(mocks.replace).toHaveBeenCalledOnce()
    expect(mocks.addUser).toHaveBeenCalledOnce()
  })

  it('特调有整页替换：渲染特调自己的页面，上下文照样交给它', async () => {
    mocks.pageOverrides.M9A = defineMaaFWLazyComponent(async () => pageStub('m9a:page'))
    setRoute({ scriptType: 'M9A', maafwPage: 'userEdit' }, { scriptId: 's1', userId: 'u1' })
    mocks.getScript.mockResolvedValue(script('M9A'))
    const { html, host } = await renderHost()
    expect(html).toBe('<main data-page="m9a:page"></main>')
    expect(host.page.value).toBe(mocks.pageOverrides.M9A.component)
    expect(mocks.pageSetups).toEqual([
      { page: 'm9a:page', mode: 'userEdit', initial: script('M9A'), again: undefined },
    ])
  })

  it('会话内类型变了（默认页 → 默认页）：组件引用不变，页面不重建', async () => {
    setRoute({ scriptType: 'MaaFW', maafwPage: 'setup' }, { id: 's1' })
    mocks.getScript.mockResolvedValue(script('MaaFW'))
    const { host } = await renderHost()
    const before = host.page.value
    host.wizardStep.value = 2
    host.scriptType.value = 'MSS'
    expect(host.page.value).toBe(before)
    host.scriptType.value = 'M9A'
    expect(host.page.value).toBe(before)
    expect(host.wizardStep.value).toBe(2)
    expect(mocks.replace).not.toHaveBeenCalled()
  })

  it('会话内类型变成有整页替换的特调：就地换页面，引导步骤留在宿主里；换回来又是默认页', async () => {
    mocks.pageOverrides.M9A = defineMaaFWLazyComponent(async () => pageStub('m9a:page'))
    setRoute({ scriptType: 'MaaFW', maafwPage: 'setup' }, { id: 's1' })
    mocks.getScript.mockResolvedValue(script('MaaFW'))
    const { host } = await renderHost()
    expect(host.page.value).toBe(MAAFW_DEFAULT_PAGES.scriptPage.component)
    host.wizardStep.value = 2
    host.scriptType.value = 'M9A'
    expect(host.page.value).toBe(mocks.pageOverrides.M9A.component)
    expect(host.wizardStep.value).toBe(2)
    host.scriptType.value = 'MaaFW'
    expect(host.page.value).toBe(MAAFW_DEFAULT_PAGES.scriptPage.component)
    // 会话内换类型从不改地址
    expect(mocks.replace).not.toHaveBeenCalled()
  })

  it('脚本不存在 / 读取失败 / 不是 MaaFW 家族：渲染默认页，由页面给出现有的报错', async () => {
    setRoute({ scriptType: 'MaaFW', maafwPage: 'userEdit' }, { scriptId: 's1', userId: 'u1' })
    // getScript 读不到时返回 null（它自己已经提示过）：原样交给页面，页面不再请求一次
    mocks.getScript.mockResolvedValueOnce(null)
    expect((await renderHost()).html).toBe('<main data-page="default:userPage"></main>')
    // 意外抛错：什么都不交，页面自己读
    mocks.getScript.mockRejectedValueOnce(new Error('boom'))
    await renderHost()
    // 别的脚本类型：不纠正，脚本详情交给页面
    mocks.getScript.mockResolvedValueOnce(script('MAA'))
    await renderHost()
    expect(mocks.pageSetups.map(entry => entry.initial)).toEqual([null, undefined, script('MAA')])
    expect(mocks.replace).not.toHaveBeenCalled()
  })

  it('纠正没走成而且还停在原地址：按实际类型照常渲染，不留空白', async () => {
    setRoute({ scriptType: 'MaaFW', maafwPage: 'script' }, { id: 's1' })
    mocks.getScript.mockResolvedValue(script('M9A'))
    mocks.replace.mockResolvedValueOnce({ type: 4, message: 'aborted' })
    const { html, host } = await renderHost()
    expect(html).toBe('<main data-page="default:scriptPage"></main>')
    expect(host.scriptType.value).toBe('M9A')
    // 被别的导航顶掉（已经不在原地址）：什么都不渲染
    mocks.replace.mockImplementationOnce(async () => {
      mocks.currentFullPath = '/scripts'
      return { type: 8, message: 'cancelled' }
    })
    expect((await renderHost()).html).toBe('')
  })

  it('MaaFWPageHost.vue：读到脚本之前什么都不渲染；类型不符时 replace', async () => {
    setRoute({ scriptType: 'MSS', maafwPage: 'script' }, { id: 's1' })
    mocks.getScript.mockResolvedValue(script('MaaFW'))
    const html = await renderToString(createSSRApp(MaaFWPageHost as Component))
    expect(html.replace(/<!--[\s\S]*?-->/g, '')).toBe('')
    await vi.waitFor(() =>
      expect(mocks.replace).toHaveBeenCalledWith({
        name: 'MaaFWScriptEdit',
        params: { id: 's1' },
        query: {},
        hash: '',
      })
    )
    expect(mocks.getScript).toHaveBeenCalledExactlyOnceWith('s1')
  })
})
