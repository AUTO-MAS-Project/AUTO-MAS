export interface DesktopSessionCheck {
  code: string
  ok: boolean
  required: boolean
  value: string | number | boolean | null
}

export const MAX_DESKTOP_SESSION_TARGETS = 100

export const DESKTOP_SESSION_REPAIRS = [
  'child_enabled',
  'rdp_local_disabled',
  'term_service_disabled',
  'term_service_stopped',
] as const

export type DesktopSessionRepair = (typeof DESKTOP_SESSION_REPAIRS)[number]

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
  repairPlan?: DesktopSessionRepair[]
  sessionId?: number
  size?: [number, number]
  code?: string
  credentialWarning?: 'credential_save_failed'
  authenticationFailure?: { time: string; status: string; substatus: string }
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
  executionSession?: 'main'
}

export type DesktopSessionPromptTarget = Pick<DesktopQueueResult, 'label' | 'targetKind'>

export type DesktopSessionPromptContent =
  | { kind: 'dispatch'; main: DesktopSessionPromptTarget[]; desktop: DesktopSessionPromptTarget[] }
  | { kind: 'takeover' | 'close' | 'close-adopted' | 'close-failed' }

export type DesktopSessionPrompt = DesktopSessionPromptContent & { id: number }

export type DesktopSessionPromptAction =
  | 'cancel'
  | 'acknowledge'
  | 'split'
  | 'desktop'
  | 'takeover'
  | 'disconnect'
  | 'logoff'

export interface DesktopSessionStartResult {
  code?: string
  queues: DesktopQueueResult[]
}
