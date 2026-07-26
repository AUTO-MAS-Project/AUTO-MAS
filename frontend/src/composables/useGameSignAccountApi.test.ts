/**
 * Lane 8：游戏签到账号 API 测试。
 *
 * 覆盖：
 * - addAccount: 成功返回 accountId+data；非 200 抛错并 message.error；网络异常返回 null
 * - updateAccount: 成功静默；非 200 抛错；网络异常抛错
 * - deleteAccount: 成功 message.success；非 200 抛错；网络异常抛错
 * - requireSuccess 契约：code !== 200 一律拒绝
 *
 * 设计：
 * - 通过 vi.mock 替换 Service，控制每次响应。
 * - 验证 useGameSignAccountApi 的错误处理和返回值契约。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// ---- Mocks --------------------------------------------------------------

const mockService = {
  addGameSignAccountApiToolsSignAccountAddPost: vi.fn(),
  updateGameSignAccountApiToolsSignAccountUpdatePost: vi.fn(),
  deleteGameSignAccountApiToolsSignAccountDeletePost: vi.fn(),
}

vi.mock('@/api', () => ({
  Service: mockService,
  // 让类型 import 在运行时不报错
}))

const messageSpy = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}

vi.mock('ant-design-vue', () => ({
  message: messageSpy,
}))

const logger = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}

// 动态 import 以确保 mock 生效
const loadComposable = async () => {
  vi.resetModules()
  return await import('./useGameSignAccountApi')
}

// ---- Tests ---------------------------------------------------------------

describe('useGameSignAccountApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('addAccount', () => {
    it('成功返回 accountId 和 data', async () => {
      mockService.addGameSignAccountApiToolsSignAccountAddPost.mockResolvedValue({
        code: 200,
        status: 'ok',
        message: '',
        accountId: 'acc-001',
        data: { Name: '用户1', Enabled: true, MiyousheToken: '' },
      })
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      const result = await api.addAccount()
      expect(result).not.toBeNull()
      expect(result!.accountId).toBe('acc-001')
      expect(result!.data).toEqual({ Name: '用户1', Enabled: true, MiyousheToken: '' })
      expect(api.loading.value).toBe(false)
    })

    it('code !== 200 时返回 null 并 message.error', async () => {
      mockService.addGameSignAccountApiToolsSignAccountAddPost.mockResolvedValue({
        code: 500,
        status: 'error',
        message: '后端拒绝',
        accountId: null,
        data: null,
      })
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      const result = await api.addAccount()
      expect(result).toBeNull()
      expect(messageSpy.error).toHaveBeenCalledWith('添加账号组失败')
      expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('后端拒绝'))
    })

    it('accountId 缺失时返回 null（契约：必须有 accountId）', async () => {
      mockService.addGameSignAccountApiToolsSignAccountAddPost.mockResolvedValue({
        code: 200,
        status: 'ok',
        message: '',
        // accountId 故意缺失
        data: { Name: 'x' },
      })
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      const result = await api.addAccount()
      expect(result).toBeNull()
      expect(messageSpy.error).toHaveBeenCalledWith('添加账号组失败')
    })

    it('网络异常时返回 null 并 message.error', async () => {
      mockService.addGameSignAccountApiToolsSignAccountAddPost.mockRejectedValue(
        new Error('Network error')
      )
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      const result = await api.addAccount()
      expect(result).toBeNull()
      expect(messageSpy.error).toHaveBeenCalledWith('添加账号组失败')
      expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('Network error'))
    })
  })

  describe('updateAccount', () => {
    it('成功时静默返回（无 message.success）', async () => {
      mockService.updateGameSignAccountApiToolsSignAccountUpdatePost.mockResolvedValue({
        code: 200,
        status: 'ok',
        message: '',
      })
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      await api.updateAccount('acc-1', {
        Name: '新名',
        Enabled: true,
        MiyousheToken: 'tok',
        KuroToken: '',
        SklandToken: '',
      })
      expect(logger.info).toHaveBeenCalledWith('账号组更新成功')
      // updateAccount 不主动 message.success，由调用方决定 UI 反馈
      expect(messageSpy.success).not.toHaveBeenCalled()
    })

    it('code !== 200 时抛出错误（调用方可捕获并回滚）', async () => {
      mockService.updateGameSignAccountApiToolsSignAccountUpdatePost.mockResolvedValue({
        code: 500,
        status: 'error',
        message: '字段不合法',
      })
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      await expect(
        api.updateAccount('acc-1', {
          Name: 'x',
          Enabled: true,
          MiyousheToken: '',
          KuroToken: '',
          SklandToken: '',
        })
      ).rejects.toThrow('字段不合法')
      expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('字段不合法'))
    })

    it('网络异常时抛出错误（调用方可捕获并回滚）', async () => {
      mockService.updateGameSignAccountApiToolsSignAccountUpdatePost.mockRejectedValue(
        new Error('Timeout')
      )
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      await expect(
        api.updateAccount('acc-1', {
          Name: 'x',
          Enabled: true,
          MiyousheToken: '',
          KuroToken: '',
          SklandToken: '',
        })
      ).rejects.toThrow('Timeout')
      expect(logger.error).toHaveBeenCalledWith(expect.stringContaining('Timeout'))
    })
  })

  describe('deleteAccount', () => {
    it('成功时 message.success', async () => {
      mockService.deleteGameSignAccountApiToolsSignAccountDeletePost.mockResolvedValue({
        code: 200,
        status: 'ok',
        message: '',
      })
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      await api.deleteAccount('acc-1')
      expect(messageSpy.success).toHaveBeenCalledWith('账号组已删除')
    })

    it('code !== 200 时抛出错误（调用方可保持 UI 状态）', async () => {
      mockService.deleteGameSignAccountApiToolsSignAccountDeletePost.mockResolvedValue({
        code: 500,
        status: 'error',
        message: '账号不存在',
      })
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      await expect(api.deleteAccount('acc-1')).rejects.toThrow('账号不存在')
      expect(messageSpy.error).toHaveBeenCalledWith('删除账号组失败')
    })

    it('网络异常时抛出错误', async () => {
      mockService.deleteGameSignAccountApiToolsSignAccountDeletePost.mockRejectedValue(
        new Error('Connection refused')
      )
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      await expect(api.deleteAccount('acc-1')).rejects.toThrow('Connection refused')
      expect(messageSpy.error).toHaveBeenCalledWith('删除账号组失败')
    })
  })

  describe('loading 状态', () => {
    it('addAccount 期间 loading=true，结束后 loading=false', async () => {
      let resolveFn!: (v: any) => void
      mockService.addGameSignAccountApiToolsSignAccountAddPost.mockReturnValue(
        new Promise(resolve => {
          resolveFn = resolve
        })
      )
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      const promise = api.addAccount()
      expect(api.loading.value).toBe(true)
      resolveFn({ code: 200, accountId: 'x', data: {} })
      await promise
      expect(api.loading.value).toBe(false)
    })

    it('deleteAccount 期间 loading=true', async () => {
      let resolveFn!: (v: any) => void
      mockService.deleteGameSignAccountApiToolsSignAccountDeletePost.mockReturnValue(
        new Promise(resolve => {
          resolveFn = resolve
        })
      )
      const { useGameSignAccountApi } = await loadComposable()
      const api = useGameSignAccountApi()
      const promise = api.deleteAccount('acc-1')
      expect(api.loading.value).toBe(true)
      resolveFn({ code: 200, status: 'ok', message: '' })
      await promise
      expect(api.loading.value).toBe(false)
    })
  })
})

/**
 * Lane 8：账号 CRUD 回滚契约测试。
 *
 * 这些测试不挂载 TabGameSign.vue，而是验证"快照-修改-失败回滚"的契约模式：
 * 1. handleAddAccount 失败时：本地数组移除新增项 + 后端清理
 * 2. handleAccountFieldSave 失败时：本地恢复旧值
 * 3. handleEditModalOk 失败时：本地恢复旧值 + 保留 editingAccount 输入
 *
 * 通过直接驱动 useGameSignAccountApi + 模拟 accounts 数组来验证。
 */
describe('Lane 8 账号 CRUD 回滚契约', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('window', {
      electronAPI: { getLogger: () => logger },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('addAccount 后 updateAccount 失败：本地移除新增项并调用 deleteAccount 清理', async () => {
    // 模拟 TabGameSign.vue 的 handleAddAccount 流程
    mockService.addGameSignAccountApiToolsSignAccountAddPost.mockResolvedValue({
      code: 200,
      status: 'ok',
      message: '',
      accountId: 'acc-new',
      data: { Name: '用户' },
    })
    mockService.updateGameSignAccountApiToolsSignAccountUpdatePost.mockResolvedValue({
      code: 500,
      status: 'error',
      message: '初始化失败',
    })
    mockService.deleteGameSignAccountApiToolsSignAccountDeletePost.mockResolvedValue({
      code: 200,
      status: 'ok',
      message: '',
    })

    const { useGameSignAccountApi } = await loadComposable()
    const api = useGameSignAccountApi()
    const accounts: any[] = []

    // 复刻 handleAddAccount 的核心逻辑
    const result = await api.addAccount()
    expect(result).not.toBeNull()
    const createdUid = result!.accountId
    const newAccount = { uid: createdUid, Name: '用户 1' }
    accounts.push(newAccount)
    const pushedIndex = accounts.length - 1

    try {
      await api.updateAccount(createdUid, {
        Name: '用户 1',
        Enabled: true,
        MiyousheToken: '',
        KuroToken: '',
        SklandToken: '',
      })
    } catch {
      // 回滚本地
      if (accounts[pushedIndex]?.uid === createdUid) {
        accounts.splice(pushedIndex, 1)
      }
      // 清理后端
      await api.deleteAccount(createdUid)
    }

    expect(accounts).toHaveLength(0)
    expect(mockService.deleteGameSignAccountApiToolsSignAccountDeletePost).toHaveBeenCalledWith({
      accountId: 'acc-new',
    })
  })

  it('field save 失败：本地恢复到旧值快照', async () => {
    // 模拟 TabGameSign.vue 的 handleAccountFieldSave 流程
    mockService.updateGameSignAccountApiToolsSignAccountUpdatePost.mockResolvedValue({
      code: 500,
      status: 'error',
      message: '字段非法',
    })

    const { useGameSignAccountApi } = await loadComposable()
    const api = useGameSignAccountApi()
    const accounts = ref([{ uid: 'acc-1', Name: '原名', Enabled: true, MiyousheToken: 'old' }])

    // 模拟 v-model 已修改本地值
    const modifiedAccount = { ...accounts.value[0], Name: '新名' }

    // 复刻 handleAccountFieldSave 的核心逻辑
    const idx = accounts.value.findIndex(a => a.uid === modifiedAccount.uid)
    expect(idx).toBe(0)
    const snapshot = { ...accounts.value[idx] }
    try {
      await api.updateAccount(modifiedAccount.uid, {
        Name: modifiedAccount.Name,
        Enabled: modifiedAccount.Enabled,
        MiyousheToken: modifiedAccount.MiyousheToken,
        KuroToken: '',
        SklandToken: '',
      })
      // 成功时才提交
      accounts.value[idx] = { ...modifiedAccount }
    } catch {
      // 失败：回滚本地状态到旧值
      accounts.value[idx] = snapshot
    }

    expect(accounts.value[0].Name).toBe('原名')
  })

  it('editModalOk 失败：本地恢复旧值，但 editingAccount 保留用户输入', async () => {
    // 模拟 TabGameSign.vue 的 handleEditModalOk 流程
    mockService.updateGameSignAccountApiToolsSignAccountUpdatePost.mockResolvedValue({
      code: 500,
      status: 'error',
      message: '保存失败',
    })

    const { useGameSignAccountApi } = await loadComposable()
    const api = useGameSignAccountApi()
    const accounts = ref([
      {
        uid: 'acc-1',
        Name: '原用户',
        Enabled: true,
        MiyousheToken: 'old-token',
        KuroToken: '',
        SklandToken: '',
      },
    ])
    const editingAccount = ref({
      uid: 'acc-1',
      Name: '原用户',
      Enabled: true,
      MiyousheToken: 'new-token-input-by-user',
      KuroToken: '',
      SklandToken: '',
    })

    // 复刻 handleEditModalOk 的核心逻辑
    const idx = accounts.value.findIndex(a => a.uid === editingAccount.value.uid)
    expect(idx).toBe(0)
    const snapshot = { ...accounts.value[idx] }
    let modalClosed = false
    try {
      await api.updateAccount(editingAccount.value.uid, {
        Name: editingAccount.value.Name,
        Enabled: editingAccount.value.Enabled,
        MiyousheToken: editingAccount.value.MiyousheToken,
        KuroToken: editingAccount.value.KuroToken,
        SklandToken: editingAccount.value.SklandToken,
      })
      accounts.value[idx] = { ...editingAccount.value }
      modalClosed = true
    } catch {
      // 失败：恢复本地状态，但保留 editingAccount 中的用户输入
      accounts.value[idx] = snapshot
      // 不关闭模态框，让用户可以重试
    }

    // 本地 accounts 已回滚
    expect(accounts.value[0].MiyousheToken).toBe('old-token')
    // 模态框保持打开
    expect(modalClosed).toBe(false)
    // editingAccount 保留用户输入（可重试）
    expect(editingAccount.value.MiyousheToken).toBe('new-token-input-by-user')
  })

  it('deleteAccount 失败：本地 accounts 不被修改（先调 API 再删本地）', async () => {
    // 模拟 TabGameSign.vue 的 handleDeleteAccount 流程
    mockService.deleteGameSignAccountApiToolsSignAccountDeletePost.mockResolvedValue({
      code: 500,
      status: 'error',
      message: '删除失败',
    })

    const { useGameSignAccountApi } = await loadComposable()
    const api = useGameSignAccountApi()
    const accounts = ref([
      { uid: 'acc-1', Name: '用户A' },
      { uid: 'acc-2', Name: '用户B' },
    ])

    const targetUid = 'acc-1'
    let localDeleted = false

    // 复刻 handleDeleteAccount 的核心逻辑：先 API 后本地
    try {
      await api.deleteAccount(targetUid)
      // 成功后才更新本地
      accounts.value = accounts.value.filter(a => a.uid !== targetUid)
      localDeleted = true
    } catch {
      // 失败：本地不修改
    }

    expect(localDeleted).toBe(false)
    expect(accounts.value).toHaveLength(2)
    expect(accounts.value[0].uid).toBe('acc-1')
  })
})

// 引入 ref 用于上面的测试
import { ref } from 'vue'
