<template>
  <!-- 任务队列右栏「任务配置」：选中任务的运行日与选项；虚影只给原来的设置与删除 -->
  <div v-if="selectedTask" class="task-option-panel">
    <div class="selected-task-header">
      <img
        v-if="resolveMaaFWAssetUrl(selectedTask.icon)"
        :src="resolveMaaFWAssetUrl(selectedTask.icon)"
        alt=""
        width="32"
        height="32"
        class="selected-task-icon"
        @error="hideBrokenMaaFWIcon"
        @load="showLoadedMaaFWIcon"
      />
      <div>
        <div class="selected-task-title">
          {{ selectedTaskTitle.name }}
          <span v-if="selectedTaskTitle.index !== null" class="task-copy-index">
            #{{ selectedTaskTitle.index }}
          </span>
        </div>
        <!-- 入口 | 分组：原来是队列行里的两个标签，挪到这里当副标题 -->
        <div class="selected-task-meta">{{ selectedTaskMeta }}</div>
      </div>
    </div>
    <!-- 运行日：前置任务与特调受管任务不受它影响，不显示 -->
    <MaaFWTaskWeekdaysField
      v-if="showWeekdays"
      :weekdays="selectedWeekdays"
      :disabled="disabled"
      @update="weekdays => emit('weekdaysUpdate', selectedTaskId, weekdays)"
    />
    <!-- 按选中的实例重建：搜索词与没提交的草稿不带到下一个任务 -->
    <MaaFWTaskOptionEditor
      :key="selectedTaskId"
      :option-names="optionNames"
      :options="previewData.options"
      :task-options="taskSnapshot.taskOptions[selectedTaskId] || {}"
      :controller-name="effectiveControllerName"
      :resource-name="effectiveResourceName"
      :base-path="previewData.path"
      :disabled="disabled"
      @update="payload => emit('taskOptionUpdate', selectedTaskId, payload)"
    />
    <div v-if="selectedTask.description" class="selected-task-description">
      <div class="selected-task-description-label">
        {{ t('core.edit.taskDescriptionLabel') }}
      </div>
      <MaaFWDescriptionView :content="selectedTask.description" :base-path="previewData.path" />
    </div>
    <a-popconfirm
      :title="t('core.edit.deleteThisTask2')"
      :ok-text="t('core.edit.ok')"
      :cancel-text="t('core.edit.cancel')"
      :disabled="disabled"
      @confirm="emit('deleteSelectedTask')"
    >
      <a-button danger block class="delete-task-button" :disabled="disabled">
        <template #icon>
          <DeleteOutlined />
        </template>
        {{ t('core.edit.deleteThisTask') }}
      </a-button>
    </a-popconfirm>
  </div>
  <div v-else-if="selectedMissingTask" class="task-option-panel">
    <div class="selected-task-header">
      <div>
        <div class="selected-task-title task-title-missing">
          {{ selectedTaskTitle.name }}
          <span v-if="selectedTaskTitle.index !== null" class="task-copy-index">
            #{{ selectedTaskTitle.index }}
          </span>
        </div>
        <div class="selected-task-meta">{{ t('core.edit.missingTaskHint') }}</div>
      </div>
    </div>
    <div v-if="missingTaskSettings.length > 0" class="missing-task-settings">
      <div class="missing-task-settings-title">{{ t('core.edit.missingTaskSettings') }}</div>
      <div v-for="row in missingTaskSettings" :key="row.key" class="missing-task-setting">
        <span class="missing-task-setting-label">{{ row.label }}</span>
        <span class="missing-task-setting-value">{{ row.value }}</span>
      </div>
    </div>
    <a-popconfirm
      :title="t('core.edit.deleteThisTask2')"
      :ok-text="t('core.edit.ok')"
      :cancel-text="t('core.edit.cancel')"
      :disabled="disabled"
      @confirm="emit('deleteSelectedTask')"
    >
      <a-button danger block class="delete-task-button" :disabled="disabled">
        <template #icon>
          <DeleteOutlined />
        </template>
        {{ t('core.edit.deleteThisTask') }}
      </a-button>
    </a-popconfirm>
  </div>
  <div v-else class="task-option-empty">
    <NoData :description="t('core.edit.pickTaskLeftConfigure')" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { DeleteOutlined } from '@ant-design/icons-vue'
import { buildMaaFWAssetUrl } from '@/composables/useMaaFWApi'
import MaaFWDescriptionView from '../MaaFWDescriptionView.vue'
import MaaFWTaskOptionEditor from '../MaaFWTaskOptionEditor.vue'
import { hideBrokenMaaFWIcon, showLoadedMaaFWIcon } from '../maafwIconImage'
import { isManagedMaaFWTask } from '../maafwManagedTasks'
import { describeMaaFWMissingTaskSettings } from '../maafwTaskChanges'
import MaaFWTaskWeekdaysField from './MaaFWTaskWeekdaysField.vue'
import { maafwDisplayedTaskWeekdays, maafwQueueEntryTitle } from './maafwTaskSnapshot'
import type {
  MaaFWInterfacePreviewData,
  MaaFWMissingQueuedTask,
  MaaFWQueueEntry,
  MaaFWTaskInfo,
  MaaFWTaskOptionValue,
  MaaFWTaskSnapshot,
} from '@/types/script'

const props = defineProps<{
  previewData: MaaFWInterfacePreviewData
  selectedTask: MaaFWTaskInfo | null
  /** 选中的队列项（虚影也在内）；队列为空时为 null */
  selectedQueuedTask: MaaFWQueueEntry | null
  selectedTaskId: string
  taskSnapshot: MaaFWTaskSnapshot
  /** 选中任务在当前控制器 / 资源下要列的选项 */
  optionNames: string[]
  effectiveControllerName: string
  effectiveResourceName: string
  managedTaskEntries?: ReadonlySet<string>
  disabled: boolean
}>()

const emit = defineEmits<{
  taskOptionUpdate: [taskId: string, payload: { optionName: string; value: MaaFWTaskOptionValue }]
  weekdaysUpdate: [taskId: string, weekdays: number[]]
  deleteSelectedTask: []
}>()

const { t } = useI18n()

const selectedMissingTask = computed<MaaFWMissingQueuedTask | null>(() => {
  const item = props.selectedQueuedTask
  return item?.missing ? item : null
})

// 虚影任务原来的设置：给用户对照着在新任务里重设
const missingTaskSettings = computed(() => {
  const item = selectedMissingTask.value
  if (!item) return []
  return describeMaaFWMissingTaskSettings(
    props.taskSnapshot.taskOptions[item.id],
    props.previewData.options
  )
})

// 标题与队列行一致（虚影也一样）：同一个 maafwQueueEntryTitle
const selectedTaskTitle = computed<{ name: string; index: number | null }>(() => {
  const item = props.selectedQueuedTask
  if (item) return maafwQueueEntryTitle(item)
  const task = props.selectedTask
  return { name: task ? task.label || task.name : '', index: null }
})

// 副标题：入口名 | 分组名…，原来是队列行里的两个标签。分组显示 label，与「添加任务」里的叫法一致
const selectedTaskMeta = computed(() => {
  const task = props.selectedTask
  if (!task) return ''
  const groupLabels = new Map(
    (props.previewData.groups || []).map(group => [group.name, group.label || group.name] as const)
  )
  const groups = (task.group || []).map(groupName => groupLabels.get(groupName) || groupName)
  return [task.entry || task.name, ...groups].filter(Boolean).join(' | ')
})

// 前置任务（MXU 壳的 pretask）与特调受管任务（M9A 的启动 / 切号 / 关闭）运行时不看运行日
const showWeekdays = computed(() => {
  const task = props.selectedTask
  if (!task || task.entry === 'MXU_PRETASK') return false
  return !isManagedMaaFWTask(task, props.managedTaskEntries ?? new Set())
})

// 红灯时七个勾全空（一天都不跑）；绿灯时是存的运行日
const selectedWeekdays = computed(() =>
  maafwDisplayedTaskWeekdays(props.taskSnapshot, props.selectedTaskId)
)

const resolveMaaFWAssetUrl = (rawPath?: string | null) =>
  buildMaaFWAssetUrl(props.previewData.path, rawPath)
</script>

<style scoped>
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

/* 同一个任务被加了多份时的副本序号（与队列行同一样式） */
.task-copy-index {
  margin-left: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--ant-color-text-tertiary);
}

.task-title-missing {
  color: var(--ant-color-text-tertiary);
  font-weight: 400;
  text-decoration: line-through;
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
</style>
