import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref } from 'vue'
import { useEventListener } from '@vueuse/core'
import { OpenAPI } from '@/api'
import { getMysteryDate } from '@/utils/mysteryAccess'

/** 后端 /api/mystery 的统一响应结构：业务码在 body 里，HTTP 状态始终是 200。 */
interface MysteryPayload {
  code: number
  status: string
  message: string
  unlocked: boolean
  unlockedDate: string
}

/**
 * 调用神秘入口后端接口。
 *
 * 解锁状态由后端校验并持久化，前端不再自行判断口令，避免两处算法各算一份。
 * 后端沿用 `code` 表达业务结果，所以 HTTP 成功不代表业务成功，交由调用方判 `code`。
 */
const request = async (path: string, init?: RequestInit): Promise<MysteryPayload> => {
  const base = OpenAPI.BASE || 'http://localhost:36163'
  const response = await fetch(`${base}/api/mystery/${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...init?.headers },
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return (await response.json()) as MysteryPayload
}

export const useMysteryStore = defineStore('mystery', () => {
  const unlockedDate = ref('')
  const today = ref(getMysteryDate())
  const unlocked = computed(() => unlockedDate.value === today.value)
  const initialized = ref(false)
  const saving = ref(false)
  let loadPromise: Promise<void> | null = null
  let expiryTimer: ReturnType<typeof setTimeout> | undefined

  const refreshDate = () => {
    const now = new Date()
    today.value = getMysteryDate(now)
    clearTimeout(expiryTimer)
    const nextMidnight = new Date(`${today.value}T00:00:00+08:00`).getTime() + 24 * 60 * 60 * 1000
    expiryTimer = setTimeout(refreshDate, nextMidnight - now.getTime())
  }

  // 零点主动锁回；窗口从后台或休眠恢复时再同步一次日期。
  refreshDate()
  if (typeof document !== 'undefined') {
    useEventListener(document, 'visibilitychange', refreshDate)
  }
  onScopeDispose(() => clearTimeout(expiryTimer))

  const load = async (): Promise<void> => {
    refreshDate()
    if (initialized.value) return
    if (loadPromise) return loadPromise

    loadPromise = (async () => {
      try {
        const payload = await request('status')
        if (payload.code !== 200) throw new Error(payload.message)
        unlockedDate.value = payload.unlockedDate ?? ''
        initialized.value = true
      } finally {
        loadPromise = null
      }
    })()

    return loadPromise
  }

  /**
   * 提交口令。
   *
   * 口令不正确（后端 400）返回 false 由页面提示，其余失败继续抛出，
   * 让页面能区分「密钥不对」与「服务异常」两种提示。
   */
  const unlock = async (accessCode: string): Promise<boolean> => {
    await load()
    if (saving.value) return false

    saving.value = true
    try {
      const payload = await request('unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accessCode }),
      })
      if (payload.code === 400) return false
      if (payload.code !== 200) throw new Error(payload.message)

      unlockedDate.value = payload.unlockedDate ?? ''
      refreshDate()
      return unlocked.value
    } finally {
      saving.value = false
    }
  }

  const lock = async (): Promise<void> => {
    await load()
    if (saving.value) return

    saving.value = true
    try {
      const payload = await request('lock', { method: 'POST' })
      if (payload.code !== 200) throw new Error(payload.message)
      unlockedDate.value = ''
    } finally {
      saving.value = false
    }
  }

  return { unlocked, initialized, saving, load, unlock, lock }
})
