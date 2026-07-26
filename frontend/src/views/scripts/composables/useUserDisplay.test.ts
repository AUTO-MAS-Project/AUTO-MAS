import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * useUserDisplay deterministic 测试集
 *
 * 覆盖目标：
 * - 纯函数：服务器标签颜色/名称、账号/密码标签可见性、状态标签解析
 * - 状态：expandedUserIds/expandedUserPasswords 在 click 后的 Set 增减
 * - 显示文本：getUserIdDisplayText / getPasswordDisplayText 随展开状态切换
 * - 副作用：clipboard.writeText 成功/失败时分别触发 success/error message
 *
 * 不依赖 @vue/test-utils，仅以 vitest + 全局 mock 验证 composable 契约。
 */

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const messageMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('ant-design-vue', () => ({
  message: messageMocks,
}))

const clipboardMocks = vi.hoisted(() => ({
  writeText: vi.fn(),
}))

beforeEach(() => {
  vi.resetModules()
  vi.clearAllMocks()

  // node 环境下 navigator 不存在，需要直接 stub 顶层 navigator 全局
  // （useUserDisplay 源码使用 navigator.clipboard.writeText，不走 window.navigator）
  vi.stubGlobal('navigator', {
    clipboard: {
      writeText: clipboardMocks.writeText,
    },
  })

  vi.stubGlobal('window', {
    electronAPI: {
      getLogger: () => logger,
    },
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

const loadModule = async () => {
  return (await import('./useUserDisplay')) as typeof import('./useUserDisplay')
}

describe('useUserDisplay: 服务器标签纯函数', () => {
  it('getServerTagColor 覆盖 Official/Bilibili/YoStar*/txwy 与 CN/OVERSEA 分支', async () => {
    const { getServerTagColor } = await loadModule()

    expect(getServerTagColor('Official')).toBe('blue')
    expect(getServerTagColor('Bilibili')).toBe('purple')
    expect(getServerTagColor('YoStarEN')).toBe('green')
    expect(getServerTagColor('YoStarJP')).toBe('red')
    expect(getServerTagColor('YoStarKR')).toBe('orange')
    expect(getServerTagColor('txwy')).toBe('gold')
    expect(getServerTagColor('CN-Official')).toBe('blue')
    expect(getServerTagColor('CN-Bilibili')).toBe('purple')
    expect(getServerTagColor('VN-Official')).toBe('cyan')
    expect(getServerTagColor('OVERSEA-America')).toBe('green')
    expect(getServerTagColor('OVERSEA-Asia')).toBe('orange')
    expect(getServerTagColor('OVERSEA-Europe')).toBe('geekblue')
    expect(getServerTagColor('OVERSEA-TWHKMO')).toBe('gold')
    expect(getServerTagColor('Unknown')).toBe('gray')
    expect(getServerTagColor('')).toBe('gray')
  })

  it('getServerDisplayName 返回中文短名，未知 server 回退原值或"未知"', async () => {
    const { getServerDisplayName } = await loadModule()

    expect(getServerDisplayName('Official')).toBe('官服')
    expect(getServerDisplayName('Bilibili')).toBe('B服')
    expect(getServerDisplayName('YoStarEN')).toBe('国际服')
    expect(getServerDisplayName('YoStarJP')).toBe('日服')
    expect(getServerDisplayName('YoStarKR')).toBe('韩服')
    expect(getServerDisplayName('txwy')).toBe('繁中服')
    expect(getServerDisplayName('CN-Official')).toBe('官服')
    expect(getServerDisplayName('CN-Bilibili')).toBe('B服')
    expect(getServerDisplayName('VN-Official')).toBe('越南服')
    expect(getServerDisplayName('OVERSEA-America')).toBe('美服')
    expect(getServerDisplayName('OVERSEA-Asia')).toBe('亚服')
    expect(getServerDisplayName('OVERSEA-Europe')).toBe('欧服')
    expect(getServerDisplayName('OVERSEA-TWHKMO')).toBe('港澳台服')
    expect(getServerDisplayName('CustomServer')).toBe('CustomServer')
    expect(getServerDisplayName('')).toBe('未知')
  })
})

describe('useUserDisplay: shouldShow* 标签可见性判定', () => {
  it('shouldShowServerTag 在 Server 或 Resource 字段有非空值时为 true', async () => {
    const { shouldShowServerTag } = await loadModule()

    expect(shouldShowServerTag({ Info: { Server: 'Official' } })).toBe(true)
    expect(shouldShowServerTag({ Info: { Resource: '官服' } })).toBe(true)
    expect(shouldShowServerTag({ Info: { Server: '' } })).toBe(false)
    expect(shouldShowServerTag({ Info: { Server: null } })).toBe(false)
    expect(shouldShowServerTag({ Info: {} })).toBe(false)
    expect(shouldShowServerTag({})).toBe(false)
    expect(shouldShowServerTag(null as any)).toBe(false)
  })

  it('shouldShowUserIdTag 仅在 Info.Id 有非空值时为 true', async () => {
    const { shouldShowUserIdTag } = await loadModule()

    expect(shouldShowUserIdTag({ Info: { Id: '12345' } })).toBe(true)
    expect(shouldShowUserIdTag({ Info: { Id: '' } })).toBe(false)
    expect(shouldShowUserIdTag({ Info: {} })).toBe(false)
    expect(shouldShowUserIdTag({})).toBe(false)
  })

  it('shouldShowPasswordTag 仅检查 Password 字段存在性（含空串），不要求非空', async () => {
    const { shouldShowPasswordTag } = await loadModule()

    expect(shouldShowPasswordTag({ Info: { Password: 'secret' } })).toBe(true)
    // 空 Password 也算"存在"，触发标签渲染（文案由 getUserIdDisplayText 决定）
    expect(shouldShowPasswordTag({ Info: { Password: '' } })).toBe(true)
    expect(shouldShowPasswordTag({ Info: {} })).toBe(false)
    expect(shouldShowPasswordTag({})).toBe(false)
  })
})

describe('useUserDisplay: 服务器配色/名称 fallback 到 MaaEnd Resource', () => {
  it('getUserServerTagColor 在 Server 缺失时回退到 blue（MaaEnd Resource 配色）', async () => {
    const { getUserServerTagColor } = await loadModule()

    expect(getUserServerTagColor({ Info: { Server: 'Bilibili' } })).toBe('purple')
    expect(getUserServerTagColor({ Info: {} })).toBe('blue')
    expect(getUserServerTagColor({ Info: { Server: '' } })).toBe('blue')
  })

  it('getUserServerDisplayName 在 Server 缺失时回退到 Resource 字段或"官服"', async () => {
    const { getUserServerDisplayName } = await loadModule()

    expect(getUserServerDisplayName({ Info: { Server: 'Official' } })).toBe('官服')
    expect(getUserServerDisplayName({ Info: {} })).toBe('官服')
    expect(getUserServerDisplayName({ Info: { Resource: '美服' } })).toBe('美服')
    // Server 优先于 Resource
    expect(getUserServerDisplayName({ Info: { Server: 'Bilibili', Resource: '美服' } })).toBe('B服')
  })

  it('getUserIdentityTagColor 在 Server 缺失时同样回退到 blue', async () => {
    const { getUserIdentityTagColor } = await loadModule()

    expect(getUserIdentityTagColor({ Info: { Server: 'YoStarJP' } })).toBe('red')
    expect(getUserIdentityTagColor({ Info: {} })).toBe('blue')
  })
})

describe('useUserDisplay: 状态标签解析', () => {
  it('getUserStatusTags 优先使用 schema 中 type=tag 字段，否则回退到 Info.Tag', async () => {
    const { getUserStatusTags } = await loadModule()

    // schema groups 形式
    const userWithSchemaGroups = {
      Info: { Tag: JSON.stringify([{ text: '人工排查未通过', color: 'orange' }]) },
      schema: {
        groups: [
          {
            fields: [
              {
                type: 'tag',
                key: 'Tag',
              },
            ],
          },
        ],
      },
      config: {
        Tag: JSON.stringify([{ text: 'SchemaTag', color: 'green' }]),
      },
    }
    expect(getUserStatusTags(userWithSchemaGroups)).toEqual([{ text: 'SchemaTag', color: 'green' }])

    // schema object 形式：field.key 由 schema 顶层 key 决定，需与 config 路径一致
    const userWithSchemaObject = {
      Info: {},
      schema: {
        Tag: { type: 'tag', name: 'Tag' },
      },
      config: {
        Tag: JSON.stringify([{ text: 'ObjectTag', color: 'gold' }]),
      },
    }
    expect(getUserStatusTags(userWithSchemaObject)).toEqual([{ text: 'ObjectTag', color: 'gold' }])

    // 无 schema 时回退到 Info.Tag
    const userWithoutSchema = {
      Info: { Tag: JSON.stringify([{ text: 'FallbackTag', color: 'red' }]) },
    }
    expect(getUserStatusTags(userWithoutSchema)).toEqual([{ text: 'FallbackTag', color: 'red' }])

    // 完全无标签
    expect(getUserStatusTags({ Info: {} })).toEqual([])
    expect(getUserStatusTags({})).toEqual([])
  })

  it('isPassCheckTag 仅识别 text="人工排查未通过" 的标签', async () => {
    const { isPassCheckTag } = await loadModule()

    expect(isPassCheckTag({ text: '人工排查未通过', color: 'orange' })).toBe(true)
    expect(isPassCheckTag({ text: '人工排查未通过' })).toBe(true)
    expect(isPassCheckTag({ text: '其他状态', color: 'green' })).toBe(false)
    expect(isPassCheckTag({} as any)).toBe(false)
  })

  it('shouldShowStatusTags 在有标签时为 true，无标签时为 false', async () => {
    const { shouldShowStatusTags } = await loadModule()

    expect(
      shouldShowStatusTags({ Info: { Tag: JSON.stringify([{ text: '运行中', color: 'green' }]) } })
    ).toBe(true)
    expect(shouldShowStatusTags({ Info: {} })).toBe(false)
    expect(shouldShowStatusTags({})).toBe(false)
  })
})

describe('useUserDisplay: 账号/密码展开状态与剪贴板副作用', () => {
  it('handleUserIdClick 首次点击展开并复制账号；再次点击折叠', async () => {
    const { useUserDisplay } = await loadModule()
    clipboardMocks.writeText.mockResolvedValue(undefined)

    const display = useUserDisplay()
    const user = { id: 'u-1', Info: { Id: 'account-123' } }

    await display.handleUserIdClick(user)
    expect(display.expandedUserIds.value!.has('u-1')).toBe(true)
    expect(clipboardMocks.writeText).toHaveBeenCalledWith('account-123')
    expect(messageMocks.success).toHaveBeenCalledWith('账号已复制到剪贴板')

    await display.handleUserIdClick(user)
    expect(display.expandedUserIds.value!.has('u-1')).toBe(false)
  })

  it('handleUserIdClick 在 Id 为空时仍切换展开状态但不调用 clipboard', async () => {
    const { useUserDisplay } = await loadModule()
    const display = useUserDisplay()
    const user = { id: 'u-empty', Info: {} }

    await display.handleUserIdClick(user)
    expect(display.expandedUserIds.value!.has('u-empty')).toBe(true)
    expect(clipboardMocks.writeText).not.toHaveBeenCalled()
    expect(messageMocks.success).not.toHaveBeenCalled()
  })

  it('handleUserIdClick 在 clipboard.writeText 抛错时显示 error', async () => {
    const { useUserDisplay } = await loadModule()
    clipboardMocks.writeText.mockRejectedValue(new Error('permission denied'))

    const display = useUserDisplay()
    const user = { id: 'u-err', Info: { Id: 'acc' } }

    await display.handleUserIdClick(user)
    expect(messageMocks.error).toHaveBeenCalledWith('复制失败')
  })

  it('handlePasswordClick 首次点击展开密码并复制；再次点击折叠', async () => {
    const { useUserDisplay } = await loadModule()
    clipboardMocks.writeText.mockResolvedValue(undefined)

    const display = useUserDisplay()
    const user = { id: 'u-pwd', Info: { Password: 'p@ssw0rd' } }

    await display.handlePasswordClick(user)
    expect(display.expandedUserPasswords.value!.has('u-pwd')).toBe(true)
    expect(clipboardMocks.writeText).toHaveBeenCalledWith('p@ssw0rd')
    expect(messageMocks.success).toHaveBeenCalledWith('密码已复制到剪贴板')

    await display.handlePasswordClick(user)
    expect(display.expandedUserPasswords.value!.has('u-pwd')).toBe(false)
  })

  it('handlePasswordClick 在 Password 缺失时仍切换展开状态但不调用 clipboard', async () => {
    const { useUserDisplay } = await loadModule()
    const display = useUserDisplay()
    const user = { id: 'u-no-pwd', Info: {} }

    await display.handlePasswordClick(user)
    expect(display.expandedUserPasswords.value!.has('u-no-pwd')).toBe(true)
    expect(clipboardMocks.writeText).not.toHaveBeenCalled()
  })

  it('handlePasswordClick 在 clipboard.writeText 抛错时显示 error', async () => {
    const { useUserDisplay } = await loadModule()
    clipboardMocks.writeText.mockRejectedValue(new Error('denied'))

    const display = useUserDisplay()
    const user = { id: 'u-pwd-err', Info: { Password: 'p' } }

    await display.handlePasswordClick(user)
    expect(messageMocks.error).toHaveBeenCalledWith('复制失败')
  })
})

describe('useUserDisplay: 显示文本随展开状态切换', () => {
  it('getUserIdDisplayText 折叠时返回"账号"，展开时显示实际账号或"未设置"', async () => {
    const { useUserDisplay } = await loadModule()
    const display = useUserDisplay()
    const user = { id: 'u-1', Info: { Id: 'acc-001' } }

    expect(display.getUserIdDisplayText(user)).toBe('账号')
    display.expandedUserIds.value!.add('u-1')
    expect(display.getUserIdDisplayText(user)).toBe('账号: acc-001')

    const emptyUser = { id: 'u-2', Info: {} }
    display.expandedUserIds.value!.add('u-2')
    expect(display.getUserIdDisplayText(emptyUser)).toBe('账号: 未设置')
  })

  it('getPasswordDisplayText 折叠时返回"密码"，展开时显示实际密码或"未设置"', async () => {
    const { useUserDisplay } = await loadModule()
    const display = useUserDisplay()
    const user = { id: 'u-1', Info: { Password: 'secret' } }

    expect(display.getPasswordDisplayText(user)).toBe('密码')
    display.expandedUserPasswords.value!.add('u-1')
    expect(display.getPasswordDisplayText(user)).toBe('密码: secret')

    const emptyUser = { id: 'u-2', Info: {} }
    display.expandedUserPasswords.value!.add('u-2')
    expect(display.getPasswordDisplayText(emptyUser)).toBe('密码: 未设置')
  })

  it('expandedUserIds 与 expandedUserPasswords 状态相互独立', async () => {
    const { useUserDisplay } = await loadModule()
    const display = useUserDisplay()

    display.expandedUserIds.value!.add('u-1')
    display.expandedUserPasswords.value!.add('u-2')

    expect(display.expandedUserIds.value!.has('u-1')).toBe(true)
    expect(display.expandedUserIds.value!.has('u-2')).toBe(false)
    expect(display.expandedUserPasswords.value!.has('u-1')).toBe(false)
    expect(display.expandedUserPasswords.value!.has('u-2')).toBe(true)
  })
})
