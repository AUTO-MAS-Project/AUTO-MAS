import { ref } from 'vue'
import { Service, type ShareAuthStatusOut, type ShareRiskItem } from '@/api'

export type { ShareRiskItem }

export type ShareAuthStatus = ShareAuthStatusOut['authStatus']

export interface ShareAuthState {
  status: ShareAuthStatus
  username: string
  displayName: string
  userCode: string
  verificationUri: string
  interval: number
  message: string
}

export const IDLE_SHARE_AUTH: ShareAuthState = {
  status: 'idle' as ShareAuthStatus,
  username: '',
  displayName: '',
  userCode: '',
  verificationUri: '',
  interval: 5,
  message: '',
}

// 只有被拒绝或已过期时后端才会带回可展示的原因，其余状态的 message 是通用的成功文案
const RESULT_STATUSES: ShareAuthStatus[] = ['denied', 'expired'] as ShareAuthStatus[]

const toAuthState = (response: ShareAuthStatusOut): ShareAuthState => ({
  status: response.authStatus,
  username: response.username ?? '',
  displayName: response.displayName ?? '',
  userCode: response.userCode ?? '',
  verificationUri: response.verificationUri ?? '',
  interval: response.interval ?? 5,
  message: RESULT_STATUSES.includes(response.authStatus) ? (response.message ?? '') : '',
})

export function useShareApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const runAuthCall = async (
    call: () => Promise<ShareAuthStatusOut>
  ): Promise<ShareAuthState | null> => {
    error.value = null
    try {
      const response = await call()
      if (response.code !== 200) {
        error.value = response.message || '配置中心授权失败'
        return null
      }
      return toAuthState(response)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '配置中心授权失败'
      return null
    }
  }

  const getShareAuthStatus = () =>
    runAuthCall(() => Service.getShareAuthStatusApiShareAuthStatusPost())

  const startShareAuth = async () => {
    loading.value = true
    try {
      return await runAuthCall(() => Service.startShareAuthApiShareAuthStartPost())
    } finally {
      loading.value = false
    }
  }

  const pollShareAuth = () => runAuthCall(() => Service.pollShareAuthApiShareAuthPollPost())

  const cancelShareAuth = () => runAuthCall(() => Service.cancelShareAuthApiShareAuthCancelPost())

  // 分享前检查：返回自动脱敏后仍然可疑的配置项，由用户确认
  const inspectShare = async (
    scriptId: string,
    configName: string
  ): Promise<ShareRiskItem[] | null> => {
    error.value = null
    try {
      const response = await Service.inspectScriptShareApiScriptsShareInspectPost({
        scriptId,
        config_name: configName,
      })
      if (response.code !== 200) {
        error.value = response.message || '分享前检查失败'
        return null
      }
      return response.risks ?? []
    } catch (err) {
      error.value = err instanceof Error ? err.message : '分享前检查失败'
      return null
    }
  }

  const uploadShare = async (payload: {
    scriptId: string
    configName: string
    description: string
    acknowledged: boolean
  }): Promise<boolean> => {
    loading.value = true
    error.value = null
    try {
      const response = await Service.uploadScriptToWebApiScriptsUploadWebPost({
        scriptId: payload.scriptId,
        config_name: payload.configName,
        description: payload.description,
        acknowledged: payload.acknowledged,
      })
      if (response.code !== 200) {
        error.value = response.message || '上传失败'
        return false
      }
      return true
    } catch (err) {
      error.value = err instanceof Error ? err.message : '上传失败'
      return false
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    getShareAuthStatus,
    startShareAuth,
    pollShareAuth,
    cancelShareAuth,
    inspectShare,
    uploadShare,
  }
}
