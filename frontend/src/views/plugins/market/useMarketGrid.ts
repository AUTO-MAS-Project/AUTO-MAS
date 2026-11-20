import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { marketColumnCount } from '../pluginCenterModel'

/**
 * 市场栅格列数：监听容器宽度，取能放下的最大列数，末行只剩一张时减一列。
 * 容器换了或组件卸载时断开监听。
 */
export function useMarketGrid(container: Ref<HTMLElement | null>, cardCount: Ref<number>) {
  const width = ref(0)
  let observer: ResizeObserver | null = null

  const disconnect = () => {
    observer?.disconnect()
    observer = null
  }

  watch(
    container,
    element => {
      disconnect()
      if (!element) return
      width.value = element.clientWidth
      observer = new ResizeObserver(entries => {
        const next = Math.round(entries[0]?.contentRect.width ?? 0)
        if (next !== width.value) width.value = next
      })
      observer.observe(element)
    },
    { immediate: true, flush: 'post' }
  )
  onBeforeUnmount(disconnect)

  return computed(() => marketColumnCount(width.value, cardCount.value))
}
