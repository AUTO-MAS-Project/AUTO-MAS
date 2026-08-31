<template>
  <div class="form-section">
    <div class="section-header section-header-with-action">
      <h3>{{ t('edit.taskQueueConfiguration') }}</h3>
      <a-space>
        <a-button
          :loading="interfaceLoading"
          :disabled="!scriptPath"
          @click="emit('reloadInterface')"
        >
          <template #icon>
            <FileSearchOutlined />
          </template>
          {{ t('edit.readInterface') }}
        </a-button>
      </a-space>
    </div>

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
      <a-col :xs="24" :lg="12" class="task-list-column">
        <div class="column-header">
          <span>{{ t('edit.taskQueue') }}</span>
          <a-space>
            <a-button
              v-if="presetTemplates.length > 0 && orderedTasks.length > 0"
              type="link"
              size="small"
              @click="showPresetModalModel = true"
            >
              {{ t('edit.presetTemplate') }}
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
                <PlusOutlined />
              </template>
            </a-cascader>
          </a-space>
        </div>
        <div class="task-list">
          <div
            v-if="orderedTasks.length === 0 && presetTemplates.length > 0"
            class="preset-section"
          >
            <div
              v-for="template in presetTemplates"
              :key="template.preset.name"
              class="preset-card"
            >
              <div class="preset-card-inner">
                <div class="preset-header">
                  <div class="preset-icon-wrap">
                    <ThunderboltOutlined class="preset-icon" />
                  </div>
                  <div class="preset-info">
                    <h3 class="preset-name">{{ getDisplayName(template.preset) }}</h3>
                    <MaaFWDescriptionView
                      v-if="template.preset.description"
                      :content="template.preset.description"
                      :base-path="previewData.path"
                      class="preset-desc"
                    />
                  </div>
                </div>

                <div class="preset-tasks-preview">
                  <div v-for="taskName in template.taskNames" :key="taskName" class="task-chip">
                    <span class="task-dot"></span>
                    <span class="task-chip-name">
                      {{ getDisplayName(taskByName.get(taskName)!) }}
                    </span>
                  </div>
                </div>

                <div class="preset-actions">
                  <a-button
                    type="primary"
                    block
                    :disabled="template.taskNames.length === 0"
                    @click="emit('applyPresetTemplate', template.preset.name)"
                  >
                    <template #icon>
                      <ThunderboltOutlined />
                    </template>
                    一键切换预设（{{ template.taskNames.length }} 个任务）
                  </a-button>
                </div>
              </div>
            </div>
          </div>
          <a-empty
            v-else-if="orderedTasks.length === 0"
            :description="t('edit.addTaskAbove')"
            class="task-queue-empty"
          />
          <draggable
            v-else
            v-model="queuedTaskNamesModel"
            :item-key="getTaskKey"
            :animation="200"
            handle=".task-drag-handle"
            ghost-class="task-row-ghost"
            chosen-class="task-row-chosen"
            drag-class="task-row-drag"
            class="task-queue-list"
            :move="canDragTask"
            @end="emit('taskDragEnd')"
          >
            <template #item="{ element: taskName, index }">
              <button
                v-if="getQueuedTask(taskName)"
                type="button"
                class="task-row"
                :class="{ 'task-row-selected': selectedTask?.name === taskName }"
                @click="emit('selectTask', taskName)"
              >
                <HolderOutlined class="task-drag-handle" aria-hidden="true" />
                <img
                  v-if="resolveMaaFWAssetUrl(getQueuedTask(taskName)?.icon)"
                  :src="resolveMaaFWAssetUrl(getQueuedTask(taskName)?.icon)"
                  alt=""
                  width="28"
                  height="28"
                  class="task-icon"
                />
                <div class="task-main">
                  <span class="task-title">{{ getQueuedTaskDisplayName(taskName) }}</span>
                  <div class="task-meta">
                    <a-tag v-if="getQueuedTask(taskName)?.entry" color="blue">
                      {{ getQueuedTask(taskName)?.entry }}
                    </a-tag>
                    <a-tag
                      v-for="group in getQueuedTask(taskName)?.group || []"
                      :key="group"
                      color="default"
                    >
                      {{ group }}
                    </a-tag>
                  </div>
                </div>
                <a-space @click.stop>
                  <a-button
                    type="text"
                    size="small"
                    :disabled="
                      interfaceDependentDisabled || !canMoveTaskByOffset(taskName, index, -1)
                    "
                    :aria-label="t('edit.moveTaskUp')"
                    @click="emit('moveTask', taskName, -1)"
                  >
                    <template #icon>
                      <ArrowUpOutlined />
                    </template>
                  </a-button>
                  <a-button
                    type="text"
                    size="small"
                    :disabled="
                      interfaceDependentDisabled || !canMoveTaskByOffset(taskName, index, 1)
                    "
                    :aria-label="t('edit.moveTaskDown')"
                    @click="emit('moveTask', taskName, 1)"
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
      <a-col :xs="24" :lg="12" class="task-option-column">
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
              <div class="selected-task-title">{{ getDisplayName(selectedTask) }}</div>
              <div class="selected-task-meta">
                {{ selectedTask.entry || selectedTask.name }}
              </div>
            </div>
          </div>
          <MaaFWTaskOptionEditor
            :option-names="getTaskOptionNames(selectedTask)"
            :options="previewData.options"
            :task-options="taskSnapshot.taskOptions[selectedTask.name] || {}"
            :controller-name="effectiveControllerName"
            :resource-name="effectiveResourceName"
            :base-path="previewData.path"
            :disabled="interfaceDependentDisabled"
            @update="payload => emit('taskOptionUpdate', selectedTask!.name, payload)"
          />
          <MaaFWDescriptionView
            v-if="selectedTask.description"
            :content="selectedTask.description"
            :base-path="previewData.path"
            class="selected-task-description"
          />
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

    <a-modal
      v-model:open="showPresetModalModel"
      :title="t('edit.presetTemplate')"
      :footer="null"
      width="720px"
      class="preset-template-modal"
    >
      <div v-if="presetTemplates.length > 0" class="preset-section preset-section-modal">
        <div v-for="template in presetTemplates" :key="template.preset.name" class="preset-card">
          <div class="preset-card-inner">
            <div class="preset-header">
              <div class="preset-icon-wrap">
                <ThunderboltOutlined class="preset-icon" />
              </div>
              <div class="preset-info">
                <h3 class="preset-name">{{ getDisplayName(template.preset) }}</h3>
                <MaaFWDescriptionView
                  v-if="template.preset.description && previewData"
                  :content="template.preset.description"
                  :base-path="previewData.path"
                  class="preset-desc"
                />
              </div>
            </div>
            <div class="preset-tasks-preview">
              <div v-for="taskName in template.taskNames" :key="taskName" class="task-chip">
                <span class="task-dot"></span>
                <span class="task-chip-name">
                  {{ getDisplayName(taskByName.get(taskName)!) }}
                </span>
              </div>
            </div>
            <div class="preset-actions">
              <a-space>
                <a-button
                  :disabled="template.taskNames.length === 0"
                  @click="emit('appendPresetTemplate', template.preset.name)"
                >
                  {{ t('edit.appendTask') }}
                </a-button>
                <a-button
                  type="primary"
                  :disabled="template.taskNames.length === 0"
                  @click="emit('applyPresetTemplate', template.preset.name)"
                >
                  {{ t('edit.applyPreset2') }}
                </a-button>
              </a-space>
            </div>
          </div>
        </div>
      </div>
      <a-empty v-else :description="t('edit.noPresetTemplates')" />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import draggable from 'vuedraggable'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  FileSearchOutlined,
  HolderOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { buildMaaFWAssetUrl } from '@/composables/useMaaFWApi'
import MaaFWDescriptionView from '../MaaFWDescriptionView.vue'
import MaaFWTaskOptionEditor from '../MaaFWTaskOptionEditor.vue'
import type {
  MaaFWInterfacePreviewData,
  MaaFWPresetInfo,
  MaaFWTaskInfo,
  MaaFWTaskOptionValue,
  MaaFWTaskSnapshot,
} from '@/types/script'

const { t } = useI18n()

type DisplayItem = {
  name: string
  label?: string | null
}

type AddTaskCascaderOption = {
  value: string
  label: string
  children?: AddTaskCascaderOption[]
}

type AddTaskCascaderPathOption = {
  label?: string | number
  value?: string | number
}

type PresetTemplate = {
  preset: MaaFWPresetInfo
  taskNames: string[]
}

const props = defineProps<{
  interfaceLoading: boolean
  scriptPath: string
  previewData: MaaFWInterfacePreviewData | null
  interfaceDependentDisabled: boolean
  availableTasks: MaaFWTaskInfo[]
  orderedTasks: MaaFWTaskInfo[]
  queuedTaskNames: string[]
  addTaskCascaderValue: string[]
  addTaskCascaderOptions: AddTaskCascaderOption[]
  presetTemplates: PresetTemplate[]
  showPresetModal: boolean
  taskByName: Map<string, MaaFWTaskInfo>
  selectedTask: MaaFWTaskInfo | null
  taskSnapshot: MaaFWTaskSnapshot
  effectiveControllerName: string
  effectiveResourceName: string
}>()

const emit = defineEmits<{
  'update:queuedTaskNames': [value: string[]]
  'update:addTaskCascaderValue': [value: string[]]
  'update:showPresetModal': [value: boolean]
  reloadInterface: []
  addTaskCascaderChange: [value: unknown]
  applyPresetTemplate: [presetName: string]
  appendPresetTemplate: [presetName: string]
  selectTask: [taskName: string]
  moveTask: [taskName: string, direction: -1 | 1]
  taskDragEnd: []
  taskOptionUpdate: [taskName: string, payload: { optionName: string; value: MaaFWTaskOptionValue }]
  deleteSelectedTask: []
}>()

const queuedTaskNamesModel = computed({
  get: () => props.queuedTaskNames,
  set: value => emit('update:queuedTaskNames', value),
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

const resolveMaaFWAssetUrl = (rawPath?: string | null) => {
  return buildMaaFWAssetUrl(props.previewData?.path, rawPath)
}

const getTaskKey = (taskName: string) => taskName

const getQueuedTask = (taskName: string) => props.taskByName.get(taskName)

const getQueuedTaskDisplayName = (taskName: string) => {
  const task = getQueuedTask(taskName)
  return task ? getDisplayName(task) : taskName
}

const isPretask = (taskName: string) => getQueuedTask(taskName)?.entry === 'MXU_PRETASK'

const canMoveTaskByOffset = (taskName: string, index: number, direction: -1 | 1) => {
  const targetTaskName = props.orderedTasks[index + direction]?.name
  return Boolean(targetTaskName && isPretask(taskName) === isPretask(targetTaskName))
}

const canDragTask = (event: { draggedContext: { element: string; futureIndex: number } }) => {
  const pretaskCount = props.orderedTasks.filter(task => task.entry === 'MXU_PRETASK').length
  const isDraggedPretask = isPretask(event.draggedContext.element)
  return isDraggedPretask
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
    String(option.label || '')
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

.section-header-with-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
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

.task-editor-layout {
  min-height: 420px;
}

.task-list-column,
.task-option-column {
  display: flex;
  flex-direction: column;
}

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 600;
}

.add-task-cascader {
  width: 220px;
}

.task-list {
  flex: 1;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  overflow: hidden;
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

.preset-section-modal {
  max-height: 60vh;
  overflow: auto;
  padding: 0;
}

.preset-card {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.preset-card-inner {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
}

.preset-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.preset-icon-wrap {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  flex: 0 0 auto;
}

.preset-icon {
  font-size: 18px;
}

.preset-info {
  flex: 1;
  min-width: 0;
}

.preset-name {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.preset-desc {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.preset-tasks-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.task-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 3px 10px 3px 7px;
  border-radius: 16px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font-size: 13px;
}

.task-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ant-color-success);
  flex: 0 0 auto;
}

.task-chip-name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
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

.task-meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.task-option-panel {
  min-height: 100%;
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

.task-option-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}

.delete-task-button {
  margin-top: 24px;
  height: 40px;
}

@media (max-width: 768px) {
  .section-header-with-action,
  .column-header {
    flex-direction: column;
    align-items: stretch;
  }

  .task-row {
    gap: 12px;
  }

  .task-editor-layout {
    row-gap: 16px;
  }

  .add-task-cascader {
    width: 100%;
  }

  .task-editor-layout :deep(.ant-col) {
    max-width: 100%;
    flex: 0 0 100%;
  }
}
</style>
