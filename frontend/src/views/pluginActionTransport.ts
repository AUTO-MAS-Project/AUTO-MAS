export class PluginWebSocketCommandError extends Error {
  constructor(
    message: string,
    readonly wasSent: boolean
  ) {
    super(message)
    this.name = 'PluginWebSocketCommandError'
  }
}

const HTTP_REPLAY_SAFE_ENDPOINTS = new Set(['plugins.get'])

export const isPluginActionHttpReplaySafe = (endpoint: string): boolean =>
  HTTP_REPLAY_SAFE_ENDPOINTS.has(endpoint)

interface PluginActionRequestOptions<T> {
  endpoint: string
  sendOverWebSocket: () => Promise<T>
  sendOverHttp: () => Promise<T>
  onHttpFallback?: (error: unknown) => void
  onHttpReplaySuppressed?: (error: unknown) => void
}

export const requestPluginActionWithFallback = async <T>({
  endpoint,
  sendOverWebSocket,
  sendOverHttp,
  onHttpFallback,
  onHttpReplaySuppressed,
}: PluginActionRequestOptions<T>): Promise<T> => {
  try {
    return await sendOverWebSocket()
  } catch (error) {
    // Unknown errors are treated as possibly sent. Replaying a mutation is only
    // allowed when the transport can prove that WebSocket.send was not accepted.
    const wasSent = error instanceof PluginWebSocketCommandError ? error.wasSent : true
    if (!wasSent || isPluginActionHttpReplaySafe(endpoint)) {
      onHttpFallback?.(error)
      return await sendOverHttp()
    }

    onHttpReplaySuppressed?.(error)
    throw error
  }
}
