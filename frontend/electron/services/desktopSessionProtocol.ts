export interface DesktopSessionCheck {
  code: string
  ok: boolean
  required: boolean
  value: string | number | boolean | null
}

export interface DesktopSessionRequest {
  queueIds: string[]
  mode: 'proxy' | 'native'
  resolution: '1080p' | 'primary'
  password?: string
}

export interface DesktopSessionSnapshot {
  state: 'idle' | 'checking' | 'blocked' | 'connecting' | 'connected' | 'disconnected'
  windowState: 'visible' | 'hidden' | 'minimized'
  checks: DesktopSessionCheck[]
  sessionId?: number
  size?: [number, number]
  code?: string
  busy: boolean
  executing: boolean
  closing?: boolean
  audioSessions?: number
}

export interface DesktopQueueResult {
  queueId: string
  taskId: string
  targetKind: 'queue' | 'script' | 'unknown'
  code: string
  label: string
}

export interface DesktopSessionStartResult {
  code?: string
  queues: DesktopQueueResult[]
}
