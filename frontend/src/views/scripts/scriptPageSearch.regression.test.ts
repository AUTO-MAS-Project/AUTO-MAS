import { describe, expect, it, vi } from 'vitest'
import {
  buildScriptSearchResult,
  createScriptSearchKeyboardController,
  getAdjacentSearchMatchKey,
  getScriptSearchEnterDirection,
  getScriptSearchMatchKey,
  getUserSearchMatchKey,
  isEditableSearchTarget,
  isKeyboardEventComposing,
  isScriptSearchShortcut,
  reconcileActiveSearchMatchKey,
  type ScriptSearchMatch,
} from './scriptPageSearch'

/** 与 scriptPageSearch 内部 ScriptSearchRecord 结构兼容的本地类型(源模块未导出该接口)。 */
interface SearchRecord {
  id?: unknown
  name?: unknown
  type?: unknown
  displayName?: unknown
  available?: unknown
  config?: unknown
  users?: readonly unknown[]
}

/**
 * 回归测试补充集：覆盖 IME、可编辑目标边界、Enter 方向、循环定位、
 * 匹配计数、折叠展开后保持当前匹配、过滤不修改原数组、无结果、Esc 关闭、
 * 监听器重复绑定幂等。与 scriptPageSearch.test.ts 互补，使用独立数据集。
 */

interface KeyboardEventOptions {
  ctrlKey?: boolean
  metaKey?: boolean
  altKey?: boolean
  shiftKey?: boolean
  isComposing?: boolean
  keyCode?: number
  target?: EventTarget | null
}

const createKeyboardEvent = (key: string, options: KeyboardEventOptions = {}) =>
  ({
    key,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    isComposing: false,
    keyCode: 0,
    target: null,
    defaultPrevented: false,
    preventDefault: vi.fn(),
    ...options,
  }) as unknown as KeyboardEvent

const createDispatchedKeyboardEvent = (key: string, options: KeyboardEventOptions = {}) => {
  const event = new Event('keydown', { cancelable: true })
  Object.defineProperties(event, {
    key: { value: key },
    ctrlKey: { value: options.ctrlKey ?? false },
    metaKey: { value: options.metaKey ?? false },
    altKey: { value: options.altKey ?? false },
    shiftKey: { value: options.shiftKey ?? false },
    isComposing: { value: options.isComposing ?? false },
    keyCode: { value: options.keyCode ?? 0 },
  })
  return event
}

const makeMatch = (key: string): ScriptSearchMatch => ({
  key,
  kind: 'script',
  scriptId: key.replace('script:', ''),
})

describe('scriptPageSearch regression: IME composing 不拦截 Ctrl+F', () => {
  it('composition 状态下(isComposing=true)的 Ctrl+F 不打开搜索且不阻止默认行为', () => {
    const open = vi.fn()
    const controller = createScriptSearchKeyboardController({
      isActive: () => true,
      isOpen: () => false,
      open,
      close: vi.fn(),
    })
    const composingFind = createKeyboardEvent('f', { ctrlKey: true, isComposing: true })

    controller.handleKeydown(composingFind)

    expect(open).not.toHaveBeenCalled()
    expect(composingFind.preventDefault).not.toHaveBeenCalled()
  })

  it('keyCode 229(部分 IME 兼容回退)同样视为 composing 并放行', () => {
    expect(isKeyboardEventComposing({ isComposing: false, keyCode: 229 })).toBe(true)
    expect(isKeyboardEventComposing({ isComposing: false, keyCode: 0 })).toBe(false)
    expect(isKeyboardEventComposing({ isComposing: true, keyCode: 0 })).toBe(true)

    const open = vi.fn()
    const controller = createScriptSearchKeyboardController({
      isActive: () => true,
      isOpen: () => false,
      open,
      close: vi.fn(),
    })
    const imeFallbackFind = createKeyboardEvent('f', { ctrlKey: true, keyCode: 229 })

    controller.handleKeydown(imeFallbackFind)

    expect(open).not.toHaveBeenCalled()
  })
})

describe('scriptPageSearch regression: isEditableSearchTarget 边界', () => {
  it('null/非对象目标与普通非可编辑元素均返回 false', () => {
    expect(isEditableSearchTarget(null)).toBe(false)
    // 实现内部以 typeof target !== 'object' 拒绝非对象,这里用 cast 验证该守卫
    expect(isEditableSearchTarget(undefined as unknown as EventTarget)).toBe(false)
    expect(isEditableSearchTarget('input' as unknown as EventTarget)).toBe(false)

    const plainDiv = { tagName: 'DIV', isContentEditable: false } as unknown as EventTarget
    expect(isEditableSearchTarget(plainDiv)).toBe(false)
  })

  it('INPUT/TEXTAREA 与 contenteditable=true 返回 true,contenteditable=false 返回 false', () => {
    const inputLower = { tagName: 'input', isContentEditable: false } as unknown as EventTarget
    const textarea = { tagName: 'TEXTAREA', isContentEditable: false } as unknown as EventTarget
    expect(isEditableSearchTarget(inputLower)).toBe(true)
    expect(isEditableSearchTarget(textarea)).toBe(true)

    const editableDiv = {
      tagName: 'DIV',
      isContentEditable: true,
      closest: (_selector: string) => null,
    } as unknown as EventTarget
    expect(isEditableSearchTarget(editableDiv)).toBe(true)

    // 模拟 closest 命中 contenteditable=true 祖先(返回真值)
    const closestTrue = {
      tagName: 'DIV',
      isContentEditable: false,
      closest: (_selector: string) => ({ tagName: 'DIV' }),
    } as unknown as EventTarget
    expect(isEditableSearchTarget(closestTrue)).toBe(true)

    // 模拟 closest 未命中(返回 null)
    const closestFalse = {
      tagName: 'DIV',
      isContentEditable: false,
      closest: (_selector: string) => null,
    } as unknown as EventTarget
    expect(isEditableSearchTarget(closestFalse)).toBe(false)
  })
})

describe('scriptPageSearch regression: Enter 导航方向', () => {
  it('Enter 下一项、Shift+Enter 上一项,非 Enter 与 composing Enter 均为 null', () => {
    expect(getScriptSearchEnterDirection(createKeyboardEvent('Enter'))).toBe(1)
    expect(getScriptSearchEnterDirection(createKeyboardEvent('Enter', { shiftKey: true }))).toBe(-1)
    expect(
      getScriptSearchEnterDirection(createKeyboardEvent('Enter', { isComposing: true }))
    ).toBeNull()
    expect(getScriptSearchEnterDirection(createKeyboardEvent('Enter', { keyCode: 229 }))).toBeNull()
    expect(getScriptSearchEnterDirection(createKeyboardEvent('a'))).toBeNull()
    expect(getScriptSearchEnterDirection(createKeyboardEvent('Escape'))).toBeNull()
  })

  it('isScriptSearchShortcut 仅识别 Ctrl/Meta+F 且排除 Alt', () => {
    expect(isScriptSearchShortcut(createKeyboardEvent('f', { ctrlKey: true }))).toBe(true)
    expect(isScriptSearchShortcut(createKeyboardEvent('F', { metaKey: true }))).toBe(true)
    expect(isScriptSearchShortcut(createKeyboardEvent('f', { ctrlKey: true, altKey: true }))).toBe(
      false
    )
    expect(isScriptSearchShortcut(createKeyboardEvent('f'))).toBe(false)
    expect(isScriptSearchShortcut(createKeyboardEvent('g', { ctrlKey: true }))).toBe(false)
  })
})

describe('scriptPageSearch regression: 循环定位 wraparound', () => {
  const matches: ScriptSearchMatch[] = [
    makeMatch('script:a'),
    makeMatch('script:b'),
    makeMatch('script:c'),
  ]

  it('到达最后一项后 Enter 回到第一项;第一项 Shift+Enter 回到最后一项', () => {
    expect(getAdjacentSearchMatchKey(matches, 'script:a', 1)).toBe('script:b')
    expect(getAdjacentSearchMatchKey(matches, 'script:b', 1)).toBe('script:c')
    expect(getAdjacentSearchMatchKey(matches, 'script:c', 1)).toBe('script:a')
    expect(getAdjacentSearchMatchKey(matches, 'script:a', -1)).toBe('script:c')
    expect(getAdjacentSearchMatchKey(matches, 'script:c', -1)).toBe('script:b')
  })

  it('空 matches 返回空串;currentKey 不存在时按方向落到首/末项', () => {
    expect(getAdjacentSearchMatchKey([], 'script:a', 1)).toBe('')
    expect(getAdjacentSearchMatchKey(matches, 'missing', 1)).toBe('script:a')
    expect(getAdjacentSearchMatchKey(matches, 'missing', -1)).toBe('script:c')
  })
})

describe('scriptPageSearch regression: 匹配计数与无结果状态', () => {
  const scripts: SearchRecord[] = [
    {
      id: 's-endfield',
      name: 'Endfield Daily',
      type: 'MaaFW',
      config: { Info: { ProjectLabel: 'Endfield' } },
      users: [
        { id: 'u-1', name: 'instance-1', Info: { Name: 'Celie', Server: 'Official' } },
        { id: 'u-2', name: 'instance-2', Info: { Name: 'Vila', Server: 'Bilibili' } },
      ],
    },
    {
      id: 's-ark',
      name: 'Arknight Daily',
      type: 'M9A',
      available: true,
      users: [{ id: 'u-3', name: 'instance-3', Info: { Name: 'Amiya', Server: 'Official' } }],
    },
  ]

  it('匹配计数同时包含 script 命中与 user 命中', () => {
    // "instance" 命中三个 user,但两个 script 自身不命中
    const userOnly = buildScriptSearchResult(scripts, 'instance')
    expect(userOnly.matches).toHaveLength(3)
    expect(userOnly.matches.every(match => match.kind === 'user')).toBe(true)
    expect(userOnly.scripts).toHaveLength(2)

    // "official" 命中两个 user(Server=Official),script 自身不命中
    const serverMatch = buildScriptSearchResult(scripts, 'official')
    expect(serverMatch.matches).toHaveLength(2)
  })

  it('无匹配查询返回空 matches、空 scripts 且不抛错', () => {
    const result = buildScriptSearchResult(scripts, 'zzzz-no-such-keyword')
    expect(result.matches).toEqual([])
    expect(result.scripts).toEqual([])
  })
})

describe('scriptPageSearch regression: 折叠展开后保持当前匹配', () => {
  it('reconcileActiveSearchMatchKey 在数据变更后:命中保留、未命中回退首项、空回退空串', () => {
    const collapsed: ScriptSearchMatch[] = [makeMatch('script:a'), makeMatch('script:b')]
    // 当前匹配仍存在 → 保留
    expect(reconcileActiveSearchMatchKey(collapsed, 'script:b')).toBe('script:b')

    // 模拟展开后新增了一项,当前匹配仍存在 → 保留
    const expanded: ScriptSearchMatch[] = [
      makeMatch('script:a'),
      makeMatch('script:b'),
      makeMatch('script:c'),
    ]
    expect(reconcileActiveSearchMatchKey(expanded, 'script:b')).toBe('script:b')

    // 当前匹配被删除(例如折叠后该用户不再匹配)→ 回退到第一项
    const shrunk: ScriptSearchMatch[] = [makeMatch('script:a'), makeMatch('script:c')]
    expect(reconcileActiveSearchMatchKey(shrunk, 'script:b')).toBe('script:a')

    // 空列表 → 空串
    expect(reconcileActiveSearchMatchKey([], 'script:b')).toBe('')
  })
})

describe('scriptPageSearch regression: 过滤不修改原数组(拖拽顺序可恢复)', () => {
  it('buildScriptSearchResult 不修改传入的 scripts 数组引用与顺序', () => {
    const scripts: SearchRecord[] = [
      { id: 's-1', name: 'Alpha', type: 'M9A', users: [] },
      { id: 's-2', name: 'Beta', type: 'MaaFW', users: [] },
      { id: 's-3', name: 'Gamma', type: 'SRC', users: [] },
    ]
    const originalIds = scripts.map(script => script.id)

    // 过滤命中 Beta
    const filtered = buildScriptSearchResult(scripts, 'beta')
    expect(filtered.scripts.map(script => script.id)).toEqual(['s-2'])

    // 清除过滤(空查询)后应返回与原数组相同的顺序
    const restored = buildScriptSearchResult(scripts, '   ')
    expect(restored.scripts.map(script => script.id)).toEqual(originalIds)
    // 原数组未被改动
    expect(scripts.map(script => script.id)).toEqual(originalIds)
    expect(scripts).toHaveLength(3)
  })
})

describe('scriptPageSearch regression: Esc 关闭搜索', () => {
  const createController = (openState: boolean) => {
    let open = openState
    const close = vi.fn(() => {
      open = false
    })
    const controller = createScriptSearchKeyboardController({
      isActive: () => true,
      isOpen: () => open,
      open: vi.fn(() => {
        open = true
      }),
      close,
    })
    return { controller, close }
  }

  it('打开状态下 Esc 调用 close 并阻止默认行为', () => {
    const { controller, close } = createController(true)
    const escape = createKeyboardEvent('Escape')

    controller.handleKeydown(escape)

    expect(close).toHaveBeenCalledOnce()
    expect(escape.preventDefault).toHaveBeenCalledOnce()
  })

  it('未打开状态下 Esc 不调用 close', () => {
    const { controller, close } = createController(false)
    controller.handleKeydown(createKeyboardEvent('Escape'))
    expect(close).not.toHaveBeenCalled()
  })
})

describe('scriptPageSearch regression: 监听器重复绑定幂等', () => {
  it('切换到新目标时旧目标不再触发,且旧 cleanup 不会误删当前监听', () => {
    const open = vi.fn()
    const controller = createScriptSearchKeyboardController({
      isActive: () => true,
      isOpen: () => false,
      open,
      close: vi.fn(),
    })
    const targetA = new EventTarget()
    const targetB = new EventTarget()

    const cleanupA = controller.bind(targetA)
    const cleanupB = controller.bind(targetB)

    // 当前生效的是 targetB
    targetA.dispatchEvent(createDispatchedKeyboardEvent('f', { ctrlKey: true }))
    targetB.dispatchEvent(createDispatchedKeyboardEvent('f', { ctrlKey: true }))

    expect(open).toHaveBeenCalledTimes(1)

    // 旧 cleanup 调用后不应移除 targetB 的监听(守卫条件生效)
    cleanupA()
    targetB.dispatchEvent(createDispatchedKeyboardEvent('f', { ctrlKey: true }))
    expect(open).toHaveBeenCalledTimes(2)

    // 正确 cleanup 移除监听
    cleanupB()
    targetB.dispatchEvent(createDispatchedKeyboardEvent('f', { ctrlKey: true }))
    expect(open).toHaveBeenCalledTimes(2)
  })

  it('unbind 后再 dispatch 不触发任何回调', () => {
    const open = vi.fn()
    const controller = createScriptSearchKeyboardController({
      isActive: () => true,
      isOpen: () => false,
      open,
      close: vi.fn(),
    })
    const target = new EventTarget()
    controller.bind(target)
    controller.unbind()

    target.dispatchEvent(createDispatchedKeyboardEvent('f', { ctrlKey: true }))
    expect(open).not.toHaveBeenCalled()
  })
})

describe('scriptPageSearch regression: 大量数据搜索性能', () => {
  it('1000 个脚本 × 10 个用户的搜索应在可接受时间内完成', () => {
    const scripts = Array.from({ length: 1000 }, (_, scriptIndex) => ({
      id: `script-${scriptIndex}`,
      name: `Script ${scriptIndex}`,
      type: scriptIndex % 3 === 0 ? 'M9A' : scriptIndex % 3 === 1 ? 'MaaFW' : 'SRC',
      users: Array.from({ length: 10 }, (_, userIndex) => ({
        id: `user-${scriptIndex}-${userIndex}`,
        name: `instance-${scriptIndex}-${userIndex}`,
        Info: {
          Name: `User ${scriptIndex}-${userIndex}`,
          Server: userIndex % 2 === 0 ? 'Official' : 'Bilibili',
        },
      })),
    }))

    const start = performance.now()
    const result = buildScriptSearchResult(scripts, 'User 500-5')
    const elapsed = performance.now() - start

    expect(result.scripts).toHaveLength(1)
    expect(result.matches).toHaveLength(1)
    // 性能基线：在普通 CI  runner 上应远低于 1000ms；若超出需调查
    expect(elapsed).toBeLessThan(1000)
  })

  it('空查询直接返回原数组副本，不进入匹配循环', () => {
    const scripts = Array.from({ length: 100 }, (_, i) => ({
      id: `script-${i}`,
      name: `Script ${i}`,
      type: 'M9A',
      users: [],
    }))

    const start = performance.now()
    const result = buildScriptSearchResult(scripts, '   ')
    const elapsed = performance.now() - start

    expect(result.scripts).toHaveLength(100)
    expect(result.matches).toHaveLength(0)
    expect(elapsed).toBeLessThan(100)
  })
})

describe('scriptPageSearch regression: match key 生成一致性', () => {
  it('script 与 user key 前缀稳定,确保 reconcile/adjacent 可匹配', () => {
    expect(getScriptSearchMatchKey('s-1')).toBe('script:s-1')
    expect(getUserSearchMatchKey('s-1', 'u-9')).toBe('user:s-1:u-9')

    const matches: ScriptSearchMatch[] = buildScriptSearchResult(
      [
        {
          id: 's-1',
          name: 'Alpha',
          type: 'M9A',
          users: [{ id: 'u-9', name: 'instance-9', Info: { Name: 'Nine' } }],
        },
      ],
      'alpha'
    ).matches

    // script 自身命中 → 含 script: 前缀 key
    expect(matches).toContainEqual({
      key: 'script:s-1',
      kind: 'script',
      scriptId: 's-1',
    })
  })
})

describe('scriptPageSearch regression: 旧插件脚本兼容', () => {
  it('缺少 config/Info/displayName 的旧插件脚本仍可被名称搜索命中', () => {
    const legacyScripts: SearchRecord[] = [
      { id: 'legacy-1', name: 'Old Plugin Script', type: 'M9A', users: [] },
      { id: 'legacy-2', name: 'Another Legacy', type: 'SRC', users: [] },
    ]

    const result = buildScriptSearchResult(legacyScripts, 'old')
    expect(result.scripts).toHaveLength(1)
    expect(result.scripts[0].id).toBe('legacy-1')
    expect(result.matches[0]).toEqual({
      key: 'script:legacy-1',
      kind: 'script',
      scriptId: 'legacy-1',
    })
  })

  it('旧插件用户仅含字符串字段仍可被搜索且不抛错', () => {
    const legacyScripts: SearchRecord[] = [
      {
        id: 'legacy-3',
        name: 'Legacy With Users',
        type: 'MaaFW',
        users: [
          { id: 'u-1', name: 'instance-legacy' },
          { id: 'u-2', name: 'instance-other', Info: { Server: 'Bilibili' } },
          null,
          'invalid-user',
        ],
      },
    ]

    // 脚本名称与用户均命中 "legacy"，应同时返回 script 与 user 匹配
    const result = buildScriptSearchResult(legacyScripts, 'legacy')
    expect(result.scripts).toHaveLength(1)
    expect(result.matches).toHaveLength(2)
    expect(result.matches.some(match => match.kind === 'user')).toBe(true)

    // 仅命中用户 Server 字段，验证非对象/异常用户不会抛错
    const serverResult = buildScriptSearchResult(legacyScripts, 'b服')
    expect(serverResult.scripts).toHaveLength(1)
    expect(serverResult.matches).toHaveLength(1)
    expect(serverResult.matches[0].kind).toBe('user')
  })

  it('id 非字符串的旧插件脚本使用 index fallback 生成 key', () => {
    const legacyScripts: SearchRecord[] = [
      { name: 'No Id Script', type: 'M9A', users: [] },
      { id: 12345, name: 'Numeric Id Script', type: 'SRC', users: [] },
    ]

    const result = buildScriptSearchResult(legacyScripts, 'script')
    expect(result.scripts).toHaveLength(2)
    expect(result.matches[0].key).toBe('script:index-0')
    expect(result.matches[1].key).toBe('script:12345')
  })
})
