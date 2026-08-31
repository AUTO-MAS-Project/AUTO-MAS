import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type ComboBoxItem } from '@/api'

export const useEmulatorDeviceOptions = () => {
  const emulatorDeviceLoading = ref(false)
  const emulatorDeviceOptions = ref<ComboBoxItem[]>([])
  const deviceOptionsCache = new Map<string, ComboBoxItem[]>()
  let requestSequence = 0

  const clearEmulatorDeviceOptions = () => {
    requestSequence += 1
    deviceOptionsCache.clear()
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

    const cachedOptions = deviceOptionsCache.get(emulatorId)
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
        deviceOptionsCache.set(emulatorId, options)
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
