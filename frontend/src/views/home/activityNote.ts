import type { HomeModuleKey } from '@/types/home'
import type { ActivitySnapshot } from '@/views/gamesign/useCommunityActivityApi'

/**
 * 轮播游戏键 → 社区数据里的游戏中文名。
 * 中文名是后端便笺/签到合同的稳定枚举（与 gamesign 页展示同源），只用于匹配，不参与界面翻译。
 * 首页社区信息只展示已接入日常便笺的五款游戏；其余游戏不展示此区域。
 */
export const ACTIVITY_NOTE_GAME_NAMES: Partial<Record<HomeModuleKey, string>> = {
  arknights: '明日方舟',
  endfield: '终末地',
  genshin: '原神',
  starrail: '星穹铁道',
  zenless: '绝区零',
}

/** 轮播切到没有社区数据可对应的游戏时返回 null，首页社区信息区不渲染 */
export const activityNoteGameName = (key: HomeModuleKey | null): string | null =>
  key === null ? null : (ACTIVITY_NOTE_GAME_NAMES[key] ?? null)

/** 只需 game 字段即可完成匹配，不依赖便笺具体类型 */
interface NoteSnapshotLike {
  game: string
}

/** 取出当前轮播游戏对应的便笺快照；同一游戏有多个账号时会全部返回 */
export const activityNoteSnapshots = <T extends NoteSnapshotLike>(
  snapshots: T[],
  key: HomeModuleKey | null
): T[] => {
  const gameName = activityNoteGameName(key)
  return gameName === null ? [] : snapshots.filter(snapshot => snapshot.game === gameName)
}

/** 用账号与角色身份保持选择；昵称和数值更新不改变已有角色的身份。 */
export const activityNoteKey = (snapshot: ActivitySnapshot): string =>
  JSON.stringify([
    snapshot.accountUid,
    snapshot.platform,
    snapshot.game,
    snapshot.roleUid || snapshot.roleName,
    snapshot.server,
  ])
