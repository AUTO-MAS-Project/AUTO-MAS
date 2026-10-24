import { translate as t } from '@/i18n'
import { computed, ref } from 'vue'
import { queryOptions, useQuery, useQueryClient } from '@tanstack/vue-query'
import { Emulator20Service, Service, type ComboBoxItem, type Emulator2DeviceItem } from '@/api'
import { queryClient } from '@/services/queryClient'
import { queryRequest } from '@/utils/queryRequest'

const DEVICE_QUERY_KEY = ['emulator-device-options'] as const

export type EmulatorDeviceOption = ComboBoxItem & { disabled?: boolean }

/**
 * 魔改 AVD 目前只支持 MFW 脚本和 MAA：不支持的脚本，设备下拉里的魔改 AVD 实例置灰并在名称后写明原因。
 * ``isModAvd`` 判断某个设备号是不是魔改 AVD；``allowed`` 为 true（MAA）时原样返回。MFW 脚本页不经过这里。
 * 后端保存与运行时也会拦，这里只是让用户选之前就看到。
 */
const markModAvdOptions = <T extends ComboBoxItem>(
  options: T[],
  isModAvd: (value: string | null) => boolean,
  allowed: boolean,
  hint: string
): (T & { disabled?: boolean })[] => {
  if (allowed) return options
  return options.map(option =>
    isModAvd(option.value)
      ? { ...option, label: `${option.label}（${hint}）`, disabled: true }
      : option
  )
}

const loadEmulatorType = async (emulatorId: string, parentSignal: AbortSignal) => {
  const queryKey = [...DEVICE_QUERY_KEY, emulatorId, 'type']
  const cancel = () => {
    void queryClient.cancelQueries({ queryKey, exact: true })
  }
  parentSignal.throwIfAborted()
  parentSignal.addEventListener('abort', cancel, { once: true })
  try {
    return await queryClient.fetchQuery({
      queryKey,
      // 配置类型延续原有缓存寿命，只有写入失效才重读；不随设备列表每分钟重读。
      staleTime: Infinity,
      gcTime: Infinity,
      queryFn: async ({ signal }) => {
        const response = await queryRequest(signal, () =>
          Service.getEmulatorApiEmulatorGetPost({ emulatorId })
        )
        if (response.code !== 200)
          throw new Error(response.message || t('edit.couldNotLoadEmulator'))
        return response.data[emulatorId]?.Info?.Type ?? ''
      },
    })
  } finally {
    parentSignal.removeEventListener('abort', cancel)
  }
}

const deviceOptionsQuery = (emulatorId: string) =>
  queryOptions({
    queryKey: [...DEVICE_QUERY_KEY, emulatorId, 'options'],
    staleTime: 60_000,
    meta: { notifyOnError: true },
    queryFn: async ({ signal }) => {
      const response = await queryRequest(signal, () =>
        Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({ emulatorId })
      )
      if (response.code !== 200) {
        throw new Error(response.message || t('apiErrors.emulatorDevicesFailed'))
      }
      let devices: Emulator2DeviceItem[] = []
      // 类型/设备属性读取仍按原行为降级；列表可用时不因附属信息失败阻断选择。
      try {
        if ((await loadEmulatorType(emulatorId, signal)) === 'emulator2') {
          const detail = await queryRequest(signal, () =>
            Emulator20Service.listDevicesApiEmulator2DevicesPost({
              emulatorId,
              withSettings: false,
            })
          )
          if (detail.code === 200) devices = detail.devices ?? []
        }
      } catch (error) {
        if (signal.aborted) throw error
      }
      return { emulatorId, options: response.data ?? [], devices }
    },
  })

/** 同一配置共享原始设备数据；是否允许魔改 AVD 由每个编辑页本地派生。 */
export const useEmulatorDeviceOptions = ({
  allowModAvd = false,
}: { allowModAvd?: boolean } = {}) => {
  const client = useQueryClient()
  const emulatorId = ref('')
  const query = useQuery(
    computed(() => ({
      ...deviceOptionsQuery(emulatorId.value),
      enabled: Boolean(emulatorId.value),
    }))
  )

  const emulatorDeviceOptions = computed<EmulatorDeviceOption[]>(() => {
    if (
      !emulatorId.value ||
      query.data.value?.emulatorId !== emulatorId.value ||
      query.isFetching.value ||
      query.isError.value
    )
      return []
    const { options, devices } = query.data.value
    const modAvdSlots = new Set(
      devices.filter(device => device.realType === 'avd').map(device => device.slot)
    )
    return markModAvdOptions(
      options,
      value => value !== null && modAvdSlots.has(value),
      allowModAvd,
      t('emulator2.avd.unsupportedScript')
    )
  })

  const clearEmulatorDeviceOptions = () => {
    emulatorId.value = ''
  }

  const loadEmulatorDeviceOptions = async (id: string) => {
    emulatorId.value = id && id !== '-' ? id : ''
    if (!emulatorId.value) return
    try {
      await client.fetchQuery(deviceOptionsQuery(emulatorId.value))
    } catch {
      // QueryCache 统一提示，取消或失败不打断页面其余初始化。
    }
  }

  return {
    emulatorDeviceLoading: computed(() => Boolean(emulatorId.value) && query.isFetching.value),
    emulatorDeviceOptions,
    clearEmulatorDeviceOptions,
    loadEmulatorDeviceOptions,
  }
}

/** 成功写入后先停止旧读取，再使对应配置的共享数据失效。 */
export async function invalidateEmulatorDeviceOptions(emulatorId?: string) {
  const queryKey = emulatorId ? [...DEVICE_QUERY_KEY, emulatorId] : DEVICE_QUERY_KEY
  await queryClient.cancelQueries({ queryKey })
  await queryClient.invalidateQueries({ queryKey })
}
