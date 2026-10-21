import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Service, type ZzzOdInstanceOut } from '@/api'
export function useZzzodInstances(scriptId: string) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('ZZZ-OD用户编辑')
  // ══ 实例列表（原生来源「选择实例」来源）══
  const instances = ref<ZzzOdInstanceOut[]>([])

  const instancesLoading = ref(false)

  const instanceOptions = computed(() =>
    instances.value.map(item => ({
      label: `${String(item.idx).padStart(2, '0')} - ${item.name}`,
      value: item.idx,
    }))
  )

  const loadInstances = async () => {
    instancesLoading.value = true
    try {
      const resp = await Service.getZzzodInstancesApiApiScriptsZzzodInstancesGet(scriptId)
      if (resp.code !== 200) {
        throw new Error(resp.message || t('edit.zzzodLoadInstancesFailed'))
      }
      instances.value = resp.data || []
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    } finally {
      instancesLoading.value = false
    }
  }
  return { instances, instancesLoading, instanceOptions, loadInstances }
}
