// MFW 用户页的公共件：特调要整页替换用户页（描述对象的 userPage.page）时，从这里取 MFW 的
// 分节、分节契约与编排层拼自己的页面，不必复制 MaaFWUserEdit.vue。页面宿主交来的上下文
// （脚本类型、读好的脚本详情）由编排层自己取，特调页面照常调用即可。
import MaaFWUserEditHeader from './MaaFWUserEditHeader.vue'
import BasicInfoSection from './BasicInfoSection.vue'
import MaaFWQueueHeaderSection from './MaaFWQueueHeaderSection.vue'
import TaskQueueSection from './TaskQueueSection.vue'

export { MaaFWUserEditHeader, BasicInfoSection, MaaFWQueueHeaderSection, TaskQueueSection }

/** MFW 用户页的默认分节表（页面按 useMaaFWSections 叠上当前特调的替换分节） */
export const MAAFW_USER_PAGE_SECTIONS = {
  header: MaaFWUserEditHeader,
  basicInfo: BasicInfoSection,
  queueHeader: MaaFWQueueHeaderSection,
  taskQueue: TaskQueueSection,
}

export { useMaaFWUserPage, type MaaFWUserPageOptions } from './useMaaFWUserPage'

export type {
  AddTaskCascaderOption,
  MaaFWUserBasicInfoSectionEmits,
  MaaFWUserBasicInfoSectionProps,
  MaaFWUserHeaderSectionEmits,
  MaaFWUserHeaderSectionProps,
  MaaFWQueueTemplateView,
  MaaFWUserQueueHeaderSectionEmits,
  MaaFWUserQueueHeaderSectionProps,
  MaaFWUserQueueImportCandidate,
  MaaFWUserSectionContracts,
  MaaFWUserTaskQueueSectionEmits,
  MaaFWUserTaskQueueSectionProps,
  PresetTemplate,
} from '../../MaaFWFlavor/sectionContracts'
