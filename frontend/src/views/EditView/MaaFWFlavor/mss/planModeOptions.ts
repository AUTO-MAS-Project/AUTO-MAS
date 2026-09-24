// MSS 用户页「计划表」下拉的选项：固定 + MSS 消费方的计划表。
// 由 prepareUserPage 在页面加载期间取好（和读取 interface 并行），下拉渲染出来时选项已经在了，
// 不会先闪一下计划表 id。页面同一时刻只有一个，模块级状态足够，每次进页面重取。

import { shallowRef } from 'vue'
import { PlanComboxIn, Service, type ComboBoxItem } from '@/api'

export const PLAN_MODE_FIXED = 'Fixed'

export interface PlanModeOption {
  label: string
  value: string
}

/** 后端给的计划表列表；null 表示还没取到或取失败，只留「固定」一项 */
export const mssPlanComboxItems = shallowRef<ComboBoxItem[] | null>(null)

export const loadMSSPlanComboxItems = async (): Promise<void> => {
  mssPlanComboxItems.value = null
  try {
    const response = await Service.getPlanComboxApiInfoComboxPlanPost({
      consumer: PlanComboxIn.consumer.MSS,
    })
    if (response?.code !== 200 || !response.data) return
    mssPlanComboxItems.value = response.data
  } catch (error) {
    // 取不到计划表时只留「固定」一项，其它设置照常能改
    window.electronAPI
      .getLogger('MaaFW用户编辑')
      .error(`加载计划表选项失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

/** 「固定」一项用本地文案，其余照后端给的名字；空值项丢掉 */
export const buildPlanModeOptions = (
  items: readonly ComboBoxItem[] | null,
  fixedLabel: string
): PlanModeOption[] => {
  if (!items) return [{ label: fixedLabel, value: PLAN_MODE_FIXED }]
  return items
    .filter(item => Boolean(item.value))
    .map(item =>
      item.value === PLAN_MODE_FIXED
        ? { label: fixedLabel, value: PLAN_MODE_FIXED }
        : { label: item.label ?? '', value: String(item.value) }
    )
}

/**
 * 队列空、计划表又是「固定」时这一轮没有任何可执行任务：引擎会判「无法构建运行计划」
 * 并抛异常（`run_plan` 里 runnable_tasks 为空）。选了计划表就不算——特调钩子会把悬赏试炼补上。
 */
export const isMSSQueueUnrunnable = (queuedTaskCount: number, planMode: string | undefined) =>
  queuedTaskCount === 0 && (planMode ?? PLAN_MODE_FIXED) === PLAN_MODE_FIXED
