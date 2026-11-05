import type { TaskItemDocument } from '@/api'
import type { WSTaskCompletedData, WSTaskScriptInfoData } from '@/services/websocket/types'

export interface TaskOverviewProjection {
  task_info: WSTaskScriptInfoData[]
}

/** 面板内部完成数据；task_info 由树投影生成，不属于 WS 契约。 */
export type TaskCompletionView = Omit<WSTaskCompletedData, 'task'> & TaskOverviewProjection

/** 展示以运行 UUID 为键；原配置 UUID 只从 info 属性读取。 */
export function projectTaskTree(tree: TaskItemDocument): WSTaskScriptInfoData[] {
  return (tree.scripts?.order ?? []).flatMap(s => {
    const script = tree.scripts?.data?.[s.uid]
    if (!script) return []
    return [
      {
        script_id: s.uid,
        config_id: script.info?.script_id ?? '',
        name: script.info?.name ?? '',
        status: script.info?.status ?? '等待',
        userList: (script.users?.order ?? []).flatMap(u => {
          const user = script.users?.data?.[u.uid]
          return user
            ? [
                {
                  user_id: u.uid,
                  config_id: user.info?.user_id ?? '',
                  name: user.info?.name ?? '',
                  status: user.info?.status ?? '等待',
                },
              ]
            : []
        }),
      },
    ]
  })
}
