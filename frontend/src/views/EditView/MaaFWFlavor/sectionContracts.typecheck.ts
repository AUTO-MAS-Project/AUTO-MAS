// 只给 vue-tsc 看的断言（yarn typecheck 覆盖 src 下所有 .ts）：不被任何模块引入，不进构建。
// 1. MFW 的每个默认分节都接得住自己的契约；
// 2. defineMaaFWSection 的约束是真的：缺契约 props 的替换组件、错页错节的组件都过不了。
import { defineComponent, type PropType } from 'vue'
import {
  defineMaaFWSection,
  type MaaFWAcceptsSectionContract,
  type MaaFWSectionContract,
} from '@/composables/maafwFlavorTypes'
import type ScriptBasicInfoSection from '../Script/MaaFWScriptEdit/BasicInfoSection.vue'
import type ControlConfigSection from '../Script/MaaFWScriptEdit/ControlConfigSection.vue'
import type UpdateSettingsSection from '../Script/MaaFWScriptEdit/UpdateSettingsSection.vue'
import type RunConfigSection from '../Script/MaaFWScriptEdit/RunConfigSection.vue'
import type ShellInstanceImportSection from '../Script/MaaFWScriptEdit/ShellInstanceImportSection.vue'
import type MaaFWUserEditHeader from '../User/MaaFWUserEdit/MaaFWUserEditHeader.vue'
import type UserBasicInfoSection from '../User/MaaFWUserEdit/BasicInfoSection.vue'
import type MaaFWQueueHeaderSection from '../User/MaaFWUserEdit/MaaFWQueueHeaderSection.vue'
import type TaskQueueSection from '../User/MaaFWUserEdit/TaskQueueSection.vue'
import type MaaFWSourceStep from '@/views/scripts/components/MaaFWSourceStep.vue'

type Assert<T extends true> = T

/** MFW 默认分节 ↔ 契约 */
export type MaaFWDefaultSectionsAcceptTheirContracts = [
  Assert<
    MaaFWAcceptsSectionContract<
      typeof ScriptBasicInfoSection,
      MaaFWSectionContract<'scriptPage', 'basicInfo'>
    >
  >,
  Assert<
    MaaFWAcceptsSectionContract<
      typeof ControlConfigSection,
      MaaFWSectionContract<'scriptPage', 'control'>
    >
  >,
  Assert<
    MaaFWAcceptsSectionContract<
      typeof UpdateSettingsSection,
      MaaFWSectionContract<'scriptPage', 'update'>
    >
  >,
  Assert<
    MaaFWAcceptsSectionContract<typeof RunConfigSection, MaaFWSectionContract<'scriptPage', 'run'>>
  >,
  Assert<
    MaaFWAcceptsSectionContract<
      typeof ShellInstanceImportSection,
      MaaFWSectionContract<'scriptPage', 'shellImport'>
    >
  >,
  Assert<
    MaaFWAcceptsSectionContract<
      typeof MaaFWUserEditHeader,
      MaaFWSectionContract<'userPage', 'header'>
    >
  >,
  Assert<
    MaaFWAcceptsSectionContract<
      typeof UserBasicInfoSection,
      MaaFWSectionContract<'userPage', 'basicInfo'>
    >
  >,
  Assert<
    MaaFWAcceptsSectionContract<
      typeof MaaFWQueueHeaderSection,
      MaaFWSectionContract<'userPage', 'queueHeader'>
    >
  >,
  Assert<
    MaaFWAcceptsSectionContract<
      typeof TaskQueueSection,
      MaaFWSectionContract<'userPage', 'taskQueue'>
    >
  >,
  Assert<
    MaaFWAcceptsSectionContract<typeof MaaFWSourceStep, MaaFWSectionContract<'create', 'source'>>
  >,
]

/** 换错了节：运行参数分节接不住控制方式的契约 */
type RunSectionAsControl = MaaFWAcceptsSectionContract<
  typeof RunConfigSection,
  MaaFWSectionContract<'scriptPage', 'control'>
>
// @ts-expect-error -- RunConfigSection 没有 controllerOptions 等 control 契约的 props
export type MaaFWWrongSectionIsRejected = Assert<RunSectionAsControl>

/** defineMaaFWSection：真实 SFC 能声明；缺 props / 类型对不上 / 多出必填 prop 的组件声明不了 */
export const maafwSectionDeclarationChecks = () => [
  defineMaaFWSection(
    'scriptPage',
    'control',
    () => import('../Script/MaaFWScriptEdit/ControlConfigSection.vue')
  ),
  defineMaaFWSection(
    'userPage',
    'header',
    () => import('../User/MaaFWUserEdit/MaaFWUserEditHeader.vue')
  ),
  defineMaaFWSection(
    'create',
    'source',
    () => import('@/views/scripts/components/MaaFWSourceStep.vue')
  ),
  // @ts-expect-error -- 新建流程的 source 接不住脚本页外壳导入分节
  defineMaaFWSection(
    'create',
    'source',
    () => import('../Script/MaaFWScriptEdit/ShellInstanceImportSection.vue')
  ),
  // @ts-expect-error -- 只声明了 instances，缺 selectedIds
  defineMaaFWSection('scriptPage', 'shellImport', async () =>
    defineComponent({ props: { instances: { type: Array, required: true } } })
  ),
  // @ts-expect-error -- selectedIds 声明成 number，接不住契约的 string[]
  defineMaaFWSection('scriptPage', 'shellImport', async () =>
    defineComponent({
      props: {
        instances: { type: Array, required: true },
        selectedIds: { type: Number, required: true },
        importHotkeys: { type: Boolean, required: true },
        disabled: Boolean,
      },
    })
  ),
  // @ts-expect-error -- 多了一个契约之外的必填 prop，页面不会传它
  defineMaaFWSection('scriptPage', 'shellImport', async () =>
    defineComponent({
      props: {
        instances: { type: Array, required: true },
        selectedIds: { type: Array as PropType<string[]>, required: true },
        importHotkeys: { type: Boolean, required: true },
        disabled: Boolean,
        extra: { type: String, required: true },
      },
    })
  ),
  // 契约 props 全接住、多余的是可选：可以
  defineMaaFWSection('scriptPage', 'shellImport', async () =>
    defineComponent({
      props: {
        instances: { type: Array, required: true },
        selectedIds: { type: Array as PropType<string[]>, required: true },
        importHotkeys: { type: Boolean, required: true },
        disabled: Boolean,
        extra: { type: String, default: '' },
      },
    })
  ),
]
