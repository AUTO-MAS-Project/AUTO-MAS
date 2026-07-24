import { describe, expect, it, vi } from 'vitest'
import {
  buildScriptSearchResult,
  createScriptSearchFocusManager,
  createScriptSearchKeyboardController,
  filterScriptsBySearch,
  getAdjacentSearchMatchKey,
  getScriptSearchEnterDirection,
  getScriptSearchMatchKey,
  getUserSearchMatchKey,
  reconcileActiveSearchMatchKey,
} from './scriptPageSearch'

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

const editableTarget = (tagName: 'INPUT' | 'TEXTAREA') =>
  ({ tagName, isContentEditable: false }) as unknown as EventTarget

describe('script page filtering and match index', () => {
  const scripts = [
    {
      id: 'script-hsr',
      name: 'HSR Daily',
      type: 'MaaFW',
      displayName: '崩坏：星穹铁道',
      config: { Info: { ProjectLabel: 'HSR' } },
      users: [
        {
          id: 'user-alice',
          name: 'instance-alice',
          Info: {
            Name: 'Alice',
            Server: 'Official',
            Status: true,
            Notes: '仅在周末运行',
            Tag: JSON.stringify([{ text: '人工排查未通过', color: 'orange' }]),
          },
        },
      ],
    },
    {
      id: 'script-m9a',
      name: 'M9A Nightly',
      type: 'M9A',
      available: false,
      users: [
        {
          id: 'user-bob',
          name: 'instance-bob',
          Info: { Name: 'Bob', Server: 'Bilibili' },
        },
      ],
    },
  ]

  it('matches script names, visible types and user names without case sensitivity', () => {
    expect(filterScriptsBySearch(scripts, 'hsr')).toEqual([scripts[0]])
    expect(filterScriptsBySearch(scripts, 'maafw')).toEqual([scripts[0]])
    expect(filterScriptsBySearch(scripts, 'ALICE')).toEqual([scripts[0]])
    expect(filterScriptsBySearch(scripts, 'instance-BOB')).toEqual([scripts[1]])
  })

  it('matches Chinese server labels, visible tags and remarks', () => {
    expect(filterScriptsBySearch(scripts, '官服')).toEqual([scripts[0]])
    expect(filterScriptsBySearch(scripts, '人工排查')).toEqual([scripts[0]])
    expect(filterScriptsBySearch(scripts, '周末运行')).toEqual([scripts[0]])
    expect(filterScriptsBySearch(scripts, '未启用')).toEqual([scripts[1]])
    expect(filterScriptsBySearch(scripts, 'ｂ服')).toEqual([scripts[1]])
  })

  it('returns stable script/user matches and restores the full list for an empty query', () => {
    const scriptResult = buildScriptSearchResult(scripts, 'HSR')
    const userResult = buildScriptSearchResult(scripts, 'Alice')
    const emptyResult = buildScriptSearchResult(scripts, '  ')

    expect(scriptResult.matches).toEqual([
      {
        key: getScriptSearchMatchKey('script-hsr'),
        kind: 'script',
        scriptId: 'script-hsr',
      },
    ])
    expect(userResult.matches).toEqual([
      {
        key: getUserSearchMatchKey('script-hsr', 'user-alice'),
        kind: 'user',
        scriptId: 'script-hsr',
        userId: 'user-alice',
      },
    ])
    expect(emptyResult.scripts).toEqual(scripts)
    expect(emptyResult.matches).toEqual([])
  })

  it('keeps the active match stable and clamps safely after data deletion', () => {
    const matches = buildScriptSearchResult(scripts, 'i').matches
    const aliceKey = getUserSearchMatchKey('script-hsr', 'user-alice')
    const bobKey = getUserSearchMatchKey('script-m9a', 'user-bob')

    expect(reconcileActiveSearchMatchKey(matches, aliceKey)).toBe(aliceKey)
    expect(reconcileActiveSearchMatchKey(matches, 'deleted-user')).toBe(matches[0]?.key)
    expect(reconcileActiveSearchMatchKey([], bobKey)).toBe('')
  })

  it('wraps Enter and Shift+Enter navigation in both directions', () => {
    const matches = buildScriptSearchResult(scripts, 'i').matches
    const first = matches[0]?.key ?? ''
    const last = matches[matches.length - 1]?.key ?? ''

    expect(getAdjacentSearchMatchKey(matches, first, -1)).toBe(last)
    expect(getAdjacentSearchMatchKey(matches, last, 1)).toBe(first)
    expect(getScriptSearchEnterDirection(createKeyboardEvent('Enter'))).toBe(1)
    expect(getScriptSearchEnterDirection(createKeyboardEvent('Enter', { shiftKey: true }))).toBe(-1)
    expect(
      getScriptSearchEnterDirection(createKeyboardEvent('Enter', { isComposing: true }))
    ).toBeNull()
  })
})

describe('script page search keyboard controller', () => {
  const createController = (overrides: { active?: boolean; open?: boolean } = {}) => {
    let openState = overrides.open ?? false
    const open = vi.fn(() => {
      openState = true
    })
    const close = vi.fn(() => {
      openState = false
    })
    const controller = createScriptSearchKeyboardController({
      isActive: () => overrides.active ?? true,
      isOpen: () => openState,
      open,
      close,
    })
    return { controller, open, close }
  }

  it('intercepts Ctrl+F and Meta+F only while the scripts route is active', () => {
    const active = createController()
    const inactive = createController({ active: false })
    const ctrlFind = createKeyboardEvent('f', { ctrlKey: true })
    const metaFind = createKeyboardEvent('F', { metaKey: true })
    const inactiveFind = createKeyboardEvent('f', { ctrlKey: true })

    active.controller.handleKeydown(ctrlFind)
    active.controller.handleKeydown(metaFind)
    inactive.controller.handleKeydown(inactiveFind)

    expect(active.open).toHaveBeenCalledTimes(2)
    expect(ctrlFind.preventDefault).toHaveBeenCalledOnce()
    expect(metaFind.preventDefault).toHaveBeenCalledOnce()
    expect(inactive.open).not.toHaveBeenCalled()
    expect(inactiveFind.preventDefault).not.toHaveBeenCalled()
  })

  it('leaves input, textarea and contenteditable browser find behavior untouched', () => {
    const { controller, open } = createController()
    const contenteditable = {
      tagName: 'DIV',
      isContentEditable: true,
    } as unknown as EventTarget
    const events = [
      createKeyboardEvent('f', { ctrlKey: true, target: editableTarget('INPUT') }),
      createKeyboardEvent('f', { ctrlKey: true, target: editableTarget('TEXTAREA') }),
      createKeyboardEvent('f', { ctrlKey: true, target: contenteditable }),
    ]

    events.forEach(event => controller.handleKeydown(event))

    expect(open).not.toHaveBeenCalled()
    events.forEach(event => expect(event.preventDefault).not.toHaveBeenCalled())
  })

  it('ignores IME composition and closes an open search with Escape otherwise', () => {
    const { controller, close } = createController({ open: true })
    const composingEscape = createKeyboardEvent('Escape', { isComposing: true })
    const escape = createKeyboardEvent('Escape')

    controller.handleKeydown(composingEscape)
    controller.handleKeydown(escape)

    expect(close).toHaveBeenCalledOnce()
    expect(composingEscape.preventDefault).not.toHaveBeenCalled()
    expect(escape.preventDefault).toHaveBeenCalledOnce()
  })

  it('keeps only one listener after repeated binding and removes it on cleanup', () => {
    const { controller, open } = createController()
    const target = new EventTarget()
    const staleCleanup = controller.bind(target)
    const cleanup = controller.bind(target)

    target.dispatchEvent(createDispatchedKeyboardEvent('f', { ctrlKey: true }))
    staleCleanup()
    target.dispatchEvent(createDispatchedKeyboardEvent('f', { ctrlKey: true }))
    cleanup()
    target.dispatchEvent(createDispatchedKeyboardEvent('f', { ctrlKey: true }))

    expect(open).toHaveBeenCalledTimes(2)
  })

  it('restores the pre-search focus once and skips detached elements', () => {
    const focusManager = createScriptSearchFocusManager()
    const original = { isConnected: true, focus: vi.fn() }
    const later = { isConnected: true, focus: vi.fn() }

    focusManager.capture(original)
    focusManager.capture(later)
    focusManager.restore()
    focusManager.restore()

    expect(original.focus).toHaveBeenCalledOnce()
    expect(original.focus).toHaveBeenCalledWith({ preventScroll: true })
    expect(later.focus).not.toHaveBeenCalled()

    const detached = { isConnected: false, focus: vi.fn() }
    focusManager.capture(detached)
    focusManager.restore()
    expect(detached.focus).not.toHaveBeenCalled()
  })
})
