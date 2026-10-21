export const createAnimationFrameScheduler = (
  requestFrame: typeof requestAnimationFrame,
  cancelFrame: typeof cancelAnimationFrame
) => {
  let pendingFrameId: number | null = null

  const request = (callback: FrameRequestCallback): boolean => {
    if (pendingFrameId !== null) {
      return false
    }

    pendingFrameId = requestFrame(timestamp => {
      pendingFrameId = null
      callback(timestamp)
    })
    return true
  }

  const cancel = () => {
    if (pendingFrameId === null) {
      return
    }

    cancelFrame(pendingFrameId)
    pendingFrameId = null
  }

  return { request, cancel }
}
