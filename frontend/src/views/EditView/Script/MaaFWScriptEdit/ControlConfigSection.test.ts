import { beforeAll, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createI18n } from 'vue-i18n'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import Antd from 'ant-design-vue'
import type { GameBindingOptionsOut } from '@/api'
import type { GameBindingValue } from '@/types/games'
import type { MaaFWScriptConfig } from '@/types/script'

// 分节的依赖在模块加载时就取日志器（IPC 边界）；只在导入期间提供，渲染时恢复 Node 环境
vi.hoisted(() => {
  vi.stubGlobal('window', { electronAPI: { getLogger: () => ({ error: () => {} }) } })
})
vi.mock('@/composables/useScriptApi', () => ({ useScriptApi: () => ({ updateScript: vi.fn() }) }))
vi.mock('@/composables/useUserApi', () => ({ useUserApi: () => ({ updateUser: vi.fn() }) }))
vi.mock('@/services/websocket/connection', () => ({
  connectionState: vi.fn(),
  onConnected: vi.fn(),
  onDisconnected: vi.fn(),
}))
vi.mock('@/services/websocket/subscriptions', () => ({ subscribe: vi.fn(), unsubscribe: vi.fn() }))

const { default: ControlConfigSection } = await import('./ControlConfigSection.vue')

const EMULATOR = '6f1d3c52-0d6e-4c1b-9a51-7c2d0e3b9a10'
const CLIENT = '2b8e7a14-55c3-4f09-8d2e-1a6b9c0d4e21'
const LIVE_DEVICE = '9c4a1e77-3b2d-4e8f-a015-6d7c8b9e0f32'
const DELETED_DEVICE = 'd03f5b29-7e1a-4c6d-b8f4-2a9e1c0b7d43'

beforeAll(() => {
  vi.unstubAllGlobals()
})

async function render(binding: GameBindingValue) {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } })
  // 持久化的控制方式为空，后端不知道控制方式，不给类型不一致的提示
  const options: GameBindingOptionsOut = {
    code: 200,
    supported: true,
    accountOverrideSupported: true,
    data: [
      { value: EMULATOR, label: 'MuMu 12' },
      { value: CLIENT, label: '终末地' },
    ],
  }
  client.setQueryData(['game-binding-options', 'script', undefined], options)
  client.setQueryData(['game-binding', 'script', undefined], { binding })
  client.setQueryData(['game-types'], {
    code: 200,
    data: [
      { type: 'mumu', name: 'MuMu', configType: 'MuMuGame', kind: 'emulator' },
      { type: 'win_process', name: 'Windows', configType: 'WinProcessGame', kind: 'client' },
    ],
  })
  client.setQueryData(['games'], {
    code: 200,
    order: [
      { uid: EMULATOR, type: 'MuMuGame' },
      { uid: CLIENT, type: 'WinProcessGame' },
    ],
    data: {
      [EMULATOR]: {
        info: { name: 'MuMu 12' },
        devices: {
          order: [{ uid: LIVE_DEVICE }, { uid: DELETED_DEVICE }],
          data: {
            [LIVE_DEVICE]: { info: { name: '实例一' } },
            // 已删除实例的墓碑：删除时托管正旁挂或正在运行，绑定还没规整
            [DELETED_DEVICE]: { info: { name: '旧实例', tombstone: true } },
          },
        },
      },
      [CLIENT]: { info: { name: '终末地' } },
    },
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/scripts/:id/edit/maafw', component: { render: () => null } }],
  })
  await router.push('/scripts/script/edit/maafw')
  const app = createSSRApp(() =>
    h(ControlConfigSection, {
      scriptId: 'script',
      maafwConfig: {
        Info: { Controller: '', Resource: '' },
        Game: { PackageName: '', WaitTime: 120 },
      } as unknown as MaaFWScriptConfig,
      previewData: null,
      interfaceLoading: false,
      controllerOptions: [{ name: 'ADB', type: 'Adb', option: [], permissionRequired: false }],
      effectiveControllerName: 'ADB',
      effectiveControllerType: 'Adb',
      isAdbController: true,
      isDesktopController: false,
      resourceOptions: [],
      effectiveResourceName: '',
      adbControlStrategyItems: [],
      interfaceDependentDisabled: false,
    })
  )
  app.use(router)
  app.use(Antd)
  app.use(VueQueryPlugin, { queryClient: client })
  app.use(createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false }))
  return renderToString(app)
}

describe('MFW 控制配置里的游戏目标', () => {
  it('后端没给提示时仍按当前控制方式判出类型不符，保留绑定、可清空，下拉不露 uid', async () => {
    const html = await render({ game_id: CLIENT, device_id: '-' })
    expect(html).toMatch(/ant-alert-warning[^]*?core\.games\.kindMismatch[^]*?core\.edit\.clear/)
    expect(html).toContain('终末地')
    expect(html).not.toContain(CLIENT)
  })

  it('所绑实例已删除（墓碑）时给出提示，实例下拉不露 uid', async () => {
    const html = await render({ game_id: EMULATOR, device_id: DELETED_DEVICE })
    expect(html).toContain('core.games.deviceDeleted')
    expect(html).toContain('旧实例 (core.games.deleted)')
    expect(html).not.toContain(DELETED_DEVICE)
  })
})
