<template>
  <div class="form-section">
    <!-- 全局选项每个用户只设一次，队列里的所有任务共用；任务配置里不再列它们 -->
    <div v-if="!interfaceLoading && previewData && showGlobalOptions" class="global-option-section">
      <div class="column-header">
        <span class="column-title">{{ t('core.edit.maafwGlobalOptions') }}</span>
      </div>
      <div class="global-option-panel">
        <div class="global-option-hint">{{ t('core.edit.maafwGlobalOptionsHint') }}</div>
        <MaaFWTaskOptionEditor
          :option-names="previewData.globalOption"
          :options="previewData.options"
          :task-options="taskSnapshot.globalOptions || {}"
          :controller-name="effectiveControllerName"
          :resource-name="effectiveResourceName"
          :base-path="previewData.path"
          :disabled="interfaceDependentDisabled"
          @update="payload => emit('globalOptionUpdate', payload)"
        />
      </div>
    </div>
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
                <!-- interface 已没有的任务（项目更新改了 name）是虚影：不能拖、不能移，只能删。
                     注释不能写进 item 插槽里：开发模式下它也算一个子节点，vuedraggable 要求只有一个 -->
                <template #item="{ element: queuedTask, index }">
                  <div
                    v-if="queuedTask.missing"
                    role="button"
                    tabindex="0"
                    class="task-row task-row-missing"
                    :class="{ 'task-row-selected': selectedTaskId === queuedTask.id }"
                    @click="emit('selectTask', queuedTask.id)"
                    @keydown.enter="emit('selectTask', queuedTask.id)"
                    @contextmenu="handleRowContextMenu(queuedTask.id)"
                  >
                    <HolderOutlined class="task-drag-handle-disabled" aria-hidden="true" />
                    <div class="task-main">
                      <span class="task-title task-title-missing">
                        {{ maafwQueueEntryTitle(queuedTask).name }}
                        <span
                          v-if="maafwQueueEntryTitle(queuedTask).index !== null"
                          class="task-copy-index"
                        >
                          #{{ maafwQueueEntryTitle(queuedTask).index }}
                        </span>
                      </span>
                      <span class="task-missing-tag">{{ t('core.edit.missingTaskTag') }}</span>
                    </div>
                    <a-popconfirm
                      :title="t('core.edit.deleteThisTask2')"
                      :ok-text="t('core.edit.ok')"
                      :cancel-text="t('core.edit.cancel')"
                      :disabled="interfaceDependentDisabled"
                      @confirm="emit('deleteTask', queuedTask.id)"
                    >
                      <a-button
                        type="text"
                        size="small"
                        :disabled="interfaceDependentDisabled"
                        :aria-label="t('core.edit.deleteThisTask')"
                        @click.stop
                      >
                        <template #icon>
                          <CloseOutlined />
                        </template>
                      </a-button>
                    </a-popconfirm>
                  </div>
                  <button
                    v-else
                    type="button"
                    class="task-row"
                    :class="{
                      'task-row-selected': selectedTaskId === queuedTask.id,
                      'task-row-skipped': taskSnapshot.taskChecked[queuedTask.id] === false,
                    }"
                    @click="emit('selectTask', queuedTask.id)"
                    @contextmenu="handleRowContextMenu(queuedTask.id)"
                  >
                    <HolderOutlined class="task-drag-handle" aria-hidden="true" />
                    <img
                      v-if="resolveMaaFWAssetUrl(queuedTask.task.icon)"
                      :src="resolveMaaFWAssetUrl(queuedTask.task.icon)"
                      alt=""
                      width="28"
                      height="28"
                      class="task-icon"
                      @error="hideBrokenMaaFWIcon"
                      @load="showLoadedMaaFWIcon"
                    />
                    <div class="task-main">
                      <span class="task-title">
                        {{ maafwQueueEntryTitle(queuedTask).name }}
                        <span
                          v-if="maafwQueueEntryTitle(queuedTask).index !== null"
                          class="task-copy-index"
                        >
                          #{{ maafwQueueEntryTitle(queuedTask).index }}
                        </span>
                      </span>
                      <!-- 多选项勾选数不满足 min_count / max_count：运行器会让整个用户的计划构建失败 -->
                      <a-tooltip
                        v-if="checkboxIssueTaskIds.has(queuedTask.id)"
                        :title="t('core.edit.maafwQueueTaskCheckboxCountInvalid')"
                      >
                        <ExclamationCircleOutlined class="task-option-issue" />
                      </a-tooltip>
                    </div>
                    <span class="task-row-actions" @click.stop>
                      <a-tooltip :title="taskCheckedLabel(queuedTask.id)">
                        <button
                          type="button"
                          class="task-lamp-button"
                          :class="{
                            'task-lamp-skipped': taskSnapshot.taskChecked[queuedTask.id] === false,
                          }"
                          :disabled="interfaceDependentDisabled"
                          :aria-label="taskCheckedLabel(queuedTask.id)"
                          @click.stop="emit('toggleTaskChecked', queuedTask.id)"
                        >
                          <span class="task-lamp" aria-hidden="true" />
                        </button>
                      </a-tooltip>
                      <span class="task-move-stack">
                        <button
                          type="button"
                          :disabled="interfaceDependentDisabled || !canMoveTaskByOffset(index, -1)"
                          :aria-label="t('core.edit.moveTaskUp')"
                          @click.stop="emit('moveTask', queuedTask.id, -1)"
                        >
                          <UpOutlined />
                        </button>
                        <button
                          type="button"
                          :disabled="interfaceDependentDisabled || !canMoveTaskByOffset(index, 1)"
                          :aria-label="t('core.edit.moveTaskDown')"
                          @click.stop="emit('moveTask', queuedTask.id, 1)"
                        >
                          <DownOutlined />
                        </button>
                      </span>
                    </span>
                  </button>
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
                <a-menu-item key="delete" danger :disabled="interfaceDependentDisabled">
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
        <MaaFWTaskConfigPanel
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

    <a-modal
      v-model:open="renameOpen"
      :title="t('core.edit.queueTaskRenameTitle')"
      width="480px"
      :ok-text="t('core.edit.ok')"
      :cancel-text="t('core.edit.cancel')"
      destroy-on-close
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
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { Modal } from 'ant-design-vue'
import draggable from 'vuedraggable'
import {
  DownOutlined,
  UpOutlined,
  CloseOutlined,
  ExclamationCircleOutlined,
  HolderOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue'
import { buildMaaFWAssetUrl } from '@/composables/useMaaFWApi'
import MaaFWTaskOptionEditor from '../MaaFWTaskOptionEditor.vue'
import { hideBrokenMaaFWIcon, showLoadedMaaFWIcon } from '../maafwIconImage'
import { findMaaFWCheckboxCountViolations } from '../maafwOptionValues'
import MaaFWNewBadge from './MaaFWNewBadge.vue'
import MaaFWQueueContextBar from './MaaFWQueueContextBar.vue'
import MaaFWQueueEmptyTemplates from './MaaFWQueueEmptyTemplates.vue'
import MaaFWQueueTemplateModal from './MaaFWQueueTemplateModal.vue'
import MaaFWTaskConfigPanel from './MaaFWTaskConfigPanel.vue'
import { matchesMaaFWAddTaskKeyword } from './maafwAddTaskMenu'
import { hasEditableMaaFWGlobalOptions } from './maafwGlobalOptions'
import {
  MAAFW_TASK_LABEL_MAX_LENGTH,
  maafwQueueEntryBaseName,
  maafwQueueEntryTitle,
} from './maafwTaskSnapshot'
import { MAAFW_MAX_TASK_REPEAT_COUNT } from '@/utils/maafwTaskInstance'
import type { MaaFWQueueEntry, MaaFWTaskInfo } from '@/types/script'
import type {
  MaaFWUserTaskQueueSectionEmits,
  MaaFWUserTaskQueueSectionProps,
} from '../../MaaFWFlavor/sectionContracts'

const { t } = useI18n()

/** 「添加任务」下拉每一栏的最小宽度：分组名、任务名不至于被截成几个字 */
const ADD_TASK_MENU_COLUMN_STYLE = { minWidth: '180px' }

type AddTaskCascaderPathOption = {
  label?: unknown
  searchText?: string
  value?: string | number
}

// props / 事件的契约在 sectionContracts（特调替换这个分节时按同一份契约接收）
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

const taskCheckedLabel = (taskId: string) =>
  t(
    props.taskSnapshot.taskChecked[taskId] === false
      ? 'core.edit.queueTaskSkipped'
      : 'core.edit.queueTaskRuns'
  )

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
  emit('selectTask', taskId)
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
    Modal.confirm({
      title: t('core.edit.deleteThisTask2'),
      okText: t('core.edit.ok'),
      okButtonProps: { danger: true },
      cancelText: t('core.edit.cancel'),
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

const uniqueOptionNames = (optionGroups: string[][]) => {
  const optionNames: string[] = []
  const seen = new Set<string>()
  for (const group of optionGroups) {
    for (const optionName of group) {
      if (seen.has(optionName)) continue
      seen.add(optionName)
      optionNames.push(optionName)
    }
  }
  return optionNames
}

// 全局选项在队列上方设一次；任务配置只列资源 / 控制器 / 任务自己的选项（同一选项也被它们
// 引用时照常列出，按任务存值，运行时叠在全局之上——与 MXU 一致）
const showGlobalOptions = computed(() =>
  hasEditableMaaFWGlobalOptions(
    props.previewData,
    props.effectiveControllerName,
    props.effectiveResourceName
  )
)

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

/* 全局选项：队列上方一块，框线与右侧任务配置面板一致 */
.global-option-section {
  margin-bottom: 24px;
}

.global-option-panel {
  padding: 20px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.global-option-hint {
  margin-bottom: 16px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
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

.task-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  /* 行尾控件高 32px，配 12px 上下内距维持原来的行高 */
  padding: 12px 16px;
  border: none;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease;
}

.task-row-chosen,
.task-row-drag {
  cursor: grabbing;
}

.task-drag-handle {
  flex: 0 0 auto;
  padding: 4px;
  border-radius: 4px;
  color: var(--ant-color-text-quaternary);
  font-size: 16px;
  cursor: grab;
  transition:
    color 0.15s ease,
    background-color 0.15s ease;
}

.task-drag-handle:hover {
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-tertiary);
}

.task-row-chosen .task-drag-handle,
.task-row-drag .task-drag-handle {
  cursor: grabbing;
}

.task-row-ghost {
  opacity: 0.45;
  background: var(--ant-color-primary-bg);
}

.task-row:last-child {
  border-bottom: none;
}

.task-row:hover {
  background: var(--ant-color-fill-quaternary);
}

.task-row-selected {
  background: var(--ant-color-primary-bg);
  border-left: 3px solid var(--ant-color-primary);
  padding-left: 13px;
}

.task-main {
  flex: 1;
  min-width: 0;
}

.task-icon {
  width: 28px;
  height: 28px;
  object-fit: contain;
  flex: 0 0 auto;
}

.task-title {
  font-weight: 600;
}

.task-row-skipped .task-icon,
.task-row-skipped .task-title {
  opacity: 0.45;
}

.task-row-actions {
  display: flex;
  align-items: center;
  flex: none;
  gap: 8px;
}

.task-lamp-button {
  --task-lamp-color: var(--ant-color-success);
  width: 24px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  display: grid;
  place-items: center;
  cursor: pointer;
}

.task-lamp {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: radial-gradient(
    circle at 35% 35%,
    color-mix(in srgb, var(--task-lamp-color) 55%, white),
    var(--task-lamp-color) 70%
  );
  box-shadow:
    inset 0 0 0 1px var(--ant-color-border),
    0 0 4px color-mix(in srgb, var(--task-lamp-color) 60%, transparent);
}

.task-lamp-skipped {
  --task-lamp-color: var(--ant-color-error);
}

.task-lamp-skipped .task-lamp {
  box-shadow:
    inset 0 0 0 1px var(--ant-color-border),
    0 0 8px var(--task-lamp-color);
}

.task-move-stack {
  width: 24px;
  height: 32px;
  display: flex;
  flex-direction: column;
  border-radius: 4px;
  overflow: hidden;
}

.task-move-stack button {
  width: 24px;
  height: 16px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--ant-color-text-secondary);
  display: grid;
  place-items: center;
  font-size: 12px;
  cursor: pointer;
}

.task-lamp-button:hover:not(:disabled),
.task-move-stack button:hover:not(:disabled) {
  background: var(--ant-color-fill-tertiary);
}

.task-move-stack button:hover:not(:disabled) {
  color: var(--ant-color-text);
}

.task-lamp-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.task-move-stack button:disabled {
  color: var(--ant-color-text-quaternary);
  cursor: not-allowed;
}

.task-lamp-button:focus-visible,
.task-move-stack button:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}

.task-option-issue {
  margin-left: 6px;
  color: var(--ant-color-warning);
}

/* 同一个任务被加了多份时的副本序号 */
.task-copy-index {
  margin-left: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--ant-color-text-tertiary);
}

/* 搜索时悬停出现的清除图标和后缀在同一个位置：加号和它一样大看不出来，NEW 标签更宽会露半截 */
:deep(.add-task-cascader:has(.ant-select-clear):hover .ant-select-arrow) {
  opacity: 0;
}

/* interface 已没有的任务：置灰、删除线，只留删除 */
.task-row-missing {
  padding-top: 14px;
  padding-bottom: 14px;
  background: var(--ant-color-fill-quaternary);
}

.task-title-missing {
  color: var(--ant-color-text-tertiary);
  font-weight: 400;
  text-decoration: line-through;
}

.task-row-missing .task-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.task-missing-tag {
  flex: none;
  padding: 0 7px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
}

.task-drag-handle-disabled {
  flex: 0 0 auto;
  padding: 4px;
  color: var(--ant-color-text-quaternary);
  font-size: 16px;
  opacity: 0.5;
  cursor: default;
}

/* 与 :lg 断点对齐：栅格在 992px 以下就折成上下两块，定高要在同一宽度放开，否则两栏叠在 640px 里溢出 */
@media (max-width: 991px) {
  .column-header {
    flex-direction: column;
    align-items: stretch;
  }

  .task-row {
    gap: 12px;
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
