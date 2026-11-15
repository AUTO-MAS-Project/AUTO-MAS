import { ref, watch } from 'vue'
import { PlanIndexItem, Service, type ComboBoxItem, type PlanGetOut } from '@/api'
import { useI18n } from 'vue-i18n'

export function useMaaPlanData(
  getMode: () => string,
  getPlans: (id: string) => Promise<PlanGetOut>,
  onError: (error: unknown) => void
) {
  const data = ref<PlanGetOut['data'][string] | null>(null)
  const status = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')

  watch(
    getMode,
    async (mode, _previous, onCleanup) => {
      let active = true
      onCleanup(() => {
        active = false
      })
      data.value = null
      if (!mode || mode === 'Fixed') {
        status.value = 'idle'
        return
      }

      status.value = 'loading'
      try {
        const response = await getPlans(mode)
        if (!active) return
        const plan = response.code === 200 ? response.data[mode] : null
        if (!plan) throw new Error('Plan data is missing')
        data.value = plan
        status.value = 'ready'
      } catch (error) {
        if (!active) return
        status.value = 'error'
        onError(error)
      }
    },
    { immediate: true, flush: 'sync' }
  )

  return { data, status }
}

/** MAA 的计划选项按已声明的配置类型查询，固定模式属于插件自身的选择语义。 */
export function useMaaPlanOptions() {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('MAA计划选项')
  const options = ref<ComboBoxItem[]>([{ label: t('core.edit.fixed'), value: 'Fixed' }])
  const load = async () => {
    try {
      const response = await Service.pluginPlanOptionsApiPluginOptionsPlansPost(undefined, {
        type: PlanIndexItem.type.MAA_PLAN_CONFIG,
      })
      if (response.code === 200) {
        options.value = [{ label: t('core.edit.fixed'), value: 'Fixed' }, ...response.data]
      }
    } catch (error) {
      logger.error(
        `加载关卡配置模式选项失败: ${error instanceof Error ? error.message : String(error)}`
      )
    }
  }
  return { options, load }
}
