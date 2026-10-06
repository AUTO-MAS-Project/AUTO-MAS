<template>
  <div class="form-section">
    <div v-if="interfaceLoading" class="task-loading">
      <a-spin :tip="t('edit.readingInterfaceJson')">
        <a-alert
          type="info"
          show-icon
          :message="t('edit.loadingMaafwProjectInterface')"
          :description="t('edit.readingTaskOptionPreset')"
        />
      </a-spin>
    </div>
    <a-empty
      v-else-if="!previewData"
      :description="t('edit.interfaceJsonHasNot')"
      class="task-empty"
    />
    <a-row v-else :gutter="24" class="task-editor-layout">
      <!-- 队列行只剩标题，左窄右宽：9 / 15 -->
      <a-col :xs="24" :lg="9" class="task-list-column">
        <div class="column-header">
          <span class="column-title">{{ t('edit.taskQueue') }}</span>
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
              {{ t('edit.queueTemplate') }}
            </a-button>
            <a-cascader
              v-model:value="addTaskCascaderValueModel"
              :options="addTaskCascaderOptions"
              :show-search="{ filter: filterAddTaskOption }"
              :placeholder="t('edit.addTask')"
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
          <!-- 队列为空：先列我的模板，再列项目预设，哪组没有就不显示那组 -->
          <div
            v-if="
              orderedTasks.length === 0 && (queueTemplates.length > 0 || presetTemplates.length > 0)
            "
            class="preset-section"
          >
            <template v-if="queueTemplates.length > 0">
              <div class="preset-group-title">{{ t('edit.queueTemplateMine') }}</div>
              <MaaFWQueueCard
                v-for="template in queueTemplates"
                :key="template.name"
                kind="template"
                :title="template.name"
                :task-count="template.chips.length"
                :invalid-count="template.invalidCount"
                :chips="template.chips"
              >
                <template #actions>
                  <a-button
                    type="primary"
                    :disabled="template.entries.length === 0"
                    @click="emit('applyQueueTemplate', template.name)"
                  >
                    {{ t('edit.queueTemplateApply') }}
                  </a-button>
                </template>
              </MaaFWQueueCard>
            </template>
            <template v-if="presetTemplates.length > 0">
              <div class="preset-group-title">{{ t('edit.queueTemplatePresets') }}</div>
              <MaaFWQueueCard
                v-for="template in presetTemplates"
                :key="template.preset.name"
                kind="preset"
                :title="getDisplayName(template.preset)"
                :description="template.preset.description"
                :base-path="previewData.path"
                :chips="presetChips(template)"
              >
                <template #actions>
                  <a-button
                    type="primary"
                    :disabled="template.entries.length === 0"
                    @click="emit('applyPresetTemplate', template.preset.name)"
                  >
                    {{ t('edit.applyPreset2') }}
                  </a-button>
                </template>
              </MaaFWQueueCard>
            </template>
          </div>
          <a-empty
            v-else-if="orderedTasks.length === 0"
            :description="t('edit.addTaskAbove')"
            class="task-queue-empty"
          />
          <draggable
            v-else
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
              >
                <HolderOutlined class="task-drag-handle-disabled" aria-hidden="true" />
                <div class="task-main">
                  <span class="task-title task-title-missing">
                    {{ queuedTask.name }}
                    <span v-if="queuedTask.copyTotal > 1" class="task-copy-index">
                      #{{ queuedTask.copyIndex }}
                    </span>
                  </span>
                  <span class="task-missing-tag">{{ t('edit.missingTaskTag') }}</span>
                </div>
                <a-popconfirm
                  :title="t('edit.deleteThisTask2')"
                  :ok-text="t('edit.ok')"
                  :cancel-text="t('edit.cancel')"
                  :disabled="interfaceDependentDisabled"
                  @confirm="emit('deleteTask', queuedTask.id)"
                >
                  <a-button
                    type="text"
                    size="small"
                    :disabled="interfaceDependentDisabled"
                    :aria-label="t('edit.deleteThisTask')"
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
                :class="{ 'task-row-selected': selectedTaskId === queuedTask.id }"
                @click="emit('selectTask', queuedTask.id)"
              >
                <HolderOutlined class="task-drag-handle" aria-hidden="true" />
                <img
                  v-if="resolveMaaFWAssetUrl(queuedTask.task.icon)"
                  :src="resolveMaaFWAssetUrl(queuedTask.task.icon)"
                  alt=""
                  width="28"
                  height="28"
                  class="task-icon"
                />
                <div class="task-main">
                  <span class="task-title">
                    {{ getDisplayName(queuedTask.task) }}
                    <span v-if="queuedTask.copyTotal > 1" class="task-copy-index">
                      #{{ queuedTask.copyIndex }}
                    </span>
                  </span>
                </div>
                <a-space @click.stop>
                  <a-button
                    type="text"
                    size="small"
                    :disabled="interfaceDependentDisabled || !canMoveTaskByOffset(index, -1)"
                    :aria-label="t('edit.moveTaskUp')"
                    @click="emit('moveTask', queuedTask.id, -1)"
                  >
                    <template #icon>
                      <ArrowUpOutlined />
                    </template>
                  </a-button>
                  <a-button
                    type="text"
                    size="small"
                    :disabled="interfaceDependentDisabled || !canMoveTaskByOffset(index, 1)"
                    :aria-label="t('edit.moveTaskDown')"
                    @click="emit('moveTask', queuedTask.id, 1)"
                  >
                    <template #icon>
                      <ArrowDownOutlined />
                    </template>
                  </a-button>
                </a-space>
              </button>
            </template>
          </draggable>
        </div>
      </a-col>
      <a-col :xs="24" :lg="15" class="task-option-column">
        <div class="column-header">
          <span>{{ t('edit.taskConfiguration') }}</span>
        </div>
        <div v-if="selectedTask" class="task-option-panel">
          <div class="selected-task-header">
            <img
              v-if="resolveMaaFWAssetUrl(selectedTask.icon)"
              :src="resolveMaaFWAssetUrl(selectedTask.icon)"
              alt=""
              width="32"
              height="32"
              class="selected-task-icon"
            />
            <div>
              <div class="selected-task-title">
                {{ getDisplayName(selectedTask) }}
                <span v-if="(selectedQueuedTask?.copyTotal || 1) > 1" class="task-copy-index">
                  #{{ selectedQueuedTask?.copyIndex }}
                </span>
              </div>
              <!-- 入口 | 分组：原来是队列行里的两个标签，挪到这里当副标题 -->
              <div class="selected-task-meta">{{ selectedTaskMeta }}</div>
            </div>
          </div>
          <MaaFWTaskOptionEditor
            :option-names="getTaskOptionNames(selectedTask)"
            :options="previewData.options"
            :task-options="taskSnapshot.taskOptions[selectedTaskId] || {}"
            :controller-name="effectiveControllerName"
            :resource-name="effectiveResourceName"
            :base-path="previewData.path"
            :disabled="interfaceDependentDisabled"
            @update="payload => emit('taskOptionUpdate', selectedTaskId, payload)"
          />
          <div v-if="selectedTask.description" class="selected-task-description">
            <div class="selected-task-description-label">
              {{ t('edit.taskDescriptionLabel') }}
            </div>
            <MaaFWDescriptionView
              :content="selectedTask.description"
              :base-path="previewData.path"
            />
          </div>
          <a-popconfirm
            :title="t('edit.deleteThisTask2')"
            :ok-text="t('edit.ok')"
            :cancel-text="t('edit.cancel')"
            :disabled="interfaceDependentDisabled"
            @confirm="emit('deleteSelectedTask')"
          >
            <a-button
              danger
              block
              class="delete-task-button"
              :disabled="interfaceDependentDisabled"
            >
              <template #icon>
                <DeleteOutlined />
              </template>
              {{ t('edit.deleteThisTask') }}
            </a-button>
          </a-popconfirm>
        </div>
        <div v-else-if="selectedMissingTask" class="task-option-panel">
          <div class="selected-task-header">
            <div>
              <div class="selected-task-title task-title-missing">
                {{ selectedMissingTask.name }}
                <span v-if="selectedMissingTask.copyTotal > 1" class="task-copy-index">
                  #{{ selectedMissingTask.copyIndex }}
                </span>
              </div>
              <div class="selected-task-meta">{{ t('edit.missingTaskHint') }}</div>
            </div>
          </div>
          <div v-if="missingTaskSettings.length > 0" class="missing-task-settings">
            <div class="missing-task-settings-title">{{ t('edit.missingTaskSettings') }}</div>
            <div v-for="row in missingTaskSettings" :key="row.key" class="missing-task-setting">
              <span class="missing-task-setting-label">{{ row.label }}</span>
              <span class="missing-task-setting-value">{{ row.value }}</span>
            </div>
          </div>
          <a-popconfirm
            :title="t('edit.deleteThisTask2')"
            :ok-text="t('edit.ok')"
            :cancel-text="t('edit.cancel')"
            :disabled="interfaceDependentDisabled"
            @confirm="emit('deleteSelectedTask')"
          >
            <a-button
              danger
              block
              class="delete-task-button"
              :disabled="interfaceDependentDisabled"
            >
              <template #icon>
                <DeleteOutlined />
              </template>
              {{ t('edit.deleteThisTask') }}
            </a-button>
          </a-popconfirm>
        </div>
        <div v-else class="task-option-empty">
          <a-empty :description="t('edit.pickTaskLeftConfigure')" />
        </div>
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
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import draggable from 'vuedraggable'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  CloseOutlined,
  DeleteOutlined,
  HolderOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue'
import { buildMaaFWAssetUrl } from '@/composables/useMaaFWApi'
import MaaFWDescriptionView from '../MaaFWDescriptionView.vue'
import MaaFWTaskOptionEditor from '../MaaFWTaskOptionEditor.vue'
import MaaFWNewBadge from './MaaFWNewBadge.vue'
import MaaFWQueueCard from './MaaFWQueueCard.vue'
import MaaFWQueueTemplateModal from './MaaFWQueueTemplateModal.vue'
import { describeMaaFWMissingTaskSettings } from '../maafwTaskChanges'
import type { MaaFWMissingQueuedTask, MaaFWQueueEntry, MaaFWTaskInfo } from '@/types/script'
import type {
  MaaFWUserTaskQueueSectionEmits,
  MaaFWUserTaskQueueSectionProps,
  PresetTemplate,
} from '../../MaaFWFlavor/sectionContracts'

const { t } = useI18n()

type DisplayItem = {
  name: string
  label?: string | null
}

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

const selectedMissingTask = computed<MaaFWMissingQueuedTask | null>(() => {
  const item = selectedQueuedTask.value
  return item?.missing ? item : null
})

// 虚影任务原来的设置：给用户对照着在新任务里重设
const missingTaskSettings = computed(() => {
  const item = selectedMissingTask.value
  if (!item) return []
  return describeMaaFWMissingTaskSettings(
    props.taskSnapshot.taskOptions[item.id],
    props.previewData?.options || []
  )
})

const addTaskCascaderValueModel = computed({
  get: () => props.addTaskCascaderValue,
  set: value => emit('update:addTaskCascaderValue', value),
})

const showPresetModalModel = computed({
  get: () => props.showPresetModal,
  set: value => emit('update:showPresetModal', value),
})

const getDisplayName = (item: DisplayItem) => item.label || item.name

const presetChips = (template: PresetTemplate) =>
  template.entries.map(entry => ({ id: entry.id, label: getDisplayName(entry.task) }))

// 右侧副标题：入口名 | 分组名…，原来是队列行里的两个标签
const selectedTaskMeta = computed(() => {
  const task = props.selectedTask
  if (!task) return ''
  return [task.entry || task.name, ...(task.group || [])].filter(Boolean).join(' | ')
})

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
    previewData?.globalOption || [],
    effectiveResource?.option || [],
    effectiveController?.option || [],
    task.option || [],
  ])
}

const filterAddTaskOption = (inputValue: string, path: AddTaskCascaderPathOption[]) => {
  const keyword = inputValue.trim().toLowerCase()
  if (!keyword) return true
  return path.some(option =>
    String(option.searchText ?? option.label ?? '')
      .toLowerCase()
      .includes(keyword)
  )
}
</script>

<style scoped>
.form-section {
  margin-bottom: 24px;
}

.section-header {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 20px;
  background: var(--ant-color-primary);
  border-radius: 2px;
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
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  overflow-x: hidden;
  overflow-y: auto;
  background: var(--ant-color-bg-container);
}

.task-queue-list {
  min-height: 100%;
}

.preset-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
}

/* 队列为空时的分组小标题：我的模板 / 项目预设 */
.preset-group-title {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.task-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  /* 标签行去掉后行变矮，内距放宽到 14px，别挤成一排细条 */
  padding: 14px 16px;
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

.missing-task-settings {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 6px;
  background: var(--ant-color-fill-quaternary);
}

.missing-task-settings-title {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  font-weight: 500;
}

.missing-task-setting {
  display: flex;
  gap: 16px;
}

.missing-task-setting-label {
  flex: none;
  width: 120px;
  color: var(--ant-color-text-secondary);
  overflow-wrap: anywhere;
}

.missing-task-setting-value {
  min-width: 0;
  color: var(--ant-color-text);
  overflow-wrap: anywhere;
}

.task-option-panel {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.selected-task-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.selected-task-icon {
  width: 32px;
  height: 32px;
  object-fit: contain;
  flex: 0 0 auto;
}

.selected-task-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.selected-task-meta {
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.selected-task-description {
  margin: 20px 0 0;
  padding: 16px 0 20px;
  border-top: 1px solid var(--ant-color-border-secondary);
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.selected-task-description-label {
  margin-bottom: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.task-option-empty {
  display: flex;
  flex: 1;
  min-height: 0;
  align-items: center;
  justify-content: center;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}

.delete-task-button {
  margin-top: 24px;
  height: 40px;
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
