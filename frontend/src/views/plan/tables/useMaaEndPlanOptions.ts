import { onMounted, ref } from 'vue'
import type { ComboBoxItem, MaaEndConfig } from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'
import type { MaaEndEssenceTargetGroup } from '@/utils/maaEndProtocolSpace'

export const useMaaEndPlanOptions = () => {
  const { getScripts, getMaaEndOptions } = useScriptApi()
  const crisisDrillsOptions = ref<ComboBoxItem[]>([])
  const essenceLocationOptions = ref<ComboBoxItem[]>([])
  const essenceMenuOptions = ref<ComboBoxItem[]>([])
  const essenceTargetWeaponGroups = ref<MaaEndEssenceTargetGroup[]>([])
  const essenceOptionsLoading = ref(false)
  const essenceOptionsLoaded = ref(false)

  const loadOptions = async () => {
    essenceOptionsLoading.value = true
    try {
      const scripts = await getScripts(false)
      const configuredMaaEndScripts = scripts.filter(script => {
        if (script.type !== 'MaaEnd') return false
        const config = script.config as MaaEndConfig
        return Boolean(config.Info?.Path?.trim())
      })
      const responses = await Promise.all(
        configuredMaaEndScripts.map(script => getMaaEndOptions(script.uid))
      )
      const crisisByValue = new Map<string, ComboBoxItem>()
      const optionsByValue = new Map<string, ComboBoxItem>()
      const menusByValue = new Map<string, ComboBoxItem>()
      const groupsByValue = new Map<string, MaaEndEssenceTargetGroup>()
      responses.forEach(response => {
        if (response?.code !== 200) return
        response.crisisDrills?.forEach(option => {
          if (option.value && !crisisByValue.has(option.value))
            crisisByValue.set(option.value, option)
        })
        response?.essenceLocations.forEach(option => {
          if (option.value && !optionsByValue.has(option.value)) {
            optionsByValue.set(option.value, option)
          }
        })
        response?.essenceMenus?.forEach(option => {
          if (option.value && !menusByValue.has(option.value)) {
            menusByValue.set(option.value, option)
          }
        })
        response?.essenceTargetWeaponGroups?.forEach(group => {
          const current = groupsByValue.get(group.value)
          if (!current) {
            groupsByValue.set(group.value, { ...group, options: [...group.options] })
            return
          }
          const values = new Set(current.options.map(option => option.value))
          current.options.push(
            ...group.options.filter(option => option.value && !values.has(option.value))
          )
        })
      })
      crisisDrillsOptions.value = [...crisisByValue.values()]
      essenceLocationOptions.value = [...optionsByValue.values()]
      essenceMenuOptions.value = menusByValue.size
        ? [...menusByValue.values()]
        : [{ label: '指定地点', value: 'Location' }]
      essenceTargetWeaponGroups.value = [...groupsByValue.values()]
    } finally {
      essenceOptionsLoading.value = false
      essenceOptionsLoaded.value = true
    }
  }

  onMounted(loadOptions)

  return {
    crisisDrillsOptions,
    essenceLocationOptions,
    essenceMenuOptions,
    essenceTargetWeaponGroups,
    essenceOptionsLoading,
    essenceOptionsLoaded,
  }
}
