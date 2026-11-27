import { shallowRef, watch } from 'vue'
import { useAppInitialization } from './useAppInitialization'
import { getConfig } from '@/utils/config'
import type { DesktopSessionConnectResult } from '../../electron/services/desktopSessionProtocol'

type LoginWaiter = {
  result: Promise<DesktopSessionConnectResult>
  finish: (result: DesktopSessionConnectResult) => void
}

export const pendingDesktopLogin = shallowRef<LoginWaiter>()

export function finishDesktopLogin(result: DesktopSessionConnectResult) {
  pendingDesktopLogin.value?.finish(result)
  pendingDesktopLogin.value = undefined
}

/** 并发启动共享一次登录，各调用方在连接成功后重试自己的原始任务。 */
export async function connectDesktopForTask(): Promise<DesktopSessionConnectResult> {
  const result = await window.electronAPI.desktopSessionConnectForTask?.()
  if (result !== 'setup_required') return result ?? 'failed'
  return requestFirstLogin()
}

/** 自动触发可早于页面就绪。已完成首次登录时沿用现有自动调度的连接要求。 */
export async function promptScheduledDesktopLogin() {
  if (!(await window.electronAPI.desktopSessionSupported?.())) return
  if ((await getConfig({ strict: true })).desktopSessionLoginCompleted === true) return true
  const { isInitialized } = useAppInitialization()
  if (!isInitialized.value) {
    await new Promise<void>(resolve => {
      const stop = watch(isInitialized, ready => {
        if (ready) {
          stop()
          resolve()
        }
      })
    })
  }
  return (await requestFirstLogin()) === 'connected'
}

async function requestFirstLogin(): Promise<DesktopSessionConnectResult> {
  if (pendingDesktopLogin.value) return pendingDesktopLogin.value.result
  let finish!: LoginWaiter['finish']
  const waiting = new Promise<DesktopSessionConnectResult>(resolve => {
    finish = resolve
  })
  pendingDesktopLogin.value = { result: waiting, finish }
  try {
    const { default: router, navigateTo } = await import('@/router')
    await navigateTo('/settings', { query: { tab: 'desktop-session' } })
    if (router.currentRoute.value.path !== '/settings') finishDesktopLogin('cancelled')
  } catch (error) {
    finishDesktopLogin('failed')
    throw error
  }
  return waiting
}
