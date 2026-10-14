// MFW 脚本页的公共件：特调要整页替换脚本页（描述对象的 scriptPage.page）时，从这里取 MFW 的
// 分节、分节契约与编排层拼自己的页面，不必复制 MaaFWScriptEdit.vue。页面宿主交来的上下文
// （脚本类型、页面种类、引导步骤、读好的脚本详情）由编排层自己取，特调页面照常调用即可。
import BasicInfoSection from '@deferred/views/EditView/Script/MaaFWScriptEdit/BasicInfoSection.vue'
import ControlConfigSection from '@deferred/views/EditView/Script/MaaFWScriptEdit/ControlConfigSection.vue'
import UpdateSettingsSection from '@deferred/views/EditView/Script/MaaFWScriptEdit/UpdateSettingsSection.vue'
import RunConfigSection from '@deferred/views/EditView/Script/MaaFWScriptEdit/RunConfigSection.vue'
import ShellInstanceImportSection from '@deferred/views/EditView/Script/MaaFWScriptEdit/ShellInstanceImportSection.vue'

export {
  BasicInfoSection,
  ControlConfigSection,
  UpdateSettingsSection,
  RunConfigSection,
  ShellInstanceImportSection,
}

/** MFW 脚本页的默认分节表（页面按 useMaaFWSections 叠上当前特调的替换分节） */
export const MAAFW_SCRIPT_PAGE_SECTIONS = {
  basicInfo: BasicInfoSection,
  control: ControlConfigSection,
  update: UpdateSettingsSection,
  run: RunConfigSection,
  shellImport: ShellInstanceImportSection,
}

export { useMaaFWScriptPage, type MaaFWScriptPageOptions } from '@deferred/views/EditView/Script/MaaFWScriptEdit/useMaaFWScriptPage.ts'

export type {
  MaaFWEnvOutcome,
  MaaFWScriptBasicInfoSectionEmits,
  MaaFWScriptBasicInfoSectionProps,
  MaaFWScriptControlSectionEmits,
  MaaFWScriptControlSectionProps,
  MaaFWScriptRunSectionEmits,
  MaaFWScriptRunSectionProps,
  MaaFWScriptSectionContracts,
  MaaFWScriptShellImportSectionEmits,
  MaaFWScriptShellImportSectionProps,
  MaaFWScriptUpdateSectionEmits,
  MaaFWScriptUpdateSectionProps,
} from '@deferred/views/EditView/MaaFWFlavor/sectionContracts.ts'
