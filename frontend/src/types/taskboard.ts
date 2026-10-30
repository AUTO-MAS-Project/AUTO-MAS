/** 任务台的一条活动（各官方活动源统一后的形状） */
export interface TaskboardActivity {
  id: string
  gameKey: string
  title: string
  start_time: string
  end_time: string
  description: string
  image_url: string
}

/** 任务台里可选的一个游戏（碧蓝档案按服务器拆成多项） */
export interface TaskboardGameOption {
  key: string
  name: string
  cover: string
}

/** 每周任务的本地状态：key 为任务台游戏标识 */
export interface TaskboardWeeklyRecord {
  week: string
  done_at: string
}

/** 本地积累的一条版本主线记录 */
export interface TaskboardVersionStoryRecord {
  game: string
  version: string
  version_name: string
  start: string
  end: string
  cover_url: string
  first_seen: string
  last_seen: string
}

/** 前端本次取到、准备提交给后端的版本记录 */
export type TaskboardVersionStoryUpdate = Pick<
  TaskboardVersionStoryRecord,
  'game' | 'version' | 'version_name' | 'start' | 'end' | 'cover_url'
>

/** 时间轴上的一个版本节点 */
export interface TaskboardVersionStoryNode {
  record: TaskboardVersionStoryRecord
  done: boolean
  current: boolean
  future: boolean
  ended: boolean
}

/** 一个游戏的版本主线分组 */
export interface TaskboardVersionStoryGroup {
  option: TaskboardGameOption
  records: TaskboardVersionStoryNode[]
  current: TaskboardVersionStoryNode
}
