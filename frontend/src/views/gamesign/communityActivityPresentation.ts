import type { ActivitySnapshot } from './useCommunityActivityApi'

export interface NoteMetric {
  name: string
  current: number
  target: number
  status: string
  period: string
}

// 中文名称来自后端便笺合同；历练点、通行证等级及任务积分不属于经验。
const FEATURED_RESOURCES: Record<string, string[]> = {
  明日方舟: ['理智', '无人机', '训练室'],
  终末地: ['理智'],
  原神: ['原粹树脂', '洞天宝钱'],
  星穹铁道: ['开拓力', '储备开拓力'],
  绝区零: ['电量'],
}

export function presentActivity(snapshot: ActivitySnapshot) {
  const visible = (metric: { name: string }) => !/经验|experience|\bexp\b/i.test(metric.name)
  const resources: NoteMetric[] = snapshot.resources.filter(visible).map(resource => ({
    ...resource,
    period: 'resource',
  }))
  const tasks: NoteMetric[] = snapshot.tasks.filter(visible).map(task => ({
    name: task.name,
    current: task.completed,
    target: task.target,
    status: task.status,
    period: task.period,
  }))
  const featured = (FEATURED_RESOURCES[snapshot.game] ?? []).flatMap(name =>
    resources.filter(resource => resource.name === name)
  )
  if (snapshot.game === '绝区零') {
    featured.push(...tasks.filter(task => task.name === '今日活跃度'))
  }
  const remainingResources = resources.filter(resource => !featured.includes(resource))
  const remainingTasks = tasks.filter(task => !featured.includes(task))
  const overview = snapshot.game === '明日方舟' || snapshot.game === '绝区零'
  const groups = overview
    ? [
        { labelKey: 'gamesign.activity.noteTasks', metrics: remainingTasks },
        { labelKey: 'gamesign.activity.resources', metrics: remainingResources },
      ]
    : [{ labelKey: '', metrics: [...remainingTasks, ...remainingResources] }]
  if (snapshot.game === '明日方舟') groups.reverse()
  return { featured, groups: groups.filter(group => group.metrics.length), overview }
}
