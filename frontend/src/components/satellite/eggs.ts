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

// ==================== MAA 点满 325 下 ====================

export const MAA_POKE_TARGET = 325

/** 点到这些下数时给一点预告，免得点了两百多下还以为什么都没有 */
const MAA_POKE_HINTS: Readonly<Record<number, 'maaHint1' | 'maaHint2' | 'maaHint3'>> = {
  100: 'maaHint1',
  200: 'maaHint2',
  300: 'maaHint3',
}

export type MaaPokeEvent =
  | { kind: 'hint'; hint: 'maaHint1' | 'maaHint2' | 'maaHint3' }
  | { kind: 'countdown'; remaining: number }
  | { kind: 'reveal' }

/**
 * MAA 卫星的点击计数。不要求连点，也不落盘：计数存在模块里，切页面回来接着数，重启应用清零。
 * 点满 325 下周哥出场，然后从头数。
 */
export function createMaaPokeTally() {
  let count = 0

  function poke(): MaaPokeEvent | null {
    count += 1
    if (count >= MAA_POKE_TARGET) {
      count = 0
      return { kind: 'reveal' }
    }

    const remaining = MAA_POKE_TARGET - count
    if (remaining <= 5) {
      return { kind: 'countdown', remaining }
    }

    const hint = MAA_POKE_HINTS[count]
    return hint ? { kind: 'hint', hint } : null
  }

  return {
    poke,
    get count() {
      return count
    },
  }
}

/** 跨组件实例共用，主页卸载再挂载不清零 */
export const maaPokeTally = createMaaPokeTally()

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
