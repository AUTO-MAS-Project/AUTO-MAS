import type { ScriptType } from '@/types/script'

// ==================== 按键 ====================

/**
 * 按下的是哪个键，给口令和秘技用。开着中文输入法时字母、数字键的 key 是 `Process`，
 * 这时按物理键位（code）换回字母或数字，否则 mas、648 这些口令一个都敲不出来。
 */
export function keyOfEvent(event: Pick<KeyboardEvent, 'key' | 'code'>): string {
  if (event.key !== 'Process' && event.key !== 'Unidentified') return event.key
  const letter = /^Key([A-Z])$/.exec(event.code)
  if (letter) return letter[1].toLowerCase()
  const digit = /^(?:Digit|Numpad)([0-9])$/.exec(event.code)
  if (digit) return digit[1]
  return event.code
}

// ==================== 科乐美秘技 ====================

/** ↑↑↓↓←→←→BA：主页上按出来就开超频 */
const KONAMI_SEQUENCE = [
  'arrowup',
  'arrowup',
  'arrowdown',
  'arrowdown',
  'arrowleft',
  'arrowright',
  'arrowleft',
  'arrowright',
  'b',
  'a',
] as const

export function createKonamiMatcher() {
  let progress = 0

  /** 喂一个按键（KeyboardEvent.key），整串按完的那一下返回 true */
  function feed(key: string): boolean {
    const normalized = key.toLowerCase()
    if (normalized === KONAMI_SEQUENCE[progress]) {
      progress += 1
    } else {
      // 按错了不一定全废：↑↑↑ 里后两个仍可以当开头
      progress = normalized === KONAMI_SEQUENCE[0] ? (progress === 2 ? 2 : 1) : 0
    }

    if (progress === KONAMI_SEQUENCE.length) {
      progress = 0
      return true
    }
    return false
  }

  return { feed }
}

// ==================== 点卫星攒保底 ====================

/** 攒满之后的奖励：周哥出场，或者一场出金（文字和颜色按游戏区分） */
export type PityReward = 'zhouge' | 'gold' | 'sixStar' | 'sRank' | 'spark'

export interface PityEggConfig {
  /** 点满这么多下给奖励 */
  target: number
  /** 点到这些下数时冒一句预告，值是 home.satelliteEgg 下的词条 */
  hints: Readonly<Record<number, string>>
  /** 最后这么多下倒数 */
  countdown: number
  reward: PityReward
}

/**
 * 各游戏的保底抽数（2026-10 查证）：原神、星铁、绝区零 90 抽，74 抽起概率上涨；
 * 鸣潮 80 抽，70 抽起猛涨；终末地 80 抽，65 抽起每抽 +5%；重返未来 1999 角色池 70 抽；
 * 蔚蓝档案 200 抽天井。MAA 点满 325 下是周哥。
 */
export const PITY_EGGS: Readonly<Partial<Record<ScriptType, PityEggConfig>>> = {
  MAA: {
    target: 325,
    hints: { 100: 'maaHint1', 200: 'maaHint2', 300: 'maaHint3' },
    countdown: 5,
    reward: 'zhouge',
  },
  BetterGI: { target: 90, hints: { 74: 'softPity' }, countdown: 0, reward: 'gold' },
  SRC: { target: 90, hints: { 74: 'softPity' }, countdown: 0, reward: 'gold' },
  HSR: { target: 90, hints: { 74: 'softPity' }, countdown: 0, reward: 'gold' },
  ZzzOd: { target: 90, hints: { 74: 'softPity' }, countdown: 0, reward: 'sRank' },
  Okww: { target: 80, hints: { 70: 'softPity' }, countdown: 0, reward: 'gold' },
  MaaEnd: { target: 80, hints: { 65: 'softPity' }, countdown: 0, reward: 'sixStar' },
  M9A: { target: 70, hints: {}, countdown: 0, reward: 'sixStar' },
  BAAH: { target: 200, hints: { 100: 'halfway' }, countdown: 0, reward: 'spark' },
}

export type PityEvent =
  | { kind: 'hint'; key: string }
  | { kind: 'countdown'; remaining: number }
  | { kind: 'reward'; reward: PityReward }

/** 一颗卫星的点击计数：不要求连点，攒满给奖励后从头数 */
export function createPityTally(config: PityEggConfig) {
  let count = 0

  function poke(): PityEvent | null {
    count += 1
    if (count >= config.target) {
      count = 0
      return { kind: 'reward', reward: config.reward }
    }

    const remaining = config.target - count
    if (remaining <= config.countdown) {
      return { kind: 'countdown', remaining }
    }

    const key = config.hints[count]
    return key ? { kind: 'hint', key } : null
  }

  return {
    poke,
    get count() {
      return count
    },
  }
}

/** 计数存在模块里，切页面回来接着数，重启应用清零；不落盘 */
const pityTallies = new Map<ScriptType, ReturnType<typeof createPityTally>>()

/** 点了一下 type 的卫星；这个游戏没有保底彩蛋时返回 null */
export function pokePity(type: ScriptType): PityEvent | null {
  const config = PITY_EGGS[type]
  if (!config) return null
  let tally = pityTallies.get(type)
  if (!tally) {
    tally = createPityTally(config)
    pityTallies.set(type, tally)
  }
  return tally.poke()
}

// ==================== 连点 ====================

/** windowMs 内连点满 count 下算一次；触发后 cooldownMs 内不再触发 */
export function createRapidClickDetector(count: number, windowMs: number, cooldownMs: number) {
  const clicks: number[] = []
  let lastHitAt = -Infinity

  function click(now: number): boolean {
    clicks.push(now)
    while (clicks.length > 0 && now - clicks[0] > windowMs) {
      clicks.shift()
    }
    if (clicks.length < count || now - lastHitAt < cooldownMs) {
      return false
    }
    clicks.length = 0
    lastHitAt = now
    return true
  }

  return { click }
}

// ==================== 键盘口令 ====================

/**
 * 主页上直接敲的口令：648 首充双倍、1999 暴雨、666 烟花、520 爱心、404 卫星走丢、
 * 233 笑出声、mas 开发者火箭打榜。
 */
export const KEY_CODES = ['648', '1999', '666', '520', '404', '233', 'mas'] as const
export type KeyCode = (typeof KEY_CODES)[number]

/** 只认连续敲的数字和字母（不分大小写），中间按了别的键就从头来 */
export function createCodeMatcher<T extends string>(codes: readonly T[]) {
  const maxLength = Math.max(...codes.map(code => code.length))
  let buffer = ''

  function feed(key: string): T | null {
    const normalized = key.toLowerCase()
    if (!/^[0-9a-z]$/.test(normalized)) {
      buffer = ''
      return null
    }
    buffer = (buffer + normalized).slice(-maxLength)
    const hit = codes.find(code => buffer.endsWith(code))
    if (hit) {
      buffer = ''
      return hit
    }
    return null
  }

  return { feed }
}

// ==================== 会话级标记 ====================
// 存在模块里：切页面回来还在，重启应用清零

let firstVisitConsumed = false

/** 本次启动应用后第一次进主页返回 true（放入场跃迁），之后都是 false */
export function consumeFirstVisit(): boolean {
  if (firstVisitConsumed) return false
  firstVisitConsumed = true
  return true
}

const launchedKeys = new Set<string>()

/** 这颗卫星本次启动应用后第一次开跑返回 true（喊一句「××，启动！」），之后都是 false */
export function consumeFirstLaunch(key: string): boolean {
  if (launchedKeys.has(key)) return false
  launchedKeys.add(key)
  return true
}

// ==================== 转晕 ====================

/** 转速超过这个值（弧度/秒）才算在猛转 */
const DIZZY_SPIN_SPEED = 10
/** 猛转累计这么久就晕；随手甩一下的惯性撑不到这么久，得来回猛搓 */
const DIZZY_SPIN_TIME = 1200
/** 晕过一次之后这么久内不再晕 */
const DIZZY_COOLDOWN = 8000

export function createDizzyDetector() {
  let spinTime = 0
  let lastDizzyAt = -Infinity

  /** 每帧喂当前转速和帧间隔；该晕的那一帧返回 true */
  function feed(angularSpeed: number, dt: number, now: number): boolean {
    if (dt <= 0) return false
    if (Math.abs(angularSpeed) >= DIZZY_SPIN_SPEED) {
      spinTime += dt
    } else {
      spinTime = Math.max(0, spinTime - dt * 0.5)
    }

    if (spinTime >= DIZZY_SPIN_TIME && now - lastDizzyAt >= DIZZY_COOLDOWN) {
      spinTime = 0
      lastDizzyAt = now
      return true
    }
    return false
  }

  return { feed }
}

// ==================== 愚人节 ====================

/** 4 月 1 日卫星倒着转、图标倒过来 */
export function isAprilFools(date: Date): boolean {
  return date.getMonth() === 3 && date.getDate() === 1
}
