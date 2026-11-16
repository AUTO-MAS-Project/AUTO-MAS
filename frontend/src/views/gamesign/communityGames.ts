/**
 * 游戏社区覆盖的五款游戏。
 *
 * 中文名是后端便笺合同的稳定枚举，只用于匹配与过滤，不参与界面翻译。
 * 分区顺序、资源置顶与卡片视觉都从这一份清单派生：新增游戏时改这里，
 * 少了映射项会直接变成类型错误，不会静默漏掉。
 */
export const COMMUNITY_GAMES = ['明日方舟', '终末地', '原神', '星穹铁道', '绝区零'] as const

export type CommunityGame = (typeof COMMUNITY_GAMES)[number]

/** 判断上游返回的游戏名是否属于已知社区游戏，用于安全索引映射表。 */
export const isCommunityGame = (game: string): game is CommunityGame =>
  (COMMUNITY_GAMES as readonly string[]).includes(game)
