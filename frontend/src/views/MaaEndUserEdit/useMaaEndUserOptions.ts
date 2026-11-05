import { ref } from 'vue'
import type { ComboBoxItem, MaaEndAutoCollectGroup, MaaEndInventoryOptions } from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'
import type { MaaEndEssenceTargetGroup } from '@/utils/maaEndProtocolSpace'

export const useMaaEndUserOptions = (
  scriptId: string,
  scriptPath: () => string,
  controllerType: () => string | null
) => {
  const { getMaaEndOptions } = useScriptApi()
  const maaEndOptionsLoading = ref(false)
  const maaEndOptionsLoaded = ref(false)
  const controllerProtocol = ref<string | null>(null)
  const presetSupported = ref(true)
  const resourceOptions = ref<Array<{ label: string; value: string }>>([])
  const crisisDrillsOptions = ref<ComboBoxItem[]>([])
  const essenceLocationOptions = ref<ComboBoxItem[]>([])
  const essenceMenuOptions = ref<ComboBoxItem[]>([])
  const autoCollectGroups = ref<MaaEndAutoCollectGroup[]>([])
  const inventoryOptions = ref<MaaEndInventoryOptions | null>(null)
  const essenceTargetWeaponGroups = ref<MaaEndEssenceTargetGroup[]>([])

  const loadMaaEndOptions = async () => {
    if (!scriptPath().trim()) return
    maaEndOptionsLoading.value = true
    try {
      const response = await getMaaEndOptions(scriptId)
      if (response?.code === 200) {
        crisisDrillsOptions.value = response.crisisDrills ?? []
        autoCollectGroups.value = response.autoCollectGroups ?? []
        inventoryOptions.value = response.inventory ?? null
        essenceLocationOptions.value = response.essenceLocations
        essenceMenuOptions.value = response.essenceMenus ?? []
        essenceTargetWeaponGroups.value = response.essenceTargetWeaponGroups ?? []
        controllerProtocol.value = response.controllerTypes[controllerType() ?? ''] ?? null
        resourceOptions.value =
          controllerProtocol.value === 'Win32'
            ? (response.servers ?? []).flatMap(item =>
                item.value === null ? [] : [{ label: item.label, value: item.value }]
              )
            : [{ label: '官服', value: '官服' }]
        presetSupported.value = controllerProtocol.value === 'Win32'
        maaEndOptionsLoaded.value = true
      }
    } finally {
      maaEndOptionsLoading.value = false
    }
  }

  return {
    maaEndOptionsLoading,
    maaEndOptionsLoaded,
    controllerProtocol,
    presetSupported,
    resourceOptions,
    crisisDrillsOptions,
    essenceLocationOptions,
    essenceMenuOptions,
    autoCollectGroups,
    inventoryOptions,
    essenceTargetWeaponGroups,
    loadMaaEndOptions,
  }
}
