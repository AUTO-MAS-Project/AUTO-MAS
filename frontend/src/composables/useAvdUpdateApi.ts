import { ref } from 'vue'

import { Emulator20Service } from '@/api'
import { getApiErrorMessage } from '@/utils/apiError'
import type { Emulator2AvdUpdateActionOut, Emulator2AvdUpdateStatusOut } from '@/api'
import { t } from '@/i18n'

/**
 * 魔改 AVD 更新客户端：状态快照（可顺带查更新）、一键更新。
 *
 * 业务失败走 ``code !== 200`` + ``message``，HTTP 失败走 ``ApiError``，两种都抛带说明的 Error。
 * 更新「没开始」（如有实例开着、已是最新）不算接口失败，``ok=false`` 原样返回。
 * ``loading`` 表示有请求在飞，``error`` 是最近一次失败的说明。
 */
export function useAvdUpdateApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  let inFlight = 0

  const call = async <T extends { code?: number; message?: string }>(
    request: () => Promise<T>,
    fallbackKey: string
  ): Promise<T> => {
    inFlight += 1
    loading.value = true
    error.value = null
    try {
      const response = await request()
      if (response.code !== 200) throw new Error(response.message || t(fallbackKey))
      return response
    } catch (caught) {
      const detail = getApiErrorMessage(caught, t(fallbackKey))
      error.value = detail
      throw new Error(detail)
    } finally {
      inFlight -= 1
      loading.value = inFlight > 0
    }
  }

  /** ``check``：「检查更新」，先强制查一次最新版本（不走缓存、不带 CDK）；不传只读本地状态和缓存 */
  const getStatus = (root: string, check = false): Promise<Emulator2AvdUpdateStatusOut> =>
    call(
      () => Emulator20Service.avdUpdateStatusApiEmulator2AvdUpdateStatusPost({ root, check }),
      'emulator2.avd.update.toast.statusFailed'
    )

  /** 有实例开着或正在开机时后端什么都不动，返回 ``instances_running`` */
  const update = (root: string): Promise<Emulator2AvdUpdateActionOut> =>
    call(
      () => Emulator20Service.avdUpdateApiEmulator2AvdUpdatePost({ root }),
      'emulator2.avd.update.toast.actionFailed'
    )

  return { loading, error, getStatus, update }
}
