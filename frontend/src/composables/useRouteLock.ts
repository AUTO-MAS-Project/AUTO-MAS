import { ref } from 'vue'

type RouteBlockCallback = (targetRoute: string) => void

const isRouteLocked = ref(false)
let blockCallback: RouteBlockCallback | null = null

export function useRouteLock() {
  /**
   * 锁定路由切换
   * @param callback 当用户尝试切换路由时的回调函数
   */
  const lockRoute = (callback: RouteBlockCallback) => {
    isRouteLocked.value = true
    blockCallback = callback
  }

  /**
   * 解锁路由切换
   */
  const unlockRoute = () => {
    isRouteLocked.value = false
    blockCallback = null
  }

  /**
   * 检查路由是否被锁定
   */
  const checkRouteLocked = () => {
    return isRouteLocked.value
  }

  /**
   * 触发路由阻止回调
   * @param targetRoute 用户尝试访问的目标路由
   */
  const triggerBlockCallback = (targetRoute: string) => {
    if (blockCallback) {
      blockCallback(targetRoute)
    }
  }

  return {
    isRouteLocked,
    lockRoute,
    unlockRoute,
    checkRouteLocked,
    triggerBlockCallback,
  }
}
