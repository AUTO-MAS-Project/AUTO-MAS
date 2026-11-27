import { computed, ref, watch } from 'vue'

/**
 * 子表就地保存的排队与在途计数。
 *
 * - 同一队列同一行的保存排队依次发出：后端写入顺序和回包顺序都等于操作顺序，较早的回包
 *   不会在较晚的之后才把旧值写回页面和缓存。不同行之间互不等待。
 * - 队列放在模块层，不跟子表实例走：切换调度队列会重建子表，旧子表里还排着的保存
 *   不能被新子表后发起的保存插队。
 * - 保存成功后父层会把新值回写到 props，子表随即用 props 整表替换本地列表；这时如果另一条
 *   编辑还没保存完，它在本地的新值会被 props 里的旧值顶掉。所以子表在 `saving` 为真时
 *   先不替换，全部结束后由这里再调一次 `sync`（期间跳过的刷新也在这时补上）。
 */
const inFlight = ref(0)
const tails = new Map<string, Promise<void>>()

/** 执行一次就地保存；同一 `key` 的调用排队，前一次结束（无论成败）后才开始。 */
async function queueInPlaceSave<R>(key: string, save: () => Promise<R>): Promise<R> {
  const previous = tails.get(key)
  let settled: Promise<void> | undefined
  inFlight.value++
  try {
    const turn = previous ? previous.then(save) : save()
    settled = turn.then(
      () => {},
      () => {}
    )
    tails.set(key, settled)
    return await turn
  } finally {
    if (settled && tails.get(key) === settled) tails.delete(key)
    inFlight.value--
  }
}

export function useInPlaceSaves(queueId: () => string, sync: () => void) {
  watch(inFlight, sync)
  return {
    saving: computed(() => inFlight.value > 0),
    queued: <R>(rowId: string, save: () => Promise<R>) =>
      queueInPlaceSave(`${queueId()}:${rowId}`, save),
  }
}
