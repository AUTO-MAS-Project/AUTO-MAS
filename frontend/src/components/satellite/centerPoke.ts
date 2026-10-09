// ── 中心图标彩蛋：连点 5 次起，每次按固定概率把中心图标换成炫彩版 ──
// 前 4 次不给机会，从第 5 次起每次 0.5%；连点到 30 次保底直接给，命中过就不再触发。
const CENTER_POKE_MIN_CLICKS = 5
const CENTER_POKE_CHANCE = 0.005
/** 手气差也不能点不到头，连点到这个次数一定给 */
const CENTER_POKE_GUARANTEE_CLICKS = 30
const CENTER_POKE_WINDOW_MS = 1500

/** 这一下点出了彩蛋：保底给的，还是运气好抽中的 */
export type CenterPokeHit = 'guarantee' | 'lucky'

export function createCenterPokeCounter(random: () => number = Math.random) {
  let count = 0
  let lastAt = 0

  /** 记一次点击；alreadyTriggered 为真时只计数不触发 */
  function poke(now: number, alreadyTriggered: boolean): CenterPokeHit | null {
    // 慢悠悠点不算连点：超过窗口就从头数
    if (now - lastAt > CENTER_POKE_WINDOW_MS) {
      count = 0
    }
    lastAt = now
    count += 1

    // 连点够数之前不给机会
    if (count < CENTER_POKE_MIN_CLICKS || alreadyTriggered) {
      return null
    }

    // 保底：点够次数直接给，不再看概率
    if (count >= CENTER_POKE_GUARANTEE_CLICKS) {
      count = 0
      return 'guarantee'
    }

    // 连点够数之后，每一次都是同样的概率，不会越点越容易
    if (random() >= CENTER_POKE_CHANCE) {
      return null
    }

    count = 0
    return 'lucky'
  }

  return { poke }
}
