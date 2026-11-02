import { ref, watch } from 'vue'
import { getGameDayOffset } from './periodMarkers'

const DAY_MS = 86_400_000

export function useMaaGameDay(getServer: () => string) {
  const now = ref(Date.now())
  watch(
    getServer,
    (server, _previous, onCleanup) => {
      let timer: ReturnType<typeof setTimeout>
      const refresh = () => {
        now.value = Date.now()
        const shifted = now.value + getGameDayOffset(server) * 3_600_000
        const nextDay = (Math.floor(shifted / DAY_MS) + 1) * DAY_MS
        timer = setTimeout(refresh, nextDay - shifted + 1)
      }
      refresh()
      onCleanup(() => clearTimeout(timer))
    },
    { immediate: true, flush: 'sync' }
  )
  return now
}
