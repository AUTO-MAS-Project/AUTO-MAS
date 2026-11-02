import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { QqService } from '@/api'
import { useClawBinding } from './useClawBinding'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('ant-design-vue', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
vi.mock('@/utils/analytics', () => ({
  beginAnalyticsOperation: () => ({ finish: vi.fn() }),
}))

vi.mock('@/api', () => ({
  QqService: {
    getStatusApiSettingOpenclawQqStatusPost: vi.fn(),
    startLoginApiSettingOpenclawQqLoginStartPost: vi.fn(),
    checkLoginApiSettingOpenclawQqLoginCheckPost: vi.fn(),
    unbindApiSettingOpenclawQqUnbindPost: vi.fn(),
    getGroupsApiSettingOpenclawQqGroupsPost: vi.fn(),
    setCredentialsApiSettingOpenclawQqCredentialsSetPost: vi.fn(),
  },
}))

afterEach(() => vi.resetAllMocks())

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => {
    resolve = done
  })
  return { promise, resolve }
}

async function createBinding(services: object) {
  for (const [name, implementation] of Object.entries(services)) {
    vi.mocked(QqService[name as Exclude<keyof typeof QqService, 'prototype'>]).mockImplementation(
      implementation
    )
  }
  let binding!: ReturnType<typeof useClawBinding>
  await renderToString(
    createSSRApp({
      setup() {
        binding = useClawBinding('qq', async () => {})
        return () => null
      },
    })
  )
  return binding
}

const credentials = { bindingId: 'old', appId: 'app', userOpenId: 'owner' }
const connected = { code: 200, enabled: true, connected: true, state: 'connected' }

describe('manual QQ binding refresh', () => {
  it('discards an earlier groups response and refreshes the saved binding', async () => {
    const old = deferred<{ code: number; bindingId: string }>()
    const getGroupsApiSettingOpenclawQqGroupsPost = vi
      .fn()
      .mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce({
        code: 200,
        bindingId: 'new',
        groupCommandWhitelist: [],
      })
    const binding = await createBinding({
      getGroupsApiSettingOpenclawQqGroupsPost,
      getStatusApiSettingOpenclawQqStatusPost: vi.fn().mockResolvedValue(connected),
      setCredentialsApiSettingOpenclawQqCredentialsSetPost: vi
        .fn()
        .mockResolvedValue({ code: 200 }),
    })
    const pending = binding.loadGroups()
    await expect(binding.saveCredentials(credentials)).resolves.toBe(true)
    old.resolve({ code: 200, bindingId: 'old' })
    await pending
    expect(binding.groups.value?.bindingId).toBe('new')
    expect(getGroupsApiSettingOpenclawQqGroupsPost).toHaveBeenCalledTimes(2)
  })

  it('does not start a manual save while an earlier status request is running', async () => {
    const status = deferred<typeof connected>()
    const save = vi.fn().mockResolvedValue({ code: 200 })
    const binding = await createBinding({
      getStatusApiSettingOpenclawQqStatusPost: () => status.promise,
      setCredentialsApiSettingOpenclawQqCredentialsSetPost: save,
    })
    const pending = binding.loadStatus()
    await expect(binding.saveCredentials(credentials)).resolves.toBe(false)
    expect(save).not.toHaveBeenCalled()
    status.resolve(connected)
    await pending
  })
})
