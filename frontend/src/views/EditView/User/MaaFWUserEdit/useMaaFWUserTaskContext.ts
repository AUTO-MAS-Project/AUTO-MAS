import { computed, type ComputedRef, type Ref } from 'vue'
import { isSupportedMaaFWControllerType } from '@/types/script'
import type { MaaFWFlavor } from '@/composables/useMaaFWFlavor'
import { resolveMaaFWTaskName } from '@/utils/maafwTaskInstance'
import { isManagedMaaFWTask } from '../maafwManagedTasks'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig, MaaFWTaskInfo } from '@/types/script'

type MaaFWDisplayItem = {
  name: string
  label?: string | null
}

interface MaaFWUserTaskContextOptions {
  previewData: Ref<MaaFWInterfacePreviewData | null>
  scriptConfig: Ref<MaaFWScriptConfig | null>
  /** 脚本配了模拟器时默认控制器优先选 ADB */
  preferAdbController: Ref<boolean>
  interfaceLoading: Ref<boolean>
  flavor: ComputedRef<MaaFWFlavor>
}

/**
 * 用户页的任务上下文：按脚本的控制器 / 资源决定哪些任务可用，任务实例 id 与任务的互查，
 * 以及特调受管任务的判定。
 *
 * 和脚本页的 `useMaaFWControlConfig` 不是一回事，不要合并：这里的控制器候选按
 * `isSupportedMaaFWControllerType` 过滤，ADB 偏好来自脚本配置里是否配了模拟器（加载时算好传进来）。
 */
export function useMaaFWUserTaskContext({
  previewData,
  scriptConfig,
  preferAdbController,
  interfaceLoading,
  flavor,
}: MaaFWUserTaskContextOptions) {
  const controllerOptions = computed(() =>
    (previewData.value?.controllers || []).filter(controller =>
      isSupportedMaaFWControllerType(controller.type)
    )
  )
  const presetOptions = computed(() => previewData.value?.presets || [])
  const taskByName = computed(() => {
    const entries = (previewData.value?.tasks || []).map(task => [task.name, task] as const)
    return new Map<string, MaaFWTaskInfo>(entries)
  })
  // 队列元素是任务实例 id：同一个任务可以加入多次，首份的 id 就是裸任务名，
  // 第二份起是 `<任务名>__MAS_DUP__<随机后缀>`。
  const validTaskNames = computed(() => new Set(taskByName.value.keys()))
  const resolveTaskName = (taskId: string) => resolveMaaFWTaskName(taskId, validTaskNames.value)
  const getTaskInfoById = (taskId: string) => taskByName.value.get(resolveTaskName(taskId))
  const isPretaskId = (taskId: string) => getTaskInfoById(taskId)?.entry === 'MXU_PRETASK'
  const partitionTaskOrder = (taskIds: string[]) => {
    const uniqueIds = taskIds.filter((taskId, index, values) => values.indexOf(taskId) === index)
    return [
      ...uniqueIds.filter(taskId => isPretaskId(taskId)),
      ...uniqueIds.filter(taskId => !isPretaskId(taskId)),
    ]
  }
  const getDefaultControllerName = () => {
    if (preferAdbController.value) {
      const adbController = controllerOptions.value.find(controller => controller.type === 'Adb')
      if (adbController) return adbController.name
    }
    return controllerOptions.value[0]?.name || ''
  }
  const resolveControllerName = (controllerName?: string) => {
    if (controllerName && controllerOptions.value.some(item => item.name === controllerName)) {
      return controllerName
    }
    return getDefaultControllerName()
  }
  const effectiveControllerName = computed(() => {
    const scriptController = scriptConfig.value?.Info.Controller || ''
    return resolveControllerName(scriptController)
  })
  const getResourceOptionsByController = (controllerName: string) => {
    const resources = previewData.value?.resources || []
    if (!controllerName) return resources
    return resources.filter(
      resource => resource.controller.length === 0 || resource.controller.includes(controllerName)
    )
  }
  const resolveResourceName = (
    resourceName?: string,
    controllerName = effectiveControllerName.value
  ) => {
    const resources = getResourceOptionsByController(controllerName)
    if (resourceName && resources.some(item => item.name === resourceName)) {
      return resourceName
    }
    return resources[0]?.name || ''
  }
  const effectiveResourceName = computed(() => {
    const scriptResource = scriptConfig.value?.Info.Resource || ''
    return resolveResourceName(scriptResource)
  })
  const interfaceDependentDisabled = computed(() => interfaceLoading.value || !previewData.value)
  const isTaskActiveForCurrentContext = (task: MaaFWTaskInfo) => {
    const controllerName = effectiveControllerName.value
    const resourceName = effectiveResourceName.value
    if (!controllerName || !resourceName) {
      return false
    }
    if (task.controller.length > 0 && !task.controller.includes(controllerName)) {
      return false
    }
    if (task.resource.length > 0 && !task.resource.includes(resourceName)) {
      return false
    }
    return true
  }

  // 特调受管的任务（M9A 的启动 / 切号 / 关闭）由后端控制，不进「添加任务」与预设模板
  const managedTaskEntries = computed<ReadonlySet<string>>(
    () => new Set(flavor.value.userPage.managed.entries)
  )
  const isManagedTaskId = (taskId: string) =>
    isManagedMaaFWTask(getTaskInfoById(taskId), managedTaskEntries.value)

  const getDisplayName = (item: MaaFWDisplayItem) => {
    return item.label || item.name
  }

  return {
    presetOptions,
    taskByName,
    validTaskNames,
    resolveTaskName,
    getTaskInfoById,
    isPretaskId,
    partitionTaskOrder,
    effectiveControllerName,
    effectiveResourceName,
    interfaceDependentDisabled,
    isTaskActiveForCurrentContext,
    managedTaskEntries,
    isManagedTaskId,
    getDisplayName,
  }
}

export type MaaFWUserTaskContext = ReturnType<typeof useMaaFWUserTaskContext>
