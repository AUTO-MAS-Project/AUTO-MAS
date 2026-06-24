const LOW_SPEED_BYTES_PER_SECOND = 50 * 1024
const LOW_SPEED_DURATION_MS = 10_000

export const createLowSpeedDetector = () => {
  let lowSpeedStartedAt: number | null = null
  let prompted = false

  return {
    update(source: string, speed: number, now = Date.now()) {
      if (source !== 'GitHub' || speed <= 0 || speed >= LOW_SPEED_BYTES_PER_SECOND) {
        lowSpeedStartedAt = null
        return false
      }
      lowSpeedStartedAt ??= now
      if (!prompted && now - lowSpeedStartedAt >= LOW_SPEED_DURATION_MS) {
        prompted = true
        return true
      }
      return false
    },
    suppress() {
      prompted = true
    },
    reset() {
      lowSpeedStartedAt = null
      prompted = false
    },
  }
}
