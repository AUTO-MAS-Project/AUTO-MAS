import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import Emulator from './Emulator.vue'

const mocks = vi.hoisted(() => {
  const logger = { info: vi.fn(), warn: vi.fn(), error: vi.fn() }
  const selectFile = vi.fn()
  vi.stubGlobal('window', { electronAPI: { getLogger: () => logger, selectFile } })
  return {
    selectFile,
    error: vi.fn(),
    service: {
      addEmulatorApiEmulatorAddPost: vi.fn(),
      getEmulatorApiEmulatorGetPost: vi.fn(),
      updateEmulatorApiEmulatorUpdatePost: vi.fn(),
      getStatusApiEmulatorStatusPost: vi.fn(),
    },
  }
})

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ path: '/emulators' }) }))
vi.mock('@vueuse/core', () => ({ useEventListener: vi.fn() }))
vi.mock('ant-design-vue', () => ({
  message: { error: mocks.error, success: vi.fn(), info: vi.fn() },
}))
vi.mock('@/api', () => ({ Service: mocks.service, EmulatorOperateIn: {} }))
vi.mock('@/stores/performance', () => ({
  usePerformanceStore: () => ({ isBackgrounded: false }),
}))
vi.mock('@/composables/useEmulatorOptions', () => ({ invalidateEmulatorOptions: vi.fn() }))
vi.mock('@/composables/useEmulatorDeviceOptions', () => ({
  invalidateEmulatorDeviceOptions: vi.fn(),
}))
vi.mock('@/components/DocLink.vue', () => ({ default: {} }))
vi.mock('@/views/Emulator/Emulator2Panel.vue', () => ({ default: {} }))
vi.mock('@/views/Emulator/components/EmulatorDeviceEmpty.vue', () => ({ default: {} }))
vi.mock('@/utils/openExternal', () => ({ MAS_DOC_URLS: {} }))

interface PageActions {
  loadEmulators: () => Promise<void>
  onEmulatorsLoaded: () => Promise<void>
  handleAdd: () => Promise<void>
  onTabChange: (key: string) => Promise<void>
  selectEmulatorPath: (key: string) => Promise<void>
}

let page: PageActions
let created: boolean
let savedPath: string | null

beforeEach(async () => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  vi.stubGlobal('document', {})
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() })
  created = true
  savedPath = null
  mocks.selectFile.mockResolvedValue([])
  mocks.service.addEmulatorApiEmulatorAddPost.mockImplementation(async () => {
    created = true
    return { code: 200, emulatorId: 'draft' }
  })
  mocks.service.getEmulatorApiEmulatorGetPost.mockImplementation(async () => ({
    code: 200,
    index: created ? [{ uid: 'draft', type: 'EmulatorConfig' }] : [],
    data: created ? { draft: { Info: { Name: 'Draft', Type: 'general', Path: savedPath } } } : {},
  }))
  mocks.service.updateEmulatorApiEmulatorUpdatePost.mockImplementation(async request => {
    savedPath = request.data.Info.Path
    return { code: 200 }
  })
  mocks.service.getStatusApiEmulatorStatusPost.mockResolvedValue({
    code: 200,
    data: { draft: {} },
  })
  // 在真实 SSR 上下文中调用页面 setup，只省略模板渲染，不复制业务逻辑。
  const setup = Emulator.setup as unknown as (
    props: Record<string, never>,
    context: { expose: () => void }
  ) => PageActions
  await renderToString(
    createSSRApp({
      setup(_props, context) {
        page = setup({}, context)
        return () => null
      },
    })
  )
})

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
})

afterAll(() => vi.unstubAllGlobals())

describe('模拟器路径配置', () => {
  it('空列表手动添加及重新加载、切换页签时不查询空路径', async () => {
    created = false
    await page.loadEmulators()
    await page.handleAdd()
    await page.onEmulatorsLoaded()
    await page.onTabChange('draft')
    expect(mocks.service.getStatusApiEmulatorStatusPost).not.toHaveBeenCalled()
    expect(mocks.error).not.toHaveBeenCalled()
  })

  it('选择并保存路径后立即恢复设备查询', async () => {
    await page.loadEmulators()
    mocks.selectFile.mockResolvedValue(['/isolated/emulator.exe'])
    await page.selectEmulatorPath('draft')
    expect(mocks.service.updateEmulatorApiEmulatorUpdatePost).toHaveBeenCalledWith({
      emulatorId: 'draft',
      data: { Info: { Path: '/isolated/emulator.exe' } },
    })
    expect(mocks.service.getStatusApiEmulatorStatusPost).toHaveBeenCalledExactlyOnceWith({
      emulatorId: 'draft',
    })
  })

  it('非空但无效的路径仍查询并展示后端错误', async () => {
    savedPath = '/isolated/missing.exe'
    const message = 'FileNotFoundError: 模拟器文件不存在: /isolated/missing.exe'
    mocks.service.getStatusApiEmulatorStatusPost.mockResolvedValue({ code: 500, message })
    await page.loadEmulators()
    await page.onEmulatorsLoaded()
    expect(mocks.service.getStatusApiEmulatorStatusPost).toHaveBeenCalledExactlyOnceWith({
      emulatorId: 'draft',
    })
    expect(mocks.error).toHaveBeenCalledWith(message)
  })

  it('连续轮询跳过空路径，保存路径后恢复轮询', async () => {
    await page.loadEmulators()
    await page.onEmulatorsLoaded()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(mocks.service.getStatusApiEmulatorStatusPost).not.toHaveBeenCalled()
    expect(mocks.error).not.toHaveBeenCalled()
    mocks.selectFile.mockResolvedValue(['/isolated/emulator.exe'])
    await page.selectEmulatorPath('draft')
    await vi.advanceTimersByTimeAsync(10_000)
    expect(mocks.service.getStatusApiEmulatorStatusPost).toHaveBeenCalledTimes(2)
  })
})
