type CloseGuard = () => Promise<boolean>
const closeGuards = new Map<CloseGuard, () => void>()

// 页面注册自己的保存守卫；退出协调器在关闭后端之前统一等待。
export const registerAppCloseGuard = (guard: CloseGuard, cancel: () => void) => {
  closeGuards.set(guard, cancel)
  return () => closeGuards.delete(guard)
}

export const prepareAppClose = async (): Promise<boolean> => {
  for (const guard of [...closeGuards.keys()]) {
    if (!(await guard())) return false
  }
  return true
}

export const cancelAppClose = () => {
  for (const cancel of closeGuards.values()) cancel()
}
