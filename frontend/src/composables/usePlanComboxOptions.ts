import { ref } from 'vue'
import { PlanComboxIn, Service, type ComboBoxItem } from '@/api'
import { comboxOptions } from '@/utils/comboxLabel'

type PlanOption = ComboBoxItem & { value: string }

const logger = window.electronAPI.getLogger('计划选项')

/**
 * 计划下拉选项（MAA 关卡配置 / MaaEnd 理智任务等）。
 *
 * 拉取指定 consumer 的计划 combox 并按界面语言本地化（固定项走词表）；
 * value 为 null 的异常项过滤掉。拉取失败时保留传入的兜底选项，不打断页面初始化。
 */
export const usePlanComboxOptions = (consumer: PlanComboxIn.consumer, fallback: PlanOption[]) => {
  const options = ref<PlanOption[]>(fallback)
  const loadOptions = async () => {
    try {
      const response = await Service.getPlanComboxApiInfoComboxPlanPost({ consumer })
      if (response?.code === 200 && response.data) {
        options.value = comboxOptions(
          response.data.filter((item): item is ComboBoxItem & { value: string } =>
            Boolean(item.value)
          )
        )
      }
    } catch (error) {
      logger.error(`加载计划选项失败: ${error instanceof Error ? error.message : String(error)}`)
    }
  }
  return { options, loadOptions }
}
