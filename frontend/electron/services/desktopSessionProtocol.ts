export interface DesktopSessionCheck {
  code: string
  ok: boolean
  required: boolean
  value: string | number | boolean | null
}

export const MAX_DESKTOP_SESSION_TARGETS = 100

export const DESKTOP_SESSION_CREDENTIAL_ERRORS: ReadonlySet<string> = new Set([
  'password_required',
  'password_invalid',
  'credential_unreadable',
  'account_mismatch',
  'rdp_authentication_failed',
])

export type DesktopSessionConnectResult =
  | 'connected'
  | 'cancelled'
  | 'failed'
  | 'preview_unavailable'
  | 'setup_required'
  | 'credentials_rejected'
  | 'login_state_save_failed'

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

/** 密码只在设置页到主进程的本次连接中传递；空字符串表示显式无密码连接。 */
export interface DesktopSessionFirstLogin {
  mode: DesktopSessionRequest['mode']
  resolution: DesktopSessionRequest['resolution']
  forTask: boolean
  password: string
}

export type DesktopSessionPendingRequest = Omit<DesktopSessionRequest, 'password'> & {
  taskConnectId?: number
  forTask: boolean
}

export type DesktopSessionStartRequest = DesktopSessionRequest & { taskConnectId?: number }

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
  reason?: 'admin_required' | 'unsupported_config' | 'plugin_unavailable' | null
  executionSession?: 'main'
}

export type DesktopSessionPromptTarget = Pick<DesktopQueueResult, 'label' | 'targetKind' | 'reason'>

export interface DesktopSessionCloseRisk {
  activeTasks: boolean
  unmanagedPrograms: boolean | null
}

export type DesktopSessionPromptContent =
  | { kind: 'dispatch'; main: DesktopSessionPromptTarget[]; desktop: DesktopSessionPromptTarget[] }
  | { kind: 'close' | 'close-adopted' | 'quit'; risk: DesktopSessionCloseRisk }
  | { kind: 'takeover' | 'close-failed' }

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
