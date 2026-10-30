import { onScopeDispose, readonly, ref } from 'vue'

/**
 * 任务台倒计时的分钟级时钟：模块内单例 + 引用计数。
 * 只有倒计时组件订阅它，页面与卡片的渲染不依赖这个 ref；
 * 最后一个订阅者卸载时停表，路由切走不会留下定时器。
 */
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null
let subscribers = 0

export const useCountdownClock = () => {
  subscribers += 1
  if (!timer) {
    now.value = Date.now()
    timer = setInterval(() => {
      now.value = Date.now()
    }, 60_000)
  }

  onScopeDispose(() => {
    subscribers -= 1
    if (subscribers <= 0 && timer) {
      clearInterval(timer)
      timer = null
    }
  })

  return readonly(now)
}
