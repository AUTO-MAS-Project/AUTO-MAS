import { createSSRApp, type Ref } from 'vue'
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
    success: vi.fn(),
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
  message: { error: mocks.error, success: mocks.success, info: vi.fn() },
}))
vi.mock('@/composables/useEmulatorApi', () => ({ Service: mocks.service, EmulatorOperateIn: {} }))
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
  loadDevices: (key: string) => Promise<void>
  pollDevicesStatus: () => Promise<void>
  needsEmulatorPath: (key: string) => boolean
  getEditingData: (key: string) => { path: string }
  emulatorData: Ref<Record<string, { Info: { Path: string | null } }>>
  devicesData: Ref<Record<string, Record<string, { title: string }>>>
}

const configResponse = (path: string | null) => ({
  code: 200,
  index: [{ uid: 'draft', type: 'EmulatorConfig' }],
  data: { draft: { Info: { Name: 'Draft', Type: 'general', Path: path } } },
})

const deferred = <T>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => {
    resolve = done
  })
  return { promise, resolve }
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

  it.each(['network', 'response', 'missing'])(
    '保存成功后首次回读 %s 失败，轮询恢复权威配置及设备',
    async failure => {
      await page.loadEmulators()
      await page.onEmulatorsLoaded()
      mocks.selectFile.mockResolvedValue(['/picked/shortcut.lnk'])
      mocks.service.updateEmulatorApiEmulatorUpdatePost.mockImplementation(async () => {
        savedPath = '/normalized/manager.exe'
        return { code: 200 }
      })
      if (failure === 'network') {
        mocks.service.getEmulatorApiEmulatorGetPost.mockRejectedValueOnce(new Error('offline'))
      } else {
        mocks.service.getEmulatorApiEmulatorGetPost.mockResolvedValueOnce(
          failure === 'response'
            ? { code: 500, message: 'temporary failure' }
            : { code: 200, index: [], data: {} }
        )
      }
      await page.selectEmulatorPath('draft')
      expect(page.needsEmulatorPath('draft')).toBe(true)
      expect(mocks.service.getStatusApiEmulatorStatusPost).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(10_000)
      expect(page.emulatorData.value.draft.Info.Path).toBe('/normalized/manager.exe')
      expect(page.getEditingData('draft').path).toBe('/normalized/manager.exe')
      expect(page.needsEmulatorPath('draft')).toBe(false)
      expect(mocks.service.getStatusApiEmulatorStatusPost).toHaveBeenCalledTimes(1)
      await vi.advanceTimersByTimeAsync(30_000)
      expect(mocks.service.getEmulatorApiEmulatorGetPost).toHaveBeenCalledTimes(3)
      expect(mocks.service.getStatusApiEmulatorStatusPost).toHaveBeenCalledTimes(4)
      expect(mocks.selectFile).toHaveBeenCalledTimes(1)
      expect(mocks.error).not.toHaveBeenCalled()
    }
  )

  it.each(['wrong index', 'missing info'])('回读 %s 不能被误判为同步成功', async incomplete => {
    await page.loadEmulators()
    await page.onEmulatorsLoaded()
    mocks.selectFile.mockResolvedValue(['/picked/emulator.exe'])
    const response = configResponse('/normalized/manager.exe')
    mocks.service.getEmulatorApiEmulatorGetPost.mockResolvedValueOnce(
      incomplete === 'wrong index'
        ? { ...response, index: [{ uid: 'other', type: 'EmulatorConfig' }] }
        : { ...response, data: { draft: {} } }
    )
    await page.selectEmulatorPath('draft')
    expect(page.needsEmulatorPath('draft')).toBe(true)
    expect(mocks.service.getStatusApiEmulatorStatusPost).not.toHaveBeenCalled()
    await page.onTabChange('draft')
    expect(page.needsEmulatorPath('draft')).toBe(false)
    expect(mocks.service.getStatusApiEmulatorStatusPost).toHaveBeenCalledTimes(1)
  })

  it('回读自动尝试有上限，耗尽后只提示一次，切换页签仍可重试', async () => {
    await page.loadEmulators()
    await page.onEmulatorsLoaded()
    mocks.selectFile.mockResolvedValue(['/picked/emulator.exe'])
    mocks.service.getEmulatorApiEmulatorGetPost.mockRejectedValue(new Error('offline'))
    await page.selectEmulatorPath('draft')
    await vi.advanceTimersByTimeAsync(100_000)
    expect(mocks.service.getEmulatorApiEmulatorGetPost).toHaveBeenCalledTimes(4)
    expect(mocks.service.getStatusApiEmulatorStatusPost).not.toHaveBeenCalled()
    expect(mocks.error).toHaveBeenCalledExactlyOnceWith('core.emulator.toast.loadFailed')
    mocks.service.getEmulatorApiEmulatorGetPost.mockResolvedValue(
      configResponse('/normalized/manager.exe')
    )
    await page.onTabChange('draft')
    expect(page.needsEmulatorPath('draft')).toBe(false)
    expect(mocks.service.getStatusApiEmulatorStatusPost).toHaveBeenCalledTimes(1)
    expect(mocks.selectFile).toHaveBeenCalledTimes(1)
  })

  it('慢回读不重叠重试，也不重复弹出耗尽提示', async () => {
    await page.loadEmulators()
    await page.onEmulatorsLoaded()
    mocks.selectFile.mockResolvedValue(['/picked/emulator.exe'])
    mocks.service.getEmulatorApiEmulatorGetPost.mockRejectedValueOnce(new Error('offline'))
    await page.selectEmulatorPath('draft')
    const slowResponse = deferred<{ code: number; message: string }>()
    mocks.service.getEmulatorApiEmulatorGetPost.mockImplementationOnce(() => slowResponse.promise)
    mocks.service.getEmulatorApiEmulatorGetPost.mockResolvedValue({
      code: 500,
      message: 'offline',
    })
    await vi.advanceTimersByTimeAsync(40_000)
    expect(mocks.service.getEmulatorApiEmulatorGetPost).toHaveBeenCalledTimes(3)
    expect(mocks.error).not.toHaveBeenCalled()
    slowResponse.resolve({ code: 500, message: 'offline' })
    await vi.advanceTimersByTimeAsync(100_000)
    expect(mocks.service.getEmulatorApiEmulatorGetPost).toHaveBeenCalledTimes(4)
    expect(mocks.error).toHaveBeenCalledExactlyOnceWith('core.emulator.toast.loadFailed')
    expect(mocks.service.getStatusApiEmulatorStatusPost).not.toHaveBeenCalled()
  })

  it.each(['response', 'network'])(
    '保存 %s 失败不查询、不提示成功，仍允许重新选择',
    async failure => {
      await page.loadEmulators()
      await page.onEmulatorsLoaded()
      mocks.selectFile.mockResolvedValue(['/picked/emulator.exe'])
      if (failure === 'network') {
        mocks.service.updateEmulatorApiEmulatorUpdatePost.mockRejectedValueOnce(
          new Error('offline')
        )
      } else {
        mocks.service.updateEmulatorApiEmulatorUpdatePost.mockResolvedValueOnce({
          code: 500,
          message: 'save failed',
        })
      }
      await page.selectEmulatorPath('draft')
      await vi.advanceTimersByTimeAsync(40_000)
      expect(page.needsEmulatorPath('draft')).toBe(true)
      expect(mocks.service.getEmulatorApiEmulatorGetPost).toHaveBeenCalledTimes(1)
      expect(mocks.service.getStatusApiEmulatorStatusPost).not.toHaveBeenCalled()
      expect(mocks.success).not.toHaveBeenCalled()
      expect(mocks.error).toHaveBeenCalledTimes(1)
      await page.selectEmulatorPath('draft')
      expect(mocks.service.getStatusApiEmulatorStatusPost).toHaveBeenCalledTimes(1)
      expect(mocks.success).toHaveBeenCalledTimes(1)
    }
  )

  it('后端将无效路径清空后保持未配置，不使用原始选择路径', async () => {
    await page.loadEmulators()
    await page.onEmulatorsLoaded()
    mocks.selectFile.mockResolvedValue(['/picked/invalid.exe'])
    mocks.service.updateEmulatorApiEmulatorUpdatePost.mockImplementation(async () => ({
      code: 200,
    }))
    await page.selectEmulatorPath('draft')
    await vi.advanceTimersByTimeAsync(30_000)
    expect(page.emulatorData.value.draft.Info.Path).toBeNull()
    expect(page.getEditingData('draft').path).toBe('')
    expect(mocks.service.getEmulatorApiEmulatorGetPost).toHaveBeenCalledTimes(2)
    expect(mocks.service.getStatusApiEmulatorStatusPost).not.toHaveBeenCalled()
  })

  it.each(['load', 'poll'])('路径切换后旧 %s 请求不能覆盖新设备', async source => {
    savedPath = '/old/emulator.exe'
    await page.loadEmulators()
    await page.onEmulatorsLoaded()
    const oldResponse = deferred<{ code: number; data: { draft: { 0: { title: string } } } }>()
    mocks.service.getStatusApiEmulatorStatusPost.mockImplementationOnce(() => oldResponse.promise)
    const oldRequest = source === 'load' ? page.loadDevices('draft') : page.pollDevicesStatus()
    mocks.service.getStatusApiEmulatorStatusPost.mockResolvedValue({
      code: 200,
      data: { draft: { 0: { title: 'new' } } },
    })
    mocks.selectFile.mockResolvedValue(['/new/emulator.exe'])
    await page.selectEmulatorPath('draft')
    expect(page.devicesData.value.draft[0].title).toBe('new')
    oldResponse.resolve({ code: 200, data: { draft: { 0: { title: 'old' } } } })
    await oldRequest
    expect(page.devicesData.value.draft[0].title).toBe('new')
  })

  it('恢复回读期间再次选路径，旧配置响应不能覆盖最新保存', async () => {
    await page.loadEmulators()
    await page.onEmulatorsLoaded()
    mocks.selectFile.mockResolvedValue(['/first/emulator.exe'])
    mocks.service.getEmulatorApiEmulatorGetPost.mockRejectedValueOnce(new Error('offline'))
    await page.selectEmulatorPath('draft')
    const oldResponse = deferred<ReturnType<typeof configResponse>>()
    mocks.service.getEmulatorApiEmulatorGetPost.mockImplementationOnce(() => oldResponse.promise)
    const recovery = page.pollDevicesStatus()
    mocks.selectFile.mockResolvedValue(['/second/emulator.exe'])
    await page.selectEmulatorPath('draft')
    oldResponse.resolve(configResponse('/first/emulator.exe'))
    await recovery
    expect(page.emulatorData.value.draft.Info.Path).not.toBe('/first/emulator.exe')
    await vi.advanceTimersByTimeAsync(10_000)
    expect(page.emulatorData.value.draft.Info.Path).toBe('/second/emulator.exe')
  })
})
