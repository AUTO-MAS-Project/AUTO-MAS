import { ref } from 'vue'

import { ApiError, Emulator20Service } from '@/api'
import type {
  Emulator2AvdApkInstallOut,
  Emulator2AvdInstanceOptionsOut,
  Emulator2AvdStatusOut,
  Emulator2PathAddOut,
} from '@/api'
import { t } from '@/i18n'
import type { AvdOptionsForm } from '@/views/Emulator/avdLogic'

/**
 * 生成客户端在非 2xx 时抛 ``ApiError``，后端的说明在 ``error.body.message``；取不到就用兜底文案。
 * 其余异常（网络断开等）用它自己的消息。
 */
const errorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof ApiError) {
    const body: unknown = error.body
    if (
      body &&
      typeof body === 'object' &&
      'message' in body &&
      typeof body.message === 'string' &&
      body.message
    ) {
      return body.message
    }
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}

/**
 * 魔改 AVD 客户端：根目录的组件状态与开机前检查、添加根目录，实例选项与安装 APK。
 * 组件随模拟器内测包提供，MAS 不下载。
 *
 * 业务失败走 ``code !== 200`` + ``message``（HTTP 仍是 200），HTTP 失败走 ``ApiError``；两种都抛带
 * 说明的 Error，取不到说明时用词表里的兜底文案。添加根目录的「没办成」（如已添加）不算接口失败，
 * 原样返回给调用方。``loading`` 表示有请求在飞，``error`` 是最近一次失败的说明。
 */
export function useAvdApi() {
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
      const detail = errorMessage(caught, t(fallbackKey))
      error.value = detail
      throw new Error(detail)
    } finally {
      inFlight -= 1
      loading.value = inFlight > 0
    }
  }

  /** ``refresh``：用户点「检查」时跳过硬件加速与 Vulkan 检查的缓存 */
  const getStatus = (root: string, refresh = false): Promise<Emulator2AvdStatusOut> =>
    call(
      () => Emulator20Service.avdStatusApiEmulator2AvdStatusPost({ root, refresh }),
      'emulator2.avd.toast.statusFailed'
    )

  /** 把组件已齐的根目录加进配置。``ok=false`` 带 ``reason``（如 ``already_added``）原样返回。 */
  const addRoot = (emulatorId: string, root: string): Promise<Emulator2PathAddOut> =>
    call(
      () =>
        Emulator20Service.addPathApiEmulator2PathsAddPost({
          emulatorId,
          installPath: root,
          alias: null,
        }),
      'emulator2.avd.toast.addFailed'
    )

  const getInstanceOptions = (
    emulatorId: string,
    slot: string
  ): Promise<Emulator2AvdInstanceOptionsOut> =>
    call(
      () =>
        Emulator20Service.avdInstanceOptionsApiEmulator2AvdInstanceOptionsPost({
          emulatorId,
          slot,
        }),
      'emulator2.avd.toast.optionsLoadFailed'
    )

  const setInstanceOptions = (
    emulatorId: string,
    slot: string,
    changes: Partial<AvdOptionsForm>
  ): Promise<Emulator2AvdInstanceOptionsOut> =>
    call(
      () =>
        Emulator20Service.avdSetInstanceOptionsApiEmulator2AvdInstanceOptionsSetPost({
          emulatorId,
          slot,
          ...changes,
        }),
      'emulator2.avd.toast.optionsFailed'
    )

  /** 在开着的实例里装一个本地 .apk，装完才返回（大安装包要几分钟） */
  const installApk = (
    emulatorId: string,
    slot: string,
    apkPath: string
  ): Promise<Emulator2AvdApkInstallOut> =>
    call(
      () =>
        Emulator20Service.avdInstallApkApiEmulator2AvdInstanceApkInstallPost({
          emulatorId,
          slot,
          apkPath,
        }),
      'emulator2.avd.toast.apkFailed'
    )

  return {
    loading,
    error,
    getStatus,
    addRoot,
    getInstanceOptions,
    setInstanceOptions,
    installApk,
  }
}
