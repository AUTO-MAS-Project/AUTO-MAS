import { ref } from 'vue'
import {
  ApiError,
  Service,
  type ShareAppearanceMineItem,
  type ShareAppearanceUploadItem,
  ShareAppearanceUploadOut,
  type ShareAuthStatusOut,
  type ShareRiskItem,
} from '@/api'
import { translate as t } from '@/i18n'

export type { ShareRiskItem }

/** 当前登录账号在本机的外观上传记录，用于下次给同一外观发新版本。 */
export interface AppearanceUploadRecord {
  appearanceId: string
  fileId: number
  fileKey: string
  displayName: string
  updatedAt: string
}

export interface AppearanceUploadPayload {
  zipPath: string
  displayName: string
  description: string
  changeNote: string
  /** 已上传文件的 ID；传了就给那个文件发新版本。 */
  fileId?: number | null
  /** 封面来源：package 包里的 preview，custom 用 coverPath，inherit 沿用分享站上的封面（只能发新版本）。 */
  coverMode: AppearanceCoverMode
  /** 封面图片路径，coverMode 为 custom 时使用。 */
  coverPath?: string | null
}

export type AppearanceCoverMode = 'package' | 'custom' | 'inherit'

/** 分享站拒绝上传的类别：待审核数超限、名称被占用或内容未变、超过体积上限。 */
export type AppearanceUploadRejection = 'pendingLimit' | 'conflict' | 'tooLarge'

export type MyAppearanceReviewStatus = 'pending' | 'approved' | 'rejected'

/** 当前账号在分享站上的一个外观（含待审核、被驳回的）。 */
export interface MyAppearanceItem {
  fileId: number
  fileKey: string
  displayName: string
  description: string
  status: string
  publishedVersionNo: number | null
  latestVersionNo: number
  latestReviewStatus: MyAppearanceReviewStatus | null
  latestReviewComment: string
  latestHasCover: boolean
  updatedAt: string
}

/** code 沿用后端：401 未登录或已过期，其余为分享站状态码或本地错误。 */
export type ShareCallResult<T> =
  | { ok: true; data: T }
  | { ok: false; code: number; message: string }

export interface AppearanceUploadData {
  fileId: number
  fileKey: string
  versionNo: number
  reviewStatus: 'pending' | 'approved'
  isNewFile: boolean
  appearanceId: string
}

/** code 沿用后端：400 外观包不合法、401 未登录或已过期、409/413/429 分享站拒绝、503 网络失败。 */
export type AppearanceUploadResult =
  | { ok: true; data: AppearanceUploadData }
  | { ok: false; code: number; message: string; reason?: AppearanceUploadRejection }

// 生成客户端在非 2xx 时抛 ApiError，后端的说明在 body.message 里（如 422 的参数校验）
const apiErrorMessage = (err: unknown, fallback: string): { code: number; message: string } => {
  if (err instanceof ApiError) {
    const body: unknown = err.body
    const message =
      body !== null &&
      typeof body === 'object' &&
      'message' in body &&
      typeof body.message === 'string'
        ? body.message
        : fallback
    return { code: err.status, message }
  }
  return { code: 0, message: err instanceof Error ? err.message : fallback }
}

const toMyAppearance = (item: ShareAppearanceMineItem): MyAppearanceItem => ({
  fileId: item.fileId,
  fileKey: item.fileKey ?? '',
  displayName: item.displayName ?? '',
  description: item.description ?? '',
  status: item.status ?? '',
  publishedVersionNo: item.publishedVersionNo ?? null,
  latestVersionNo: item.latestVersionNo ?? 0,
  latestReviewStatus: item.latestReviewStatus ?? null,
  latestReviewComment: item.latestReviewComment ?? '',
  latestHasCover: item.latestHasCover ?? false,
  updatedAt: item.updatedAt ?? '',
})

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

  // 外观包上传：失败不抛异常，把状态码和可展示的原因交给调用方决定怎么提示
  const uploadAppearance = async (
    payload: AppearanceUploadPayload
  ): Promise<AppearanceUploadResult> => {
    loading.value = true
    error.value = null
    try {
      const response = await Service.uploadShareAppearanceApiShareAppearanceUploadPost({
        zipPath: payload.zipPath,
        displayName: payload.displayName,
        description: payload.description,
        changeNote: payload.changeNote,
        fileId: payload.fileId ?? null,
        coverMode: payload.coverMode,
        coverPath: payload.coverMode === 'custom' ? (payload.coverPath ?? null) : null,
      })
      if (response.code !== 200) {
        const message = response.message || t('themeStore.upload.failed')
        error.value = message
        return {
          ok: false,
          code: response.code ?? 500,
          message,
          ...(response.reason ? { reason: response.reason } : {}),
        }
      }
      return {
        ok: true,
        data: {
          fileId: response.fileId ?? 0,
          fileKey: response.fileKey ?? '',
          versionNo: response.versionNo ?? 0,
          reviewStatus:
            response.reviewStatus === ShareAppearanceUploadOut.reviewStatus.APPROVED
              ? 'approved'
              : 'pending',
          isNewFile: response.isNewFile ?? false,
          appearanceId: response.appearanceId ?? '',
        },
      }
    } catch (err) {
      const failure = apiErrorMessage(err, t('themeStore.upload.failed'))
      error.value = failure.message
      return { ok: false, ...failure }
    } finally {
      loading.value = false
    }
  }

  const listAppearanceUploads = async (): Promise<AppearanceUploadRecord[]> => {
    try {
      const response = await Service.listShareAppearanceUploadsApiShareAppearanceUploadsPost()
      if (response.code !== 200) return []
      return (response.data ?? []).map((item: ShareAppearanceUploadItem) => ({
        appearanceId: item.appearanceId,
        fileId: item.fileId,
        fileKey: item.fileKey ?? '',
        displayName: item.displayName ?? '',
        updatedAt: item.updatedAt ?? '',
      }))
    } catch {
      return []
    }
  }

  /** 当前账号在分享站上的全部外观；失败时把状态码交给调用方（401 要刷新登录状态）。 */
  const listMyAppearances = async (): Promise<ShareCallResult<MyAppearanceItem[]>> => {
    try {
      const response = await Service.listMyShareAppearancesApiShareAppearanceMinePost()
      if (response.code !== 200) {
        return {
          ok: false,
          code: response.code ?? 500,
          message: response.message || t('themeStore.mine.loadFailed'),
        }
      }
      return { ok: true, data: (response.data ?? []).map(toMyAppearance) }
    } catch (err) {
      return { ok: false, ...apiErrorMessage(err, t('themeStore.mine.loadFailed')) }
    }
  }

  /** 自己外观某个版本的封面（data URL），不传版本取最新版本。 */
  const getMyAppearanceCover = async (
    fileId: number,
    versionNo?: number
  ): Promise<ShareCallResult<string>> => {
    try {
      const response = await Service.getMyShareAppearanceCoverApiShareAppearanceCoverPost({
        fileId,
        versionNo: versionNo ?? null,
      })
      if (response.code !== 200 || !response.dataUrl) {
        return { ok: false, code: response.code ?? 500, message: response.message ?? '' }
      }
      return { ok: true, data: response.dataUrl }
    } catch (err) {
      return { ok: false, ...apiErrorMessage(err, '') }
    }
  }

  /**
   * 不带封面发新版本时分享站会沿用的那张封面（最近一个未被驳回且带封面的版本）；
   * 没有可沿用的封面时 code 为 404。
   */
  const getInheritableAppearanceCover = async (
    fileId: number
  ): Promise<ShareCallResult<{ dataUrl: string; versionNo: number | null }>> => {
    try {
      const response = await Service.getMyShareAppearanceCoverApiShareAppearanceCoverPost({
        fileId,
        inheritable: true,
      })
      if (response.code !== 200 || !response.dataUrl) {
        return { ok: false, code: response.code ?? 500, message: response.message ?? '' }
      }
      return {
        ok: true,
        data: { dataUrl: response.dataUrl, versionNo: response.versionNo ?? null },
      }
    } catch (err) {
      return { ok: false, ...apiErrorMessage(err, '') }
    }
  }

  const updateMyAppearanceDescription = async (
    fileId: number,
    description: string
  ): Promise<ShareCallResult<MyAppearanceItem>> => {
    try {
      const response =
        await Service.updateMyShareAppearanceDescriptionApiShareAppearanceDescriptionPost({
          fileId,
          description,
        })
      if (response.code !== 200 || !response.data) {
        return {
          ok: false,
          code: response.code ?? 500,
          message: response.message || t('themeStore.mine.descriptionFailed'),
        }
      }
      return { ok: true, data: toMyAppearance(response.data) }
    } catch (err) {
      return { ok: false, ...apiErrorMessage(err, t('themeStore.mine.descriptionFailed')) }
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
    uploadAppearance,
    listAppearanceUploads,
    listMyAppearances,
    getMyAppearanceCover,
    getInheritableAppearanceCover,
    updateMyAppearanceDescription,
  }
}
