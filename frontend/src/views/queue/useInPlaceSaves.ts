import { computed, ref, watch } from 'vue'

/**
 * 子表就地保存的排队与在途计数。
 *
 * - 同一行的保存排队依次发出：后端写入顺序和回包顺序都等于操作顺序，较早的回包不会在
 *   较晚的之后才把旧值写回页面和缓存。不同行之间互不等待。
 * - 保存成功后父层会把新值回写到 props，子表随即用 props 整表替换本地列表；这时如果另一条
 *   编辑还没保存完，它在本地的新值会被 props 里的旧值顶掉。所以子表在 `saving` 为真时
 *   先不替换，全部结束后由这里再调一次 `sync`（期间跳过的刷新也在这时补上）。
 */
export function useInPlaceSaves(sync: () => void) {
  const inFlight = ref(0)
  watch(inFlight, sync)
  const tails = new Map<string, Promise<void>>()

  /** 执行一次就地保存；同一 `rowId` 的调用排队，前一次结束（无论成败）后才开始。 */
  async function queued<R>(rowId: string, save: () => Promise<R>): Promise<R> {
    const previous = tails.get(rowId)
    let settled: Promise<void> | undefined
    inFlight.value++
    try {
      const turn = previous ? previous.then(save) : save()
      settled = turn.then(
        () => {},
        () => {}
      )
      tails.set(rowId, settled)
      return await turn
    } finally {
      if (settled && tails.get(rowId) === settled) tails.delete(rowId)
      inFlight.value--
    }
  }

  return { saving: computed(() => inFlight.value > 0), queued }
}
