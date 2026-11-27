<template>
  <div class="form-section">
    <div v-if="interfaceLoading" class="task-loading">
      <a-spin :tip="t('core.edit.readingInterfaceJson')">
        <a-alert
          type="info"
          show-icon
          :message="t('core.edit.loadingMaafwProjectInterface')"
          :description="t('core.edit.readingTaskOptionPreset')"
        />
      </a-spin>
    </div>
    <NoData
      v-else-if="!previewData"
      :description="t('core.edit.interfaceJsonHasNot')"
      class="task-empty"
    />
    <a-row v-else :gutter="24" class="task-editor-layout">
      <!-- 队列行只剩标题，左窄右宽：9 / 15 -->
      <a-col :xs="24" :lg="9" class="task-list-column">
        <div class="column-header">
          <span class="column-title">{{ t('core.edit.taskQueue') }}</span>
          <!-- 不用 a-space：列窄下来时级联选择器要能收缩，标题行不能折成两行，否则两栏顶边对不齐 -->
          <div class="column-actions">
            <!-- 队列为空时空态里已列出模板与预设；但有自定义模板时仍要能进弹窗改名、删除
                 （模板全部失效时空态卡片的「应用」都是灰的） -->
            <a-button
              v-if="orderedTasks.length > 0 || queueTemplates.length > 0"
              type="link"
              size="small"
              @click="showPresetModalModel = true"
            >
              {{ t('core.edit.queueTemplate') }}
            </a-button>
            <!-- 下拉宽度不跟输入框走（搜索时默认会跟）：每栏给够宽，任务名别被截断 -->
            <a-cascader
              v-model:value="addTaskCascaderValueModel"
              :options="addTaskCascaderOptions"
              :show-search="{ filter: filterAddTaskOption, matchInputWidth: false }"
              :dropdown-menu-column-style="ADD_TASK_MENU_COLUMN_STYLE"
              :placeholder="t('core.edit.addTask')"
              expand-trigger="hover"
              class="add-task-cascader"
              :disabled="interfaceDependentDisabled || availableTasks.length === 0"
              @change="(value: unknown) => emit('addTaskCascaderChange', value)"
            >
              <template #suffixIcon>
                <MaaFWNewBadge v-if="hasNewTasks" />
                <PlusOutlined v-else />
              </template>
            </a-cascader>
          </div>
        </div>
        <div class="task-list">
          <MaaFWQueueContextBar
            :preview-data="previewData"
            :task-snapshot="taskSnapshot"
            :task-by-name="taskByName"
            :effective-controller-name="effectiveControllerName"
            :effective-resource-name="effectiveResourceName"
          />
          <!-- 全局选项（项目声明了才有）：每个用户只设一次、队列里的任务共用，钉在队列最前，
               点它右栏换成全局选项的编辑器；队列为空时照样在 -->
          <MaaFWQueueGlobalOptionsRow
            v-if="showGlobalOptions"
            :selected="globalPanelActive"
            @select="globalOptionsSelected = true"
          />
          <MaaFWQueueEmptyTemplates
            v-if="
              orderedTasks.length === 0 && (queueTemplates.length > 0 || presetTemplates.length > 0)
            "
            :queue-templates="queueTemplates"
            :preset-templates="presetTemplates"
            :base-path="previewData.path"
            @apply-queue-template="name => emit('applyQueueTemplate', name)"
            @apply-preset-template="presetName => emit('applyPresetTemplate', presetName)"
          />
          <NoData
            v-else-if="orderedTasks.length === 0"
            :description="t('core.edit.addTaskAbove')"
            class="task-queue-empty"
          />
          <!-- 右键菜单整列共用一个：行上右键时先记下是哪一行，空白处右键不弹 -->
          <a-dropdown
            v-else
            :open="contextMenuOpen"
            :trigger="['contextmenu']"
            @open-change="handleContextMenuOpenChange"
          >
            <div class="task-queue-menu-area" @contextmenu.capture="contextTaskId = ''">
              <draggable
                v-model="queuedTaskItemsModel"
                item-key="id"
                :animation="200"
                handle=".task-drag-handle"
                ghost-class="task-row-ghost"
                chosen-class="task-row-chosen"
                drag-class="task-row-drag"
                class="task-queue-list"
                :move="canDragTask"
                @end="emit('taskDragEnd')"
              >
                <!-- 注释不能写进 item 插槽里：开发模式下它也算一个子节点，vuedraggable 要求只有一个 -->
                <template #item="{ element: queuedTask, index }">
                  <MaaFWQueueTaskRow
                    :entry="queuedTask"
                    :selected="!globalPanelActive && selectedTaskId === queuedTask.id"
                    :skipped="taskSnapshot.taskChecked[queuedTask.id] === false"
                    :disabled="interfaceDependentDisabled || deletingTask"
                    :can-move-up="canMoveTaskByOffset(index, -1)"
                    :can-move-down="canMoveTaskByOffset(index, 1)"
                    :option-issue="checkboxIssueTaskIds.has(queuedTask.id)"
                    :weekdays="rowWeekdays(queuedTask)"
                    :icon-url="queuedTask.missing ? '' : resolveMaaFWAssetUrl(queuedTask.task.icon)"
                    @select="selectTask(queuedTask.id)"
                    @open-menu="handleRowContextMenu(queuedTask.id)"
                    @toggle-checked="emit('toggleTaskChecked', queuedTask.id)"
                    @move="direction => emit('moveTask', queuedTask.id, direction)"
                    @delete="emit('deleteTask', queuedTask.id)"
                  />
                </template>
              </draggable>
            </div>
            <template #overlay>
              <a-menu @click="handleContextMenuClick">
                <template v-if="contextTask && !contextTask.missing">
                  <a-menu-item key="duplicate" :disabled="!canDuplicateContextTask">
                    {{ t('core.edit.queueTaskDuplicate') }}
                  </a-menu-item>
                  <a-menu-item key="rename" :disabled="interfaceDependentDisabled">
                    {{ t('core.edit.queueTaskRename') }}
                  </a-menu-item>
                </template>
                <a-menu-item
                  key="delete"
                  danger
                  :disabled="interfaceDependentDisabled || deletingTask"
                >
                  {{ t('core.edit.queueTaskDelete') }}
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-col>
      <a-col :xs="24" :lg="15" class="task-option-column">
        <div class="column-header">
          <span>{{ t('core.edit.taskConfiguration') }}</span>
        </div>
        <!-- 两块都用 v-show：切来切去不重建，选项编辑器里没提交的草稿还在，离开守卫照样查得到 -->
        <MaaFWGlobalOptionsPanel
          v-if="showGlobalOptions"
          v-show="globalPanelActive"
          :preview-data="previewData"
          :global-options="taskSnapshot.globalOptions || {}"
          :effective-controller-name="effectiveControllerName"
          :effective-resource-name="effectiveResourceName"
          :disabled="interfaceDependentDisabled"
          @update="payload => emit('globalOptionUpdate', payload)"
        />
        <MaaFWTaskConfigPanel
          v-show="!globalPanelActive"
          :preview-data="previewData"
          :selected-task="selectedTask"
          :selected-queued-task="selectedQueuedTask"
          :selected-task-id="selectedTaskId"
          :task-snapshot="taskSnapshot"
          :option-names="selectedTask ? getTaskOptionNames(selectedTask) : []"
          :effective-controller-name="effectiveControllerName"
          :effective-resource-name="effectiveResourceName"
          :managed-task-entries="managedTaskEntries"
          :disabled="interfaceDependentDisabled"
          :deleting="deletingTask"
          @task-option-update="(taskId, payload) => emit('taskOptionUpdate', taskId, payload)"
          @weekdays-update="(taskId, weekdays) => emit('taskWeekdaysUpdate', taskId, weekdays)"
          @delete-selected-task="emit('deleteSelectedTask')"
        />
      </a-col>
    </a-row>

    <MaaFWQueueTemplateModal
      v-model:open="showPresetModalModel"
      :queue-templates="queueTemplates"
      :preset-templates="presetTemplates"
      :draft="queueTemplateDraft"
      :base-path="previewData?.path"
      @apply-preset-template="presetName => emit('applyPresetTemplate', presetName)"
      @save-queue-template="name => emit('saveQueueTemplate', name)"
      @apply-queue-template="name => emit('applyQueueTemplate', name)"
      @rename-queue-template="(name, nextName) => emit('renameQueueTemplate', name, nextName)"
      @delete-queue-template="name => emit('deleteQueueTemplate', name)"
    />

    <AppModal
      v-model:open="renameOpen"
      size="sm"
      :title="t('core.edit.queueTaskRenameTitle')"
      @ok="confirmRename"
    >
      <!-- antd 受控输入只绑 :value 会被重渲染清空，必须 v-model:value -->
      <a-input
        v-model:value="renameDraft"
        :placeholder="t('core.edit.queueTaskDisplayName')"
        :maxlength="MAAFW_TASK_LABEL_MAX_LENGTH"
        autofocus
        @press-enter="confirmRename"
      />
    </AppModal>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import draggable from 'vuedraggable'
import { PlusOutlined } from '@ant-design/icons-vue'
import { AppModal } from '@/components/ui'
import { useConfirm } from '@/composables/useConfirm'
import { buildMaaFWAssetUrl } from '@/composables/useMaaFWApi'
import { isManagedMaaFWTask } from '../maafwManagedTasks'
import { findMaaFWCheckboxCountViolations } from '../maafwOptionValues'
import MaaFWGlobalOptionsPanel from './MaaFWGlobalOptionsPanel.vue'
import MaaFWNewBadge from './MaaFWNewBadge.vue'
import MaaFWQueueContextBar from './MaaFWQueueContextBar.vue'
import MaaFWQueueEmptyTemplates from './MaaFWQueueEmptyTemplates.vue'
import MaaFWQueueGlobalOptionsRow from './MaaFWQueueGlobalOptionsRow.vue'
import MaaFWQueueTaskRow from './MaaFWQueueTaskRow.vue'
import MaaFWQueueTemplateModal from './MaaFWQueueTemplateModal.vue'
import MaaFWTaskConfigPanel from './MaaFWTaskConfigPanel.vue'
import { matchesMaaFWAddTaskKeyword } from './maafwAddTaskMenu'
import { hasEditableMaaFWGlobalOptions } from './maafwGlobalOptions'
import {
  MAAFW_TASK_LABEL_MAX_LENGTH,
  maafwQueueEntryBaseName,
  maafwRestrictedTaskWeekdays,
} from './maafwTaskSnapshot'
import { MAAFW_MAX_TASK_REPEAT_COUNT } from '@/utils/maafwTaskInstance'
import type { MaaFWQueueEntry, MaaFWTaskInfo } from '@/types/script'
import type { MaaFWUserTaskQueueSectionEmits, MaaFWUserTaskQueueSectionProps } from './sectionProps'

const { t } = useI18n()
const { confirm } = useConfirm()

/** 「添加任务」下拉每一栏的最小宽度：分组名、任务名不至于被截成几个字 */
const ADD_TASK_MENU_COLUMN_STYLE = { minWidth: '180px' }

type AddTaskCascaderPathOption = {
  label?: unknown
  searchText?: string
  value?: string | number
}

// props / 事件见 sectionProps.ts
const props = defineProps<MaaFWUserTaskQueueSectionProps>()

const emit = defineEmits<MaaFWUserTaskQueueSectionEmits>()

const queuedTaskItemsModel = computed({
  get: () => props.orderedTasks,
  set: value =>
    emit(
      'reorderTasks',
      value.map(item => item.id)
    ),
})

const selectedQueuedTask = computed(
  () => props.orderedTasks.find(item => item.id === props.selectedTaskId) || null
)

const addTaskCascaderValueModel = computed({
  get: () => props.addTaskCascaderValue,
  set: value => emit('update:addTaskCascaderValue', value),
})

const showPresetModalModel = computed({
  get: () => props.showPresetModal,
  set: value => emit('update:showPresetModal', value),
})

// 全局选项在队列置顶那一行里设一次；任务配置只列资源 / 控制器 / 任务自己的选项（同一选项也被它们
// 引用时照常列出，按任务存值，运行时叠在全局之上——与 MXU 一致）
const showGlobalOptions = computed(() =>
  hasEditableMaaFWGlobalOptions(
    props.previewData,
    props.effectiveControllerName,
    props.effectiveResourceName
  )
)

// ── 右栏显示什么：选中的任务，或左栏置顶的「全局选项」 ──
// 选中哪个任务归页面管（selectedTaskId），全局选项不是任务，只在这里记一下；项目改了控制器 /
// 资源后没有可编辑的全局选项了，右栏自动回到任务
const globalOptionsSelected = ref(false)
const globalPanelActive = computed(() => globalOptionsSelected.value && showGlobalOptions.value)
// 页面换了选中的任务（添加、复制、删除后改选）：右栏跟过去
watch(
  () => props.selectedTaskId,
  () => {
    globalOptionsSelected.value = false
  }
)
// 点任务行：即使点的就是已选中的那一行，也要从全局选项切回来
const selectTask = (taskId: string) => {
  globalOptionsSelected.value = false
  emit('selectTask', taskId)
}

// 行上的运行日摘要：前置任务与特调受管任务运行时不看运行日，不显示
const rowWeekdays = (item: MaaFWQueueEntry) => {
  if (item.missing || item.task.entry === 'MXU_PRETASK') return null
  if (isManagedMaaFWTask(item.task, props.managedTaskEntries ?? new Set())) return null
  return maafwRestrictedTaskWeekdays(props.taskSnapshot, item.id)
}

// ── 队列行右键菜单：复制任务 / 重命名 / 删除任务 ──
const contextTaskId = ref('')
const contextMenuOpen = ref(false)
const contextTask = computed(
  () => props.orderedTasks.find(item => item.id === contextTaskId.value) || null
)
// 能复制的与「添加任务」能加的同一口径（受管、不可选、当前控制器 / 资源下不可用的都不在候选里），
// 同一任务的份数到上限后不再复制
const canDuplicateContextTask = computed(() => {
  const item = contextTask.value
  if (!item || item.missing || props.interfaceDependentDisabled) return false
  const taskName = item.task.name
  if (!props.availableTasks.some(task => task.name === taskName)) return false
  const copyCount = props.orderedTasks.filter(
    entry => !entry.missing && entry.task.name === taskName
  ).length
  return copyCount < MAAFW_MAX_TASK_REPEAT_COUNT
})

// 行上右键（冒泡阶段，先于菜单打开）：记下是哪一行，并把这一行同时选中，右栏与菜单指向同一任务。
// 放在行上而不是菜单打开时做：菜单已开着再右键另一行不会再触发 openChange，选中会停在旧行
const handleRowContextMenu = (taskId: string) => {
  contextTaskId.value = taskId
  selectTask(taskId)
}

// 空白处右键没有记下行，不弹
const handleContextMenuOpenChange = (open: boolean) => {
  contextMenuOpen.value = open && Boolean(contextTask.value)
}
// 菜单开着时又在空白处右键、或那一行已经不在了：收起
watch(contextTask, item => {
  if (!item) contextMenuOpen.value = false
})

const renameOpen = ref(false)
const renameDraft = ref('')
const renameTaskId = ref('')

const handleContextMenuClick = ({ key }: { key: string | number }) => {
  contextMenuOpen.value = false
  const item = contextTask.value
  if (!item) return
  if (key === 'duplicate') {
    emit('duplicateTask', item.id)
    return
  }
  if (key === 'rename' && !item.missing) {
    renameTaskId.value = item.id
    renameDraft.value = maafwQueueEntryBaseName(item)
    renameOpen.value = true
    return
  }
  if (key === 'delete') {
    // 菜单项里挂不了气泡确认，改用确认弹窗，文案与删除按钮的气泡相同
    const taskId = item.id
    void confirm({
      tone: 'danger',
      title: t('core.edit.deleteThisTask2'),
      onOk: () => emit('deleteTask', taskId),
    })
  }
}

const confirmRename = () => {
  if (!renameOpen.value) return
  renameOpen.value = false
  emit('renameTask', renameTaskId.value, renameDraft.value)
}

const resolveMaaFWAssetUrl = (rawPath?: string | null) => {
  return buildMaaFWAssetUrl(props.previewData?.path, rawPath)
}

const isPretaskItem = (item?: MaaFWQueueEntry | null) =>
  Boolean(item && !item.missing && item.task.entry === 'MXU_PRETASK')

const canMoveTaskByOffset = (index: number, direction: -1 | 1) => {
  const current = props.orderedTasks[index]
  const target = props.orderedTasks[index + direction]
  return Boolean(target && isPretaskItem(current) === isPretaskItem(target))
}

const canDragTask = (event: {
  draggedContext: { element: MaaFWQueueEntry; futureIndex: number }
}) => {
  const pretaskCount = props.orderedTasks.filter(item => isPretaskItem(item)).length
  return isPretaskItem(event.draggedContext.element)
    ? event.draggedContext.futureIndex < pretaskCount
    : event.draggedContext.futureIndex >= pretaskCount
}

const uniqueOptionNames = (optionGroups: string[][]) => [...new Set(optionGroups.flat())]

const getTaskOptionNames = (task: MaaFWTaskInfo) => {
  if (task.entry === 'MXU_PRETASK') {
    return uniqueOptionNames([task.option || []])
  }
  const previewData = props.previewData
  const effectiveResource = previewData?.resources.find(
    item => item.name === props.effectiveResourceName
  )
  const effectiveController = previewData?.controllers.find(
    item => item.name === props.effectiveControllerName
  )
  return uniqueOptionNames([
    effectiveResource?.option || [],
    effectiveController?.option || [],
    task.option || [],
  ])
}

// 勾选数不满足 min_count / max_count 的任务实例：与右栏编辑器列出的选项同一范围、同一取值口径。
// 只看勾选了的实例：运行时只检查它们（run_plan 的 _select_tasks），没勾选的亮了就是误报
const checkboxIssueTaskIds = computed(() => {
  const ids = new Set<string>()
  const optionMap = new Map((props.previewData?.options || []).map(item => [item.name, item]))
  if (optionMap.size === 0) return ids
  const context = {
    controllerName: props.effectiveControllerName,
    resourceName: props.effectiveResourceName,
  }
  for (const item of props.orderedTasks) {
    if (item.missing || !props.taskSnapshot.taskChecked[item.id]) continue
    const violations = findMaaFWCheckboxCountViolations(
      getTaskOptionNames(item.task),
      optionMap,
      props.taskSnapshot.taskOptions[item.id],
      context
    )
    if (violations.length > 0) ids.add(item.id)
  }
  return ids
})

const filterAddTaskOption = (inputValue: string, path: AddTaskCascaderPathOption[]) =>
  matchesMaaFWAddTaskKeyword(inputValue, path)
</script>

<style scoped>
.form-section {
  margin-bottom: 24px;
}

.task-loading {
  padding: 24px;
}

.task-loading :deep(.ant-spin-container) {
  opacity: 1;
}

.task-empty {
  padding: 24px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}

/* 左右两栏等高、高度固定：队列再长也不把页面撑长，各自在框里滚 */
.task-editor-layout {
  height: 640px;
}

.task-list-column,
.task-option-column {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

/* 两栏标题行同高：左边有 32px 的级联选择器，右边只有文字，不定高的话两个框的顶边差 7px */
.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 32px;
  margin-bottom: 16px;
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 600;
}

.column-title {
  white-space: nowrap;
}

.column-actions {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-width: 0;
}

.add-task-cascader {
  flex: 0 1 220px;
  min-width: 140px;
}

.task-list {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  overflow-x: hidden;
  overflow-y: auto;
  background: var(--ant-color-bg-container);
}

/* 右键菜单的触发区：撑满队列框余下的高度（基准 0 才是定高），拖拽列表的 min-height: 100% 才有定高可依 */
.task-queue-menu-area {
  flex: 1 0 0;
}

.task-queue-list {
  min-height: 100%;
}

/* 搜索时悬停出现的清除图标和后缀在同一个位置：加号和它一样大看不出来，NEW 标签更宽会露半截 */
:deep(.add-task-cascader:has(.ant-select-clear):hover .ant-select-arrow) {
  opacity: 0;
}

/* 与 :lg 断点对齐：栅格在 992px 以下就折成上下两块，定高要在同一宽度放开，否则两栏叠在 640px 里溢出 */
@media (max-width: 991px) {
  .column-header {
    flex-direction: column;
    align-items: stretch;
  }

  /* 折成上下两块后整行不再定高，改成每一栏各自定高 */
  .task-editor-layout {
    height: auto;
    row-gap: 16px;
  }

  .task-list-column,
  .task-option-column {
    height: 420px;
  }

  .add-task-cascader {
    flex: 1 1 auto;
  }

  .task-editor-layout :deep(.ant-col) {
    max-width: 100%;
    flex: 0 0 100%;
  }
}
</style>
