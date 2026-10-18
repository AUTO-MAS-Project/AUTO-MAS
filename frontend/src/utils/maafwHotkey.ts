// MFW 键位映射（PI v2.8 hotkey）的键名规范化：录制、解析、比较、显示都走这里，单一来源。
//
// 存储契约（后端按此验证）：`修饰键+...+主键`，修饰键按 Ctrl、Win、Alt、Shift 排序、最多两个；
// 主键用下面 PRIMARY_KEYS 里的存储名。存储名一律不用符号：后端 `_canonical_key` 会用
// `[\s_-]+` 把 `-` 删成空串，`+` 又是分隔符。
//
// 支持集合须与 app/task/MaaFW/tools/core/runner/hotkey.py 的 Win32 表一致，两边同改。

/** 修饰键的存储名，按存储顺序排列 */
export const HOTKEY_MODIFIERS = ['Ctrl', 'Win', 'Alt', 'Shift'] as const
export type HotkeyModifier = (typeof HOTKEY_MODIFIERS)[number]

/** 一个组合键最多带几个修饰键 */
export const HOTKEY_MAX_MODIFIERS = 2

const range = (count: number, map: (index: number) => string) =>
  Array.from({ length: count }, (_, index) => map(index))

/** 主键的存储名（不含修饰键） */
export const HOTKEY_PRIMARY_KEYS: readonly string[] = [
  ...range(26, index => String.fromCharCode(65 + index)),
  ...range(10, index => String(index)),
  ...range(24, index => `F${index + 1}`),
  ...range(10, index => `Numpad${index}`),
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
  'Left',
  'Right',
  'Up',
  'Down',
  'CapsLock',
  'Pause',
  'PrintScreen',
  'NumLock',
  'ScrollLock',
  'Minus',
  'Equals',
  'Comma',
  'Period',
  'Slash',
  'Backslash',
  'Semicolon',
  'Quote',
  'BracketLeft',
  'BracketRight',
  'Grave',
]

/** KeyboardEvent.code 里名字与存储名不同的键；字母 / 数字 / F 键 / 小键盘数字按规则换算 */
const CODE_TO_PRIMARY: Record<string, string> = {
  NumpadAdd: 'NumpadAdd',
  NumpadSubtract: 'NumpadSubtract',
  NumpadMultiply: 'NumpadMultiply',
  NumpadDivide: 'NumpadDivide',
  NumpadDecimal: 'NumpadDecimal',
  NumpadEnter: 'Enter',
  Space: 'Space',
  Enter: 'Enter',
  Tab: 'Tab',
  Escape: 'Escape',
  Backspace: 'Backspace',
  Delete: 'Delete',
  Insert: 'Insert',
  Home: 'Home',
  End: 'End',
  PageUp: 'PageUp',
  PageDown: 'PageDown',
  ArrowLeft: 'Left',
  ArrowRight: 'Right',
  ArrowUp: 'Up',
  ArrowDown: 'Down',
  CapsLock: 'CapsLock',
  Pause: 'Pause',
  PrintScreen: 'PrintScreen',
  NumLock: 'NumLock',
  ScrollLock: 'ScrollLock',
  Minus: 'Minus',
  Equal: 'Equals',
  Comma: 'Comma',
  Period: 'Period',
  Slash: 'Slash',
  Backslash: 'Backslash',
  Semicolon: 'Semicolon',
  Quote: 'Quote',
  BracketLeft: 'BracketLeft',
  BracketRight: 'BracketRight',
  Backquote: 'Grave',
}

const MODIFIER_CODES = new Set([
  'ControlLeft',
  'ControlRight',
  'MetaLeft',
  'MetaRight',
  'OSLeft',
  'OSRight',
  'AltLeft',
  'AltRight',
  'ShiftLeft',
  'ShiftRight',
])
const MODIFIER_KEYS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'OS'])

/** 把 KeyboardEvent.code 换成主键存储名；不支持的键返回 null */
export const primaryKeyFromCode = (code: string): string | null => {
  let match = /^Key([A-Z])$/.exec(code)
  if (match) return match[1]
  match = /^Digit([0-9])$/.exec(code)
  if (match) return match[1]
  match = /^F([1-9]|1[0-9]|2[0-4])$/.exec(code)
  if (match) return `F${match[1]}`
  match = /^Numpad([0-9])$/.exec(code)
  if (match) return `Numpad${match[1]}`
  return CODE_TO_PRIMARY[code] ?? null
}

// ---- 解析：interface 的 default 与已存值 ----

/** 别名（大写、去掉空白 / 下划线 / 连字符后）→ 存储名；照 hotkey.py 的 _ALIASES 与标点别名 */
const ALIASES: Record<string, string> = {
  CTRL: 'Ctrl',
  CONTROL: 'Ctrl',
  CTL: 'Ctrl',
  ALT: 'Alt',
  OPTION: 'Alt',
  SHIFT: 'Shift',
  WIN: 'Win',
  META: 'Win',
  COMMAND: 'Win',
  CMD: 'Win',
  WINDOWS: 'Win',
  SUPER: 'Win',
  OS: 'Win',
  ESC: 'Escape',
  RETURN: 'Enter',
  NUMPADENTER: 'Enter',
  SPACEBAR: 'Space',
  ARROWLEFT: 'Left',
  ARROWRIGHT: 'Right',
  ARROWUP: 'Up',
  ARROWDOWN: 'Down',
  PGUP: 'PageUp',
  PGDN: 'PageDown',
  DEL: 'Delete',
  INS: 'Insert',
  BACKTICK: 'Grave',
  BACKQUOTE: 'Grave',
  APOSTROPHE: 'Quote',
  EQUAL: 'Equals',
  // hotkey.py 里 ADD / PLUS、MULTIPLY、DIVIDE、DECIMAL 都是小键盘键码
  ADD: 'NumpadAdd',
  PLUS: 'NumpadAdd',
  SUBTRACT: 'NumpadSubtract',
  MULTIPLY: 'NumpadMultiply',
  DIVIDE: 'NumpadDivide',
  DECIMAL: 'NumpadDecimal',
}

const PUNCTUATION_ALIASES: Record<string, string> = {
  '-': 'Minus',
  '=': 'Equals',
  ',': 'Comma',
  '.': 'Period',
  '/': 'Slash',
  '\\': 'Backslash',
  ';': 'Semicolon',
  "'": 'Quote',
  '`': 'Grave',
  '[': 'BracketLeft',
  ']': 'BracketRight',
}

const STORAGE_BY_UPPER = new Map<string, string>(
  [...HOTKEY_MODIFIERS, ...HOTKEY_PRIMARY_KEYS].map(name => [name.toUpperCase(), name])
)

/** 单个键名归一成存储名；认不出的原样返回（去掉首尾空白） */
export const canonicalKeyName = (value: string): string => {
  if (value === ' ') return 'Space'
  const trimmed = value.trim()
  const punctuation = PUNCTUATION_ALIASES[trimmed]
  if (punctuation) return punctuation
  let normalized = trimmed.replace(/[\s_-]+/g, '').toUpperCase()
  if (/^KEY[A-Z]$/.test(normalized)) normalized = normalized.slice(3)
  else if (/^DIGIT[0-9]$/.test(normalized)) normalized = normalized.slice(5)
  return ALIASES[normalized] ?? STORAGE_BY_UPPER.get(normalized) ?? trimmed
}

const isModifier = (name: string): name is HotkeyModifier =>
  (HOTKEY_MODIFIERS as readonly string[]).includes(name)

/**
 * 解析一个组合键字符串成键名数组（修饰键在前、按存储顺序，主键最后）。
 * 认不出的键原样保留；整串拆不开（如有空段）就当一个键原样返回，不报错。
 */
export const parseHotkey = (value: string | null | undefined): string[] => {
  const raw = (value ?? '').trim()
  if (!raw) return []
  const parts = raw.split('+')
  if (parts.some(part => !part.trim())) return [raw]
  const keys = parts.map(canonicalKeyName)
  const modifiers = keys.slice(0, -1)
  if (!modifiers.every(isModifier)) return keys
  const ordered = HOTKEY_MODIFIERS.filter(modifier => modifiers.includes(modifier))
  return [...ordered, keys[keys.length - 1]]
}

/** 键名数组 → 存储串 */
export const formatHotkey = (keys: readonly string[]): string => keys.join('+')

/** 组合键的比较形态：别名、大小写、修饰键顺序都归一掉，只用来判断是否相同 */
export const canonicalHotkey = (value: string | readonly string[] | null | undefined): string =>
  (typeof value === 'string' || value == null
    ? parseHotkey(value)
    : parseHotkey(formatHotkey(value))
  )
    .map(key => key.toUpperCase())
    .join('+')

/** 两个组合键是否相同（别名、大小写、修饰键顺序都不算差别） */
export const sameHotkey = (
  a: string | readonly string[] | null | undefined,
  b: string | readonly string[] | null | undefined
): boolean => canonicalHotkey(a) === canonicalHotkey(b)

/**
 * 组合键能不能存（导入外壳配置等非录制来源用）：主键在支持集合里、修饰键都认得且不超过两个。
 * 与录制时 `hotkeyFromKeyboardEvent` 的拒绝条件一致。
 */
export const isStorableHotkey = (value: string): boolean => {
  const keys = parseHotkey(value)
  if (keys.length === 0) return false
  const modifiers = keys.slice(0, -1)
  return (
    modifiers.length <= HOTKEY_MAX_MODIFIERS &&
    modifiers.every(isModifier) &&
    HOTKEY_PRIMARY_KEYS.includes(keys[keys.length - 1])
  )
}

// ---- 显示 ----

const DISPLAY_NAMES: Record<string, string> = {
  Minus: '-',
  Equals: '=',
  Comma: ',',
  Period: '.',
  Slash: '/',
  Backslash: '\\',
  Semicolon: ';',
  Quote: "'",
  BracketLeft: '[',
  BracketRight: ']',
  Grave: '`',
  Escape: 'Esc',
  Left: '←',
  Right: '→',
  Up: '↑',
  Down: '↓',
  NumpadAdd: 'Num +',
  NumpadSubtract: 'Num -',
  NumpadMultiply: 'Num *',
  NumpadDivide: 'Num /',
  NumpadDecimal: 'Num .',
}

/** 键帽上显示的文字（存储名不变） */
export const displayKey = (name: string): string => {
  const numpadDigit = /^Numpad([0-9])$/.exec(name)
  if (numpadDigit) return `Num ${numpadDigit[1]}`
  return DISPLAY_NAMES[name] ?? name
}

// ---- 录制 ----

export type HotkeyEventResult =
  /** 没有任何键信息的合成事件，忽略 */
  | { kind: 'ignored' }
  /** 只按了修饰键，继续等主键 */
  | { kind: 'modifier-only' }
  /** 主键不在支持集合里 */
  | { kind: 'unsupported' }
  /** 修饰键超过两个 */
  | { kind: 'too-many-modifiers' }
  | { kind: 'combo'; keys: string[] }

/** 键盘事件里录制需要的字段（KeyboardEvent 本身满足） */
export type HotkeyKeyboardEventLike = Pick<
  KeyboardEvent,
  'code' | 'key' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey'
>

/** 把一次 keydown 换成录制结果 */
export const hotkeyFromKeyboardEvent = (event: HotkeyKeyboardEventLike): HotkeyEventResult => {
  const code = event.code ?? ''
  const key = event.key ?? ''
  if (!code && !key) return { kind: 'ignored' }
  // code 在部分输入法 / 远程桌面 / 自动化下不带左右后缀，按 key 兜底
  if (MODIFIER_CODES.has(code) || MODIFIER_KEYS.has(key)) return { kind: 'modifier-only' }

  let primary = code ? primaryKeyFromCode(code) : null
  if (!primary && !code) {
    // 没有 code 的事件按 key 认：只认归一后落在支持集合里的主键
    const fromKey = canonicalKeyName(key.length === 1 ? key.toUpperCase() : key)
    if (HOTKEY_PRIMARY_KEYS.includes(fromKey)) primary = fromKey
  }
  if (!primary) return { kind: 'unsupported' }

  const pressed: Record<HotkeyModifier, boolean> = {
    Ctrl: event.ctrlKey,
    Win: event.metaKey,
    Alt: event.altKey,
    Shift: event.shiftKey,
  }
  const modifiers = HOTKEY_MODIFIERS.filter(modifier => pressed[modifier])
  if (modifiers.length > HOTKEY_MAX_MODIFIERS) return { kind: 'too-many-modifiers' }
  return { kind: 'combo', keys: [...modifiers, primary] }
}
