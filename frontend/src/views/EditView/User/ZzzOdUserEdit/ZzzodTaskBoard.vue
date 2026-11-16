<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import draggable from 'vuedraggable'
import {
  SettingOutlined,
  ExportOutlined,
  SortAscendingOutlined,
  QuestionCircleOutlined,
  HistoryOutlined,
} from '@ant-design/icons-vue'
import { useZzzOdTaskBoard } from '@/composables/useZzzOdTaskBoard'
import ZzzOdPlanListEditor from '@/components/ZzzOdPlanListEditor.vue'
import type { useZzzodTaskConfig } from './useZzzodTaskConfig'
import type { TaskCard } from './zzzodTypes'
const props = defineProps<{
  cards: TaskCard[]
  editable: boolean
  saving: boolean
  editor: ReturnType<typeof useZzzodTaskConfig>
  commit: (cards: TaskCard[]) => void
  configure: () => void
  restore: () => void
}>()
const {
  taskConfigData,
  taskConfigLoading,
  taskPopoverOpen,
  taskTipVisible,
  jumpTipVisible,
  handleTaskPopoverChange,
  scheduleTaskConfigSave,
  flushTaskConfigSave,
  saveTaskConfigField,
  planModal,
  planModalField,
  planModalOtherFields,
  savePlanModal,
} = props.editor

const openRestoreModal = () => props.restore()
const { t } = useI18n()
/** 拖拽排序的渲染数据源：跟随当前模式任务列表，拖拽过程由 vuedraggable 就地更新 */
const taskDragCards = ref<TaskCard[]>([])
watch(
  () => props.cards,
  cards => {
    taskDragCards.value = cards
  },
  { immediate: true }
)
// 任务看板共用操作（开关/拖拽/一键整理），两种模式仅落盘方式不同
const {
  toggle: toggleTask,
  commitDragOrder: handleTaskDragEnd,
  sortEnabledFirst: handleSortTasks,
} = useZzzOdTaskBoard(taskDragCards, {
  editable: () => props.editable,
  commit: props.commit,
})
// 任务卡跳转：先关跳转提示再进入配置会话
const jumpFromTaskCard = (appId: string) => {
  jumpTipVisible.value[appId] = false
  props.configure()
}
</script>
<template>
  <div class="section-header">
    <h3>
      {{ t('core.edit.zzzodOneDragonConfig') }}
      <a-tooltip :title="t('core.edit.zzzodOneDragonConfigHint')">
        <QuestionCircleOutlined class="help-icon" />
      </a-tooltip>
    </h3>
    <div class="section-header-actions">
      <a-tooltip :title="t('core.edit.zzzodSortTasksHint')">
        <a-button size="small" class="restore-entry" @click="handleSortTasks">
          <template #icon><SortAscendingOutlined /></template>
          {{ t('core.edit.zzzodSortTasks') }}
        </a-button>
      </a-tooltip>
      <a-button size="small" class="restore-entry" @click="openRestoreModal">
        <template #icon><HistoryOutlined /></template>
        {{ t('core.edit.configRestoreTitle') }}
      </a-button>
    </div>
  </div>
  <slot />
  <draggable
    v-model="taskDragCards"
    item-key="app_id"
    :animation="200"
    ghost-class="task-card-ghost"
    chosen-class="task-card-chosen"
    drag-class="task-card-drag"
    handle=".drag-handle"
    :disabled="!props.editable || props.saving"
    class="task-grid"
    @end="handleTaskDragEnd"
  >
    <template #item="{ element: card }">
      <div class="task-card" :class="{ inactive: !card.enabled }">
        <div class="task-card-main">
          <span
            class="drag-handle"
            :title="t('core.edit.zzzodDragSortHint')"
            :aria-label="t('core.edit.zzzodDragSortHint')"
          >
            <span class="drag-dots" aria-hidden="true"></span>
          </span>
          <span class="task-name" :title="card.app_name">{{ card.app_name }}</span>
          <div v-if="card.enabled" class="task-card-actions">
            <a-popover
              v-if="card.configurable"
              :open="taskPopoverOpen[card.app_id] === true"
              trigger="click"
              placement="top"
              @open-change="(o: boolean) => handleTaskPopoverChange(card, o)"
            >
              <template #content>
                <div
                  v-for="f in taskConfigData[card.app_id] ?? []"
                  :key="f.field"
                  class="task-config-field"
                >
                  <span class="task-config-field-title">{{ f.title }}</span>
                  <a-select
                    v-if="f.type === 'select' || f.type === 'team'"
                    :value="f.value ?? undefined"
                    size="small"
                    style="min-width: 150px"
                    @change="(v: any) => saveTaskConfigField(card, f, v)"
                  >
                    <a-select-option v-for="o in f.options" :key="o.value" :value="o.value">
                      {{ o.label }}
                    </a-select-option>
                  </a-select>
                  <a-switch
                    v-else-if="f.type === 'bool'"
                    :checked="f.value === true"
                    size="small"
                    @change="(v: any) => saveTaskConfigField(card, f, v)"
                  />
                  <a-input-number
                    v-else
                    :value="f.value"
                    size="small"
                    style="min-width: 100px"
                    @change="(v: any) => scheduleTaskConfigSave(card, f, v)"
                    @blur="() => flushTaskConfigSave(card, f)"
                  />
                </div>
              </template>
              <a-tooltip
                :title="t('core.edit.zzzodTaskConfigHint')"
                :open="taskTipVisible[card.app_id] === true"
                @open-change="(o: boolean) => (taskTipVisible[card.app_id] = o)"
              >
                <a-button
                  size="small"
                  type="text"
                  class="task-config-gear"
                  :loading="taskConfigLoading[card.app_id] === true"
                  @click="taskTipVisible[card.app_id] = false"
                >
                  <template #icon><SettingOutlined /></template>
                </a-button>
              </a-tooltip>
            </a-popover>
            <a-tooltip
              v-if="card.jump"
              :title="t('core.edit.zzzodTaskJumpHint')"
              :open="jumpTipVisible[card.app_id] === true"
              @open-change="(o: boolean) => (jumpTipVisible[card.app_id] = o)"
            >
              <a-button
                size="small"
                type="text"
                class="task-config-gear"
                @click="jumpFromTaskCard(card.app_id)"
              >
                <template #icon><ExportOutlined /></template>
              </a-button>
            </a-tooltip>
          </div>
          <div
            class="config-group-item-capsule"
            :class="{ active: card.enabled }"
            @click="toggleTask(card)"
          >
            <span class="config-group-item-dot"></span>
          </div>
        </div>
      </div>
    </template>
  </draggable>
  <a-modal
    v-model:open="planModal.open"
    :title="planModal.title"
    :width="760"
    :confirm-loading="planModal.saving"
    :mask-closable="false"
    :body-style="{ maxHeight: '70vh', overflowY: 'auto' }"
    @ok="savePlanModal"
  >
    <a-spin :spinning="planModal.loading">
      <div class="plan-modal-body">
        <ZzzOdPlanListEditor
          v-if="planModalField"
          v-model="planModal.draft"
          :columns="planModalField.columns ?? []"
          :new-item="planModalField.newItem ?? {}"
          :train-categories="planModal.trainCategories"
        />
        <div v-for="f in planModalOtherFields" :key="f.field" class="plan-modal-field">
          <span class="plan-modal-field-title">{{ f.title }}</span>
          <a-switch
            v-if="f.type === 'bool'"
            :checked="f.value === true"
            @change="(v: any) => (f.value = v)"
          />
          <a-input-number
            v-else-if="f.type === 'number'"
            :value="f.value"
            style="min-width: 120px"
            @change="(v: any) => (f.value = v)"
          />
          <a-select
            v-else
            :value="f.value ?? undefined"
            :options="f.options"
            style="min-width: 220px"
            @change="(v: any) => (f.value = v)"
          />
        </div>
      </div>
    </a-spin>
  </a-modal>
</template>
<style scoped>
@import './zzzodSectionHeader.css';
@import './zzzodFormControls.css';
@import './zzzodTaskCapsule.css';
/* 拖拽排序：手柄（所有卡片常显，含未启用的灰色卡片）与拖拽进行状态 */
.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-tertiary);
  cursor: grab;
  user-select: none;
  touch-action: none;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-dots {
  width: 12px;
  height: 14px;
  display: block;
  background-image: radial-gradient(currentColor 1.2px, transparent 1.2px);
  background-size: 5px 5px;
  opacity: 0.65;
}

.drag-handle:hover .drag-dots {
  opacity: 0.85;
}

.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.task-card {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  transition:
    background 0.2s,
    border-color 0.2s;
}

.task-card:hover {
  background: var(--ant-color-fill-tertiary);
}

.task-card.inactive {
  opacity: 0.6;
}

.task-card-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 24px;
}

.task-name {
  flex: 1;
  min-width: 0;
  font-weight: 600;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-card-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.task-card-ghost {
  opacity: 0.4;
}

.task-card-chosen {
  cursor: grabbing !important;
}

.task-card-drag {
  transform: rotate(3deg);
  opacity: 1 !important;
}

.task-config-gear {
  color: var(--ant-color-primary);
}

.task-config-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 260px;
  padding: 4px 0;
}

.task-config-field-title {
  color: var(--ant-color-text);
  font-size: 13px;
}

.plan-modal-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}

.plan-modal-field {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 2px 0;
}

.plan-modal-field-title {
  color: var(--ant-color-text);
  font-size: 13px;
  min-width: 120px;
}
</style>
