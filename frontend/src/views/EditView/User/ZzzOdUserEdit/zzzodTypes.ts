import type { ZzzOdUserConfig } from '@/api'
import type { ZzzOdTaskCard } from '@/composables/useZzzOdTaskBoard'
/** 「游戏结束后操作」按模式分流：原生来源写原生 after_done（与原生 GUI 同源），
 * 用户/脚本写 MAS 用户字段（该模式无原生实例概念） */
export type AfterDoneValue = NonNullable<NonNullable<ZzzOdUserConfig['OneDragon']>['AfterDone']>
// ══ 一条龙任务（OneDragon.AppList JSON 字段，打开页面即可开关）══
// 卡片结构与操作封装见 useZzzOdTaskBoard（独立来源与原生来源共用）
export type TaskCard = ZzzOdTaskCard
