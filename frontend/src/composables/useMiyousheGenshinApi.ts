import { ref } from 'vue'
import {
  ApiError,
  GameSignService,
  type MiyousheGenshinAccountOut,
  type MiyousheGenshinRoleOut,
} from '@/api'

export class MiyousheGenshinApiError extends Error {
  constructor(public readonly reason: string) {
    super(reason)
  }
}

const normalizeError = (error: unknown): MiyousheGenshinApiError => {
  if (error instanceof MiyousheGenshinApiError) return error
  if (error instanceof ApiError) {
    const body: unknown = error.body
    if (body && typeof body === 'object' && 'reason' in body && typeof body.reason === 'string') {
      return new MiyousheGenshinApiError(body.reason)
    }
  }
  return new MiyousheGenshinApiError('network_error')
}

/** 米游社原神登录只读取账号元信息和角色，不向前端传递凭据。 */
export function useMiyousheGenshinApi() {
  const accountsLoading = ref(false)
  const rolesLoading = ref(false)
  const error = ref<MiyousheGenshinApiError | null>(null)
  let accountsRequest = 0
  let rolesRequest = 0

  const getAccounts = async (): Promise<MiyousheGenshinAccountOut[]> => {
    const request = ++accountsRequest
    accountsLoading.value = true
    error.value = null
    try {
      const response =
        await GameSignService.getMiyousheGenshinAccountsApiToolsMiyousheGenshinAccountsPost()
      if (response.code !== 200) {
        throw new MiyousheGenshinApiError(response.reason || 'upstream_rejected')
      }
      return response.data || []
    } catch (cause) {
      const failure = normalizeError(cause)
      if (request === accountsRequest) error.value = failure
      throw failure
    } finally {
      if (request === accountsRequest) accountsLoading.value = false
    }
  }

  const getRoles = async (accountUid: string): Promise<MiyousheGenshinRoleOut[]> => {
    const request = ++rolesRequest
    rolesLoading.value = true
    error.value = null
    try {
      const response =
        await GameSignService.getMiyousheGenshinRolesApiToolsMiyousheGenshinRolesPost({
          account_uid: accountUid,
        })
      if (response.code !== 200) {
        throw new MiyousheGenshinApiError(response.reason || 'upstream_rejected')
      }
      return response.data || []
    } catch (cause) {
      const failure = normalizeError(cause)
      if (request === rolesRequest) error.value = failure
      throw failure
    } finally {
      if (request === rolesRequest) rolesLoading.value = false
    }
  }

  return { accountsLoading, rolesLoading, error, getAccounts, getRoles }
}
