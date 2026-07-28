// useWebSocket.ts - 主 WebSocket 组合式 API 门面
// 连接管理与分发实现见 src/services/websocket；
// 后端进程恢复与关闭流程见 src/composables/useAppLifecycle.ts。

import { connectionInfo, connectionState, request, send } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import type {
  WSConnectionState,
  WSEnvelope,
  WSMessageHandler,
  WSSubscriptionKey,
} from '@/services/websocket/types'

export type { WSConnectionState, WSEnvelope, WSMessageHandler, WSSubscriptionKey }
export { subscribe, unsubscribe, send, request }

export function useWebSocket() {
  return {
    subscribe,
    unsubscribe,
    send,
    request,
    state: connectionState(),
    getConnectionInfo: connectionInfo,
  }
}
