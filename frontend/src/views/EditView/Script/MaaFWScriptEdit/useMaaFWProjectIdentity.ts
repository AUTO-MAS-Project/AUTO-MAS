import { computed, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { maafwDefaultScriptNames, type MaaFWFlavor } from '@/composables/useMaaFWFlavor'
import { resolveMaaFWProjectName } from '@/utils/maafwProjectName'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'
import type { MaaFWScriptChangeHandler, MaaFWScriptFormData } from './useMaaFWScriptDraft'

interface MaaFWProjectIdentityOptions {
  maafwConfig: MaaFWScriptConfig
  formData: MaaFWScriptFormData
  previewData: Ref<MaaFWInterfacePreviewData | null>
  isInitializing: Ref<boolean>
  handleChange: MaaFWScriptChangeHandler
  flavor: ComputedRef<MaaFWFlavor>
  isWizard: ComputedRef<boolean>
}

/** 项目名、页面标题与类型标签，以及读到 interface 后把项目名同步进脚本名。 */
export function useMaaFWProjectIdentity({
  maafwConfig,
  formData,
  previewData,
  isInitializing,
  handleChange,
  flavor,
  isWizard,
}: MaaFWProjectIdentityOptions) {
  const { t } = useI18n()

  // 项目实际的名字（「识宝小助手 Oᴗoಣ」而不是整条窗口标题或 MAA_bbb）：读到 interface 就按它算，
  // 没读到时用上次记下的 Info.ProjectLabel
  const projectName = computed(
    () =>
      (previewData.value ? resolveMaaFWProjectName(previewData.value.project) : '') ||
      maafwConfig.Info.ProjectLabel?.trim() ||
      ''
  )

  const previewProjectTitle = computed(() => {
    if (!previewData.value) return '-'
    return projectName.value || previewData.value.project.name
  })

  const projectDisplayName = computed(
    () => projectName.value || maafwConfig.Info.Name?.trim() || 'MFW'
  )

  // 卡片右上角的类型标签：有项目名就显示项目名，没有才显示 MFW / M9A
  const typeTagLabel = computed(() => projectName.value || flavor.value.typeTagLabel)

  // 新建脚本时后端给的默认名（MaaFWConfig 及各特调配置类的 DEFAULT_SCRIPT_NAME，登记在特调注册表）
  const DEFAULT_SCRIPT_NAMES = maafwDefaultScriptNames()

  // 读到 interface 后把项目名记进 Info.ProjectLabel（脚本列表的类型标签用它）；
  // 脚本名还是默认名、空、或是上次自动起的项目名时，一并改成项目名，用户自己起的名字不动。
  // 初始化期间 handleChange 不落盘，由 onMounted 在初始化结束后再调一次。
  const syncProjectName = async () => {
    if (isInitializing.value) return
    const name = previewData.value ? resolveMaaFWProjectName(previewData.value.project) : ''
    if (!name) return
    const previousLabel = maafwConfig.Info.ProjectLabel?.trim() ?? ''
    const currentName = maafwConfig.Info.Name.trim()
    const autoNamed =
      !currentName || DEFAULT_SCRIPT_NAMES.has(currentName) || currentName === previousLabel
    if (autoNamed && currentName !== name) {
      maafwConfig.Info.Name = name
      formData.name = name
      await handleChange('Info', 'Name', name)
    }
    if (previousLabel !== name) {
      maafwConfig.Info.ProjectLabel = name
      await handleChange('Info', 'ProjectLabel', name)
    }
  }

  // 通用 MaaFW 用「<项目名> 项目配置 / 项目引导」；特调类型（M9A）用它自己那句标题
  const pageTitle = computed(() =>
    flavor.value.scriptPage.text.titleKey
      ? t(flavor.value.scriptPage.text.titleKey)
      : `${projectDisplayName.value} ${isWizard.value ? '项目引导' : '项目配置'}`
  )

  return { previewProjectTitle, typeTagLabel, pageTitle, syncProjectName }
}
