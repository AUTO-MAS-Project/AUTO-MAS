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

/** 列表分区：进行中/已达成是一个扁平分区，已归档按游戏分组 */
export interface TaskboardSection {
  id: string
  name: string
  showHead: boolean
  items: TaskboardActivity[]
}
