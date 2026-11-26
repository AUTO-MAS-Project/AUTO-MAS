// MFW 脚本页的公共件：通用页与专属页（views/m9a、views/mss）都从这里取 MFW 的分节、分节 props
// 与编排层拼自己的页面，不必复制 MaaFWScriptEdit.vue。页面宿主交来的上下文（脚本类型、页面种类、
// 引导步骤、读好的脚本详情）由编排层自己取，页面照常调用即可。
// 这个文件刻意不叫 index.ts：vite 解析扩展名时 .vue 排在目录之前，按目录名引入会拿到同名的
// MaaFWScriptEdit.vue 页面本身（typecheck 却照样通过）。
import BasicInfoSection from './BasicInfoSection.vue'
import ControlConfigSection from './ControlConfigSection.vue'
import UpdateSettingsSection from './UpdateSettingsSection.vue'
import RunConfigSection from './RunConfigSection.vue'
import ShellInstanceImportSection from './ShellInstanceImportSection.vue'

export {
  BasicInfoSection,
  ControlConfigSection,
  UpdateSettingsSection,
  RunConfigSection,
  ShellInstanceImportSection,
}

export { useMaaFWScriptPage, type MaaFWScriptPageOptions } from './useMaaFWScriptPage'

export type {
  MaaFWEnvOutcome,
  MaaFWScriptBasicInfoSectionEmits,
  MaaFWScriptBasicInfoSectionProps,
  MaaFWScriptControlSectionEmits,
  MaaFWScriptControlSectionProps,
  MaaFWScriptRunSectionEmits,
  MaaFWScriptRunSectionProps,
  MaaFWScriptShellImportSectionEmits,
  MaaFWScriptShellImportSectionProps,
  MaaFWScriptUpdateSectionEmits,
  MaaFWScriptUpdateSectionProps,
} from './sectionProps'
