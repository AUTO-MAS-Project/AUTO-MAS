import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Emulator20Service, Service, type ComboBoxItem } from '@/api'
import { markModAvdOptions } from '@/views/Emulator/avdLogic'

/**
 * 实例下拉的缓存放在模块级、跨页面共用。
 *
 * 六个脚本编辑页各自 new 一份 composable，页内缓存只对"同一页里反复切换模拟器"有用；
 * 用户在几个脚本之间来回点时，每进一页都要重新问一遍后端，下拉框先显示裸设备号、
 * 再跳成名字。实例名几乎不变，缓存一分钟足够；模拟器页增删实例时显式作废。
 */
const DEVICE_OPTIONS_TTL_MS = 60_000

/** 下拉的一项；魔改 AVD 实例在非 M9A 脚本里 ``disabled`` */
export type EmulatorDeviceOption = ComboBoxItem & { disabled?: boolean }

const sharedDeviceOptions = new Map<
  string,
  { options: EmulatorDeviceOption[]; expiresAt: number }
>()

const readShared = (emulatorId: string): EmulatorDeviceOption[] | undefined => {
  const entry = sharedDeviceOptions.get(emulatorId)
  if (!entry) return undefined
  if (Date.now() >= entry.expiresAt) {
    sharedDeviceOptions.delete(emulatorId)
    return undefined
  }
  return entry.options
}

/** 模拟器页增删了实例 / 路径之后调用，让脚本页下次重新拉列表。 */
export const invalidateEmulatorDeviceOptions = (emulatorId?: string): void => {
  if (emulatorId) sharedDeviceOptions.delete(emulatorId)
  else sharedDeviceOptions.clear()
}

/**
 * Emulator 2.0 配置里哪些设备号是魔改 AVD。下拉只有名字，类型要另问一次设备表；不是 Emulator 2.0
 * 配置、或者问失败，都当没有魔改 AVD（保存与运行时后端还会再拦一次）。
 */
const loadModAvdSlots = async (emulatorId: string): Promise<Set<string>> => {
  try {
    const response = await Emulator20Service.listDevicesApiEmulator2DevicesPost({
      emulatorId,
      withSettings: false,
    })
    if (response?.code !== 200) return new Set()
    return new Set(
      (response.devices ?? [])
        .filter(device => device.realType === 'avd' && device.slot)
        .map(device => device.slot)
    )
  } catch {
    return new Set()
  }
}

/**
 * 用这个下拉的都是 MAA / SRC / MaaEnd / BAAH / 通用脚本页，不是 M9A：魔改 AVD 目前只支持 M9A，
 * 它的实例在这里置灰并写明原因。
 */
export const useEmulatorDeviceOptions = () => {
  const emulatorDeviceLoading = ref(false)
  const emulatorDeviceOptions = ref<EmulatorDeviceOption[]>([])
  let requestSequence = 0

  /** 模拟器选择被清空：丢掉本页的选项、作废在飞的请求。共享缓存不动，那是别的页面的。 */
  const clearEmulatorDeviceOptions = () => {
    requestSequence += 1
    emulatorDeviceOptions.value = []
    emulatorDeviceLoading.value = false
  }

  const loadEmulatorDeviceOptions = async (emulatorId: string) => {
    const requestId = ++requestSequence
    emulatorDeviceOptions.value = []

    if (!emulatorId) {
      emulatorDeviceLoading.value = false
      return
    }

    const cachedOptions = readShared(emulatorId)
    if (cachedOptions) {
      emulatorDeviceOptions.value = cachedOptions
      emulatorDeviceLoading.value = false
      return
    }

    emulatorDeviceLoading.value = true
    try {
      const response = await Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({
        emulatorId,
      })

      if (requestId !== requestSequence) return

      if (response.code === 200) {
        const modAvdSlots = await loadModAvdSlots(emulatorId)
        if (requestId !== requestSequence) return
        const options = markModAvdOptions(
          response.data || [],
          value => value !== null && modAvdSlots.has(value),
          false,
          t('emulator2.avd.m9aOnly')
        )
        sharedDeviceOptions.set(emulatorId, {
          options,
          expiresAt: Date.now() + DEVICE_OPTIONS_TTL_MS,
        })
        emulatorDeviceOptions.value = options
      } else {
        message.error(response.message || '加载模拟器实例选项失败')
      }
    } catch (error) {
      if (requestId !== requestSequence) return

      const errorMessage = error instanceof Error ? error.message : String(error)
      message.error(t('misc.couldNotLoadEmulator', { p0: errorMessage }))
    } finally {
      if (requestId === requestSequence) {
        emulatorDeviceLoading.value = false
      }
    }
  }

  return {
    emulatorDeviceLoading,
    emulatorDeviceOptions,
    clearEmulatorDeviceOptions,
    loadEmulatorDeviceOptions,
  }
}
