import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type ComboBoxItem } from '@/api'

/**
 * 实例下拉的缓存放在模块级、跨页面共用。
 *
 * 六个脚本编辑页各自 new 一份 composable，页内缓存只对"同一页里反复切换模拟器"有用；
 * 用户在几个脚本之间来回点时，每进一页都要重新问一遍后端，下拉框先显示裸设备号、
 * 再跳成名字。实例名几乎不变，缓存一分钟足够；模拟器页增删实例时显式作废。
 */
const DEVICE_OPTIONS_TTL_MS = 60_000
const sharedDeviceOptions = new Map<string, { options: ComboBoxItem[]; expiresAt: number }>()

const readShared = (emulatorId: string): ComboBoxItem[] | undefined => {
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

export const useEmulatorDeviceOptions = () => {
  const emulatorDeviceLoading = ref(false)
  const emulatorDeviceOptions = ref<ComboBoxItem[]>([])
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
        const options = response.data || []
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
