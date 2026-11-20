import { onMounted, onScopeDispose, ref } from 'vue'
import { onConnected } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import { WS_ID_PLUGIN, WS_PLUGIN_CAPABILITIES_UPDATED } from '@/services/websocket/types'

export function useDesktopSessionAvailability() {
  const available = ref(false)
  let requestId = 0

  async function refresh() {
    const id = ++requestId
    const status = await window.electronAPI
      ?.desktopSessionSupported?.()
      .catch(() => 'unavailable' as const)
    if (id === requestId) available.value = status === 'ready'
  }

  const subscription = subscribe(
    { id: WS_ID_PLUGIN, type: WS_PLUGIN_CAPABILITIES_UPDATED },
    refresh
  )
  const stopConnected = onConnected(refresh)
  onMounted(refresh)
  onScopeDispose(() => {
    requestId++
    unsubscribe(subscription)
    stopConnected()
  })

  return available
}
