import { message } from 'ant-design-vue'
import type { ConfigEditIn } from '@/api'
import { Service } from '@/api'

export type ConfigResourceKey =
  | 'Config'
  | 'EmulatorConfig'
  | 'PlanConfig'
  | 'ScriptConfig'
  | 'QueueConfig'
  | 'ToolsConfig'

interface ConfigEditSession {
  resourceKey: ConfigResourceKey
  token: string
  baseVersion: string
  frozen: boolean
  renewTimer: number | null
}

const RENEW_INTERVAL_MS = 10_000

const sessions = new Map<ConfigResourceKey, ConfigEditSession>()
const API_RESOURCE_KEY: Record<ConfigResourceKey, ConfigEditIn['resourceKey']> = {
  Config: 'Config' as ConfigEditIn['resourceKey'],
  EmulatorConfig: 'EmulatorConfig' as ConfigEditIn['resourceKey'],
  PlanConfig: 'PlanConfig' as ConfigEditIn['resourceKey'],
  ScriptConfig: 'ScriptConfig' as ConfigEditIn['resourceKey'],
  QueueConfig: 'QueueConfig' as ConfigEditIn['resourceKey'],
  ToolsConfig: 'ToolsConfig' as ConfigEditIn['resourceKey'],
}

const stopRenewTimer = (session: ConfigEditSession) => {
  if (session.renewTimer == null) return
  window.clearInterval(session.renewTimer)
  session.renewTimer = null
}

const freezeSession = (session: ConfigEditSession, text: string) => {
  session.frozen = true
  stopRenewTimer(session)
  message.warning(text)
}

const renewConfigEditSession = async (session: ConfigEditSession) => {
  const response = await Service.renewConfigEditLeaseApiConfigEditRenewPost({
    resourceKey: API_RESOURCE_KEY[session.resourceKey],
    editLeaseToken: session.token,
  })
  if (response.code !== 200) {
    freezeSession(session, response.message || '配置编辑锁已失效，请重新进入编辑页')
    return false
  }
  if (response.version !== session.baseVersion) {
    freezeSession(session, '配置已被外部修改，请刷新后再保存')
    return false
  }
  return true
}

const startRenewTimer = (session: ConfigEditSession) => {
  stopRenewTimer(session)
  session.renewTimer = window.setInterval(() => {
    void renewConfigEditSession(session)
  }, RENEW_INTERVAL_MS)
}

const acquireConfigEditSession = async (resourceKey: ConfigResourceKey) => {
  const existing = sessions.get(resourceKey)
  if (existing) {
    if (existing.frozen) return null
    return existing
  }

  const response = await Service.acquireConfigEditLeaseApiConfigEditAcquirePost({
    resourceKey: API_RESOURCE_KEY[resourceKey],
  })
  if (response.code !== 200 || !response.editLeaseToken) {
    message.warning(response.message || '有其他用户正在编辑该配置')
    return null
  }

  const session: ConfigEditSession = {
    resourceKey,
    token: response.editLeaseToken,
    baseVersion: response.version,
    frozen: false,
    renewTimer: null,
  }
  sessions.set(resourceKey, session)
  startRenewTimer(session)
  return session
}

const releaseConfigEditSession = async (resourceKey: ConfigResourceKey) => {
  const session = sessions.get(resourceKey)
  if (!session) return
  stopRenewTimer(session)
  sessions.delete(resourceKey)
  try {
    await Service.releaseConfigEditLeaseApiConfigEditReleasePost({
      resourceKey: API_RESOURCE_KEY[resourceKey],
      editLeaseToken: session.token,
    })
  } catch {
    // 离开页面释放锁尽力而为，失败由租约过期自动回收。
  }
}

const markConfigEditSaved = async (resourceKey: ConfigResourceKey) => {
  const session = sessions.get(resourceKey)
  if (!session || session.frozen) return false
  const response = await Service.renewConfigEditLeaseApiConfigEditRenewPost({
    resourceKey: API_RESOURCE_KEY[resourceKey],
    editLeaseToken: session.token,
  })
  if (response.code !== 200) {
    freezeSession(session, response.message || '配置编辑锁已失效，请重新进入编辑页')
    return false
  }
  session.baseVersion = response.version
  startRenewTimer(session)
  return true
}

if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('focus', () => {
    for (const session of sessions.values()) {
      if (!session.frozen) void renewConfigEditSession(session)
    }
  })

  window.addEventListener('beforeunload', () => {
    for (const resourceKey of Array.from(sessions.keys())) {
      void releaseConfigEditSession(resourceKey)
    }
  })
}

export function useConfigEditSession() {
  const ensureConfigEditSession = async (resourceKey: ConfigResourceKey) => {
    const session = await acquireConfigEditSession(resourceKey)
    if (!session || session.frozen) return null
    return {
      editLeaseToken: session.token,
      baseVersion: session.baseVersion,
    }
  }

  return {
    ensureConfigEditSession,
    markConfigEditSaved,
    releaseConfigEditSession,
  }
}
