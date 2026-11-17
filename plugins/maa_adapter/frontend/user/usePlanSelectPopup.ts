import { shallowRef, ref } from 'vue'
import { useResizeObserver } from '@vueuse/core'

const DEFAULT_LIST_HEIGHT = 256
const MIN_LIST_HEIGHT = 32
const DROPDOWN_PADDING = 8

/** 菜单随编辑器滚动，候选列表高度限制在弹窗正文内。 */
export function usePlanSelectPopup() {
  const scrollContainer = shallowRef<HTMLElement | null>(null)
  const listHeight = ref(DEFAULT_LIST_HEIGHT)
  const updateListHeight = () => {
    listHeight.value = scrollContainer.value
      ? Math.max(
          MIN_LIST_HEIGHT,
          Math.min(DEFAULT_LIST_HEIGHT, scrollContainer.value.clientHeight - DROPDOWN_PADDING)
        )
      : DEFAULT_LIST_HEIGHT
  }
  useResizeObserver(scrollContainer, updateListHeight)

  const getPopupContainer = (trigger: HTMLElement): HTMLElement => {
    scrollContainer.value = trigger.closest<HTMLElement>('.ant-modal-body')
    updateListHeight()
    return trigger.closest<HTMLElement>('.depot-plan-editor, .cultivate-editor') ?? document.body
  }

  return { getPopupContainer, listHeight }
}
