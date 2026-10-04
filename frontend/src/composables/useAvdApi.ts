import { Emulator20Service } from '@/api'
import type {
  Emulator2AvdInstallOut,
  Emulator2AvdInstanceOptionsOut,
  Emulator2AvdLicenseOut,
  Emulator2AvdSourcesOut,
  Emulator2AvdStatusOut,
} from '@/api'
import type { AvdOptionsForm } from '@/views/Emulator/avdLogic'

/**
 * 官方模拟器（AVD）客户端：根目录的组件状态与开机前检查、许可协议、下载源测速、后台下载，
 * 以及实例选项。业务失败走 ``code !== 200`` + ``message``（HTTP 仍是 200），这里抛带后端文案的
 * Error；下载开始 / 取消的「没开成」（未同意、空间不足、没有任务）不算接口失败，原样返回给调用方。
 */
export function useAvdApi() {
  const ensureOk = <T extends { code?: number; message?: string }>(
    response: T,
    fallback: string
  ) => {
    if (response.code !== 200) throw new Error(response.message || fallback)
    return response
  }

  /** ``refresh``：用户点「检查」时跳过硬件加速与 Vulkan 检查的缓存 */
  const getStatus = async (root: string, refresh = false): Promise<Emulator2AvdStatusOut> =>
    ensureOk(
      await Emulator20Service.avdStatusApiEmulator2AvdStatusPost({ root, refresh }),
      '读取官方模拟器状态失败'
    )

  const getLicense = async (source?: string | null): Promise<Emulator2AvdLicenseOut> =>
    ensureOk(
      await Emulator20Service.avdLicenseApiEmulator2AvdLicensePost({ source: source || null }),
      '获取许可协议失败'
    )

  const probeSources = async (): Promise<Emulator2AvdSourcesOut> =>
    ensureOk(await Emulator20Service.avdSourcesApiEmulator2AvdSourcesPost(), '下载源测速失败')

  const startInstall = async (params: {
    root: string
    acceptLicense: boolean
    source: string | null
    includeLauncher: boolean
    emulatorId: string
  }): Promise<Emulator2AvdInstallOut> =>
    ensureOk(
      await Emulator20Service.avdInstallStartApiEmulator2AvdInstallStartPost(params),
      '开始下载失败'
    )

  const cancelInstall = async (root: string) =>
    ensureOk(
      await Emulator20Service.avdInstallCancelApiEmulator2AvdInstallCancelPost({ root }),
      '取消下载失败'
    )

  const getInstanceOptions = async (
    emulatorId: string,
    slot: string
  ): Promise<Emulator2AvdInstanceOptionsOut> =>
    ensureOk(
      await Emulator20Service.avdInstanceOptionsApiEmulator2AvdInstanceOptionsPost({
        emulatorId,
        slot,
      }),
      '读取实例选项失败'
    )

  const setInstanceOptions = async (
    emulatorId: string,
    slot: string,
    changes: Partial<AvdOptionsForm>
  ): Promise<Emulator2AvdInstanceOptionsOut> =>
    ensureOk(
      await Emulator20Service.avdSetInstanceOptionsApiEmulator2AvdInstanceOptionsSetPost({
        emulatorId,
        slot,
        ...changes,
      }),
      '保存实例选项失败'
    )

  return {
    getStatus,
    getLicense,
    probeSources,
    startInstall,
    cancelInstall,
    getInstanceOptions,
    setInstanceOptions,
  }
}
