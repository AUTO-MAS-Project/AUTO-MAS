import { describe, expect, it } from 'vitest'

import {
  HOTKEY_PRIMARY_KEYS,
  canonicalHotkey,
  canonicalKeyName,
  displayKey,
  formatHotkey,
  hotkeyFromKeyboardEvent,
  isStorableHotkey,
  parseHotkey,
  primaryKeyFromCode,
  sameHotkey,
  type HotkeyKeyboardEventLike,
} from './maafwHotkey'

describe('isStorableHotkey / canonicalHotkey', () => {
  it('主键不在支持集合里、修饰键认不出或超过两个的不能存（与录制拒绝条件一致）', () => {
    expect(isStorableHotkey('E')).toBe(true)
    expect(isStorableHotkey('ctrl+shift+f1')).toBe(true)
    expect(isStorableHotkey('Esc')).toBe(true)
    expect(isStorableHotkey('MouseLeft')).toBe(false)
    expect(isStorableHotkey('Ctrl+Alt+Shift+E')).toBe(false)
    expect(isStorableHotkey('Q+E')).toBe(false)
    expect(isStorableHotkey('Ctrl++')).toBe(false)
    expect(isStorableHotkey('')).toBe(false)
  })

  it('比较形态归一别名、大小写与修饰键顺序，sameHotkey 用的就是它', () => {
    expect(canonicalHotkey('shift+control+g')).toBe(canonicalHotkey(['Ctrl', 'Shift', 'G']))
    expect(canonicalHotkey('Esc')).toBe('ESCAPE')
    expect(canonicalHotkey(null)).toBe('')
    expect(sameHotkey('esc', 'Escape')).toBe(true)
  })
})

const keydown = (init: Partial<HotkeyKeyboardEventLike>): HotkeyKeyboardEventLike => ({
  code: '',
  key: '',
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  ...init,
})

describe('primaryKeyFromCode', () => {
  it.each([
    ...Array.from({ length: 26 }, (_, i) => {
      const letter = String.fromCharCode(65 + i)
      return [`Key${letter}`, letter]
    }),
    ...Array.from({ length: 10 }, (_, i) => [`Digit${i}`, String(i)]),
    ...Array.from({ length: 24 }, (_, i) => [`F${i + 1}`, `F${i + 1}`]),
    ...Array.from({ length: 10 }, (_, i) => [`Numpad${i}`, `Numpad${i}`]),
    ['NumpadAdd', 'NumpadAdd'],
    ['NumpadSubtract', 'NumpadSubtract'],
    ['NumpadMultiply', 'NumpadMultiply'],
    ['NumpadDivide', 'NumpadDivide'],
    ['NumpadDecimal', 'NumpadDecimal'],
    ['NumpadEnter', 'Enter'],
    ['Space', 'Space'],
    ['Enter', 'Enter'],
    ['Tab', 'Tab'],
    ['Escape', 'Escape'],
    ['Backspace', 'Backspace'],
    ['Delete', 'Delete'],
    ['Insert', 'Insert'],
    ['Home', 'Home'],
    ['End', 'End'],
    ['PageUp', 'PageUp'],
    ['PageDown', 'PageDown'],
    ['ArrowLeft', 'Left'],
    ['ArrowRight', 'Right'],
    ['ArrowUp', 'Up'],
    ['ArrowDown', 'Down'],
    ['CapsLock', 'CapsLock'],
    ['Pause', 'Pause'],
    ['PrintScreen', 'PrintScreen'],
    ['NumLock', 'NumLock'],
    ['ScrollLock', 'ScrollLock'],
    ['Minus', 'Minus'],
    ['Equal', 'Equals'],
    ['Comma', 'Comma'],
    ['Period', 'Period'],
    ['Slash', 'Slash'],
    ['Backslash', 'Backslash'],
    ['Semicolon', 'Semicolon'],
    ['Quote', 'Quote'],
    ['BracketLeft', 'BracketLeft'],
    ['BracketRight', 'BracketRight'],
    ['Backquote', 'Grave'],
  ])('%s → %s', (code, expected) => {
    expect(primaryKeyFromCode(code)).toBe(expected)
  })

  it('映射结果全部落在支持集合里，支持集合每个键都有 code 能录到', () => {
    const codes = [
      ...Array.from({ length: 26 }, (_, i) => `Key${String.fromCharCode(65 + i)}`),
      ...Array.from({ length: 10 }, (_, i) => `Digit${i}`),
      ...Array.from({ length: 24 }, (_, i) => `F${i + 1}`),
      ...Array.from({ length: 10 }, (_, i) => `Numpad${i}`),
      'NumpadAdd',
      'NumpadSubtract',
      'NumpadMultiply',
      'NumpadDivide',
      'NumpadDecimal',
      'Space',
      'Enter',
      'Tab',
      'Escape',
      'Backspace',
      'Delete',
      'Insert',
      'Home',
      'End',
      'PageUp',
      'PageDown',
      'ArrowLeft',
      'ArrowRight',
      'ArrowUp',
      'ArrowDown',
      'CapsLock',
      'Pause',
      'PrintScreen',
      'NumLock',
      'ScrollLock',
      'Minus',
      'Equal',
      'Comma',
      'Period',
      'Slash',
      'Backslash',
      'Semicolon',
      'Quote',
      'BracketLeft',
      'BracketRight',
      'Backquote',
    ]
    const mapped = new Set(codes.map(primaryKeyFromCode))
    expect([...mapped].every(name => name && HOTKEY_PRIMARY_KEYS.includes(name))).toBe(true)
    expect(HOTKEY_PRIMARY_KEYS.filter(name => !mapped.has(name))).toEqual([])
  })

  it('存储名里没有符号', () => {
    expect(HOTKEY_PRIMARY_KEYS.filter(name => /[^A-Za-z0-9]/.test(name))).toEqual([])
  })

  it('不支持的键返回 null', () => {
    expect(primaryKeyFromCode('F25')).toBeNull()
    expect(primaryKeyFromCode('ContextMenu')).toBeNull()
    expect(primaryKeyFromCode('IntlBackslash')).toBeNull()
  })
})

describe('hotkeyFromKeyboardEvent', () => {
  it('单个主键', () => {
    expect(hotkeyFromKeyboardEvent(keydown({ code: 'KeyQ', key: 'q' }))).toEqual({
      kind: 'combo',
      keys: ['Q'],
    })
  })

  it('Minus 的存储名不是符号', () => {
    const result = hotkeyFromKeyboardEvent(keydown({ code: 'Minus', key: '-' }))
    expect(result).toEqual({ kind: 'combo', keys: ['Minus'] })
    expect(formatHotkey((result as { keys: string[] }).keys)).toBe('Minus')
  })

  it('修饰键按 Ctrl、Win、Alt、Shift 排序', () => {
    expect(
      hotkeyFromKeyboardEvent(keydown({ code: 'Digit1', key: '!', shiftKey: true, ctrlKey: true }))
    ).toEqual({ kind: 'combo', keys: ['Ctrl', 'Shift', '1'] })
    expect(
      hotkeyFromKeyboardEvent(keydown({ code: 'KeyA', key: 'a', altKey: true, metaKey: true }))
    ).toEqual({ kind: 'combo', keys: ['Win', 'Alt', 'A'] })
  })

  it('三个修饰键报错', () => {
    expect(
      hotkeyFromKeyboardEvent(
        keydown({ code: 'KeyA', key: 'a', ctrlKey: true, altKey: true, shiftKey: true })
      )
    ).toEqual({ kind: 'too-many-modifiers' })
  })

  it.each([
    ['ShiftLeft', 'Shift'],
    ['ShiftRight', 'Shift'],
    ['ControlLeft', 'Control'],
    ['ControlRight', 'Control'],
    ['AltLeft', 'Alt'],
    ['AltRight', 'Alt'],
    ['MetaLeft', 'Meta'],
    ['MetaRight', 'Meta'],
  ])('单按修饰键 %s 不结束录制', (code, key) => {
    expect(hotkeyFromKeyboardEvent(keydown({ code, key }))).toEqual({ kind: 'modifier-only' })
  })

  it('code 不带左右后缀时按 key 认修饰键', () => {
    for (const key of ['Shift', 'Control', 'Alt', 'Meta', 'OS']) {
      expect(hotkeyFromKeyboardEvent(keydown({ code: '', key }))).toEqual({
        kind: 'modifier-only',
      })
    }
  })

  it('key 与 code 皆空的合成事件忽略', () => {
    expect(hotkeyFromKeyboardEvent(keydown({}))).toEqual({ kind: 'ignored' })
  })

  it('不支持的键', () => {
    expect(hotkeyFromKeyboardEvent(keydown({ code: 'ContextMenu', key: 'ContextMenu' }))).toEqual({
      kind: 'unsupported',
    })
  })

  it('没有 code 时按 key 兜底认主键', () => {
    expect(hotkeyFromKeyboardEvent(keydown({ key: 'e' }))).toEqual({ kind: 'combo', keys: ['E'] })
    expect(hotkeyFromKeyboardEvent(keydown({ key: 'ArrowUp' }))).toEqual({
      kind: 'combo',
      keys: ['Up'],
    })
    expect(hotkeyFromKeyboardEvent(keydown({ key: 'Unidentified' }))).toEqual({
      kind: 'unsupported',
    })
  })
})

describe('parseHotkey / sameHotkey', () => {
  it.each([
    ['Control', 'Ctrl'],
    ['ctl', 'Ctrl'],
    ['Esc', 'Escape'],
    ['Return', 'Enter'],
    ['ArrowLeft', 'Left'],
    ['PgUp', 'PageUp'],
    ['PgDn', 'PageDown'],
    ['Del', 'Delete'],
    ['Command', 'Win'],
    ['Cmd', 'Win'],
    ['Meta', 'Win'],
    ['Windows', 'Win'],
    ['Super', 'Win'],
    [',', 'Comma'],
    ['.', 'Period'],
    ['-', 'Minus'],
    ['=', 'Equals'],
    ['`', 'Grave'],
    ['Backquote', 'Grave'],
    ['KeyA', 'A'],
    ['Digit3', '3'],
    ['page up', 'PageUp'],
    ['f12', 'F12'],
    ['numpad5', 'Numpad5'],
    ['e', 'E'],
  ])('别名 %s → %s', (alias, expected) => {
    expect(canonicalKeyName(alias)).toBe(expected)
  })

  it('解析组合键并按存储顺序排修饰键', () => {
    expect(parseHotkey('shift+control+1')).toEqual(['Ctrl', 'Shift', '1'])
    expect(parseHotkey('F1')).toEqual(['F1'])
    expect(parseHotkey('')).toEqual([])
    expect(parseHotkey(null)).toEqual([])
  })

  it('解析不了的原样保留', () => {
    expect(parseHotkey('Mouse4')).toEqual(['Mouse4'])
    expect(parseHotkey('Ctrl++')).toEqual(['Ctrl++'])
  })

  it('比较时别名、大小写与修饰键顺序都不算差别', () => {
    expect(sameHotkey('e', 'E')).toBe(true)
    expect(sameHotkey('Control+Esc', 'Ctrl+Escape')).toBe(true)
    expect(sameHotkey('Shift+Ctrl+A', ['Ctrl', 'Shift', 'A'])).toBe(true)
    expect(sameHotkey('Shift+1', '1')).toBe(false)
    expect(sameHotkey('Q', 'E')).toBe(false)
  })
})

describe('displayKey', () => {
  it.each([
    ['Minus', '-'],
    ['Equals', '='],
    ['Comma', ','],
    ['Period', '.'],
    ['Slash', '/'],
    ['Backslash', '\\'],
    ['Semicolon', ';'],
    ['Quote', "'"],
    ['BracketLeft', '['],
    ['BracketRight', ']'],
    ['Grave', '`'],
    ['Escape', 'Esc'],
    ['Left', '←'],
    ['Right', '→'],
    ['Up', '↑'],
    ['Down', '↓'],
    ['Numpad1', 'Num 1'],
    ['NumpadAdd', 'Num +'],
    ['NumpadSubtract', 'Num -'],
    ['F1', 'F1'],
    ['Shift', 'Shift'],
    ['Mouse4', 'Mouse4'],
  ])('%s 显示为 %s', (name, expected) => {
    expect(displayKey(name)).toBe(expected)
  })
})
