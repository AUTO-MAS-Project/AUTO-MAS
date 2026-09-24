import type { Ref } from 'vue'

/** 一条龙任务卡片（用户模式 AppList 与直控原生编排通用结构） */
export interface ZzzOdTaskCard {
  app_id: string
  app_name: string
  enabled: boolean
  configurable?: boolean
  jump?: boolean
}

/**
 * 一条龙任务看板的共用操作（用户模式与直控模式通用）。
 *
 * 两种模式只是配置对象不同（用户=MAS `OneDragon.AppList` 字段、
 * 直控=实例原生 `_group.yml`），开关 / 拖拽排序 / 一键整理的列表
 * 语义完全一致：未启用项原位保留（对齐一条龙原生队列语义），
 * 「启用在前、禁用在后」只在用户显式点一键整理时触发；改动先写回
 * 本地渲染状态，再由 commit 按当前模式各自落盘。
 */
export function useZzzOdTaskBoard(
  dragCards: Ref<ZzzOdTaskCard[]>,
  options: {
    /** 可编辑守卫（初始化 / 页面加载中时忽略操作） */
    editable: () => boolean
    /** 应用到当前模式的本地状态并落盘 */
    commit: (list: ZzzOdTaskCard[]) => void
  }
) {
  /** 开关：原位翻转启用状态；不在列表时加入末尾 */
  const toggle = (card: ZzzOdTaskCard) => {
    if (!options.editable()) return
    const list = [...dragCards.value]
    const idx = list.findIndex(item => item.app_id === card.app_id)
    if (idx >= 0) {
      list[idx] = { ...list[idx], enabled: !list[idx].enabled }
    } else {
      list.push({ ...card, enabled: true })
    }
    options.commit(list)
  }

  /** 拖拽结束：vuedraggable 已就地更新 dragCards，按最终顺序落盘 */
  const commitDragOrder = () => {
    if (!options.editable()) return
    options.commit([...dragCards.value])
  }

  /** 一键整理：启用在前、禁用在后（各自保持相对顺序），仅在点击时触发 */
  const sortEnabledFirst = () => {
    if (!options.editable()) return
    const list = [...dragCards.value]
    const sorted = [...list.filter(card => card.enabled), ...list.filter(card => !card.enabled)]
    dragCards.value = sorted
    options.commit(sorted)
  }

  return { toggle, commitDragOrder, sortEnabledFirst }
}
