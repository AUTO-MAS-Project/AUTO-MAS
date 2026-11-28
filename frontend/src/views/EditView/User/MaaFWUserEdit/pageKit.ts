// MFW 用户页的公共件：通用页与专属页（views/m9a、views/mss）都从这里取 MFW 的分节、分节 props
// 与编排层拼自己的页面，不必复制 MaaFWUserEdit.vue。页面宿主交来的上下文（脚本类型、读好的
// 脚本详情）由编排层自己取，页面照常调用即可。
// 这个文件刻意不叫 index.ts：vite 解析扩展名时 .vue 排在目录之前，按目录名引入会拿到同名的
// MaaFWUserEdit.vue 页面本身（typecheck 却照样通过）。
import BasicInfoSection from './BasicInfoSection.vue'
import MaaFWQueueHeaderSection from './MaaFWQueueHeaderSection.vue'
import TaskQueueSection from './TaskQueueSection.vue'

export { BasicInfoSection, MaaFWQueueHeaderSection, TaskQueueSection }

export {
  useMaaFWUserPage,
  type MaaFWManagedTasks,
  type MaaFWUserPageOptions,
} from './useMaaFWUserPage'

export type {
  AddTaskCascaderOption,
  MaaFWUserBasicInfoSectionEmits,
  MaaFWUserBasicInfoSectionProps,
  MaaFWQueueTemplateView,
  MaaFWUserQueueHeaderSectionEmits,
  MaaFWUserQueueHeaderSectionProps,
  MaaFWUserFormData,
  MaaFWUserQueueImportCandidate,
  MaaFWUserTaskQueueSectionEmits,
  MaaFWUserTaskQueueSectionProps,
  PresetTemplate,
} from './sectionProps'
