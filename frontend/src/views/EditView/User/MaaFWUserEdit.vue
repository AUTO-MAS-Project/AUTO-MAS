<template>
  <div class="user-edit-container">
    <MaaFWUserEditHeader
      :save-status="saveStatus"
      :save-error-message="saveErrorMessage"
      :script-id="scriptId"
      :script-name="scriptName"
      :script-route-suffix="flavor.routeSuffix"
      :is-edit="isEdit"
      :user-id="userIdHolder.value"
      @cancel="handleCancel"
    />

    <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
      <a-card class="config-card" :loading="loading">
        <template #title>
          <div class="card-title">
            <img
              :src="projectIconUrl || flavor.logo"
              :alt="flavor.typeTagLabel"
              width="22"
              height="22"
              class="title-logo"
              @error="handleProjectIconError"
            />
            <span>{{ scriptName || 'MFW' }}</span>
          </div>
        </template>

        <a-form
          v-if="isEdit"
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <BasicInfoSection
            :form-data="formData"
            :interface-dependent-disabled="interfaceDependentDisabled"
            :account-record-tooltip="accountRecordTooltip"
            :account-placeholder="t(flavor.accountPlaceholderKey)"
            @save="handleFieldSave"
          />

          <!-- MaaFW 是通用引擎，没有可退回的原生配置：三态来源与快速配置开关对它没有所指，
               任务队列始终显示。两个字段仍留在配置模型里，只是不再提供入口。 -->
          <a-flex
            class="section-header"
            justify="space-between"
            align="center"
            wrap="wrap"
            gap="small"
          >
            <h3>{{ t('edit.taskQueueConfiguration') }}</h3>
            <a-button size="small" @click="restoreOpen = true">
              <template #icon>
                <HistoryOutlined />
              </template>
              {{ t('edit.configRestoreTitle') }}
            </a-button>
          </a-flex>
          <!-- 特调类型（M9A）的受管任务（启动 / 切号 / 关闭）由后端全权控制：「添加任务」与预设里
               都没有它们；一条提示一个框：挤在一个框里读起来还是一坨 -->
          <a-alert
            v-for="(line, index) in queueHintLines"
            :key="index"
            class="flavor-queue-hint"
            type="info"
            show-icon
            :message="line"
          />
          <!-- 队列里还残留受管任务：照常显示。真要拆用户时是警告，其余（如刚导入成 M9A 带进来的
               启动 / 关闭）是轻提示，下次保存或重启会移出队列 -->
          <a-alert
            v-if="managedQueueAlert"
            class="flavor-queue-hint"
            :type="managedQueueAlert.type"
            show-icon
            :message="managedQueueAlert.message"
          />
          <!-- 特调独有区块（如 MSS 的计划表与活动优先），由特调注册表按需加载 -->
          <MaaFWFlavorSlot
            name="userBeforeTaskQueue"
            :flavor="flavor"
            :context="flavorSlotContext"
            @save="handleFieldSave"
          />
          <TaskQueueSection
            v-model:add-task-cascader-value="addTaskCascaderValue"
            v-model:show-preset-modal="showPresetModal"
            :interface-loading="interfaceLoading"
            :preview-data="previewData"
            :interface-dependent-disabled="interfaceDependentDisabled"
            :available-tasks="availableTasks"
            :ordered-tasks="orderedTasks"
            :add-task-cascader-options="addTaskCascaderOptions"
            :has-new-tasks="hasNewTasks"
            :preset-templates="presetTemplates"
            :task-by-name="taskByName"
            :selected-task="selectedTask"
            :selected-task-id="selectedQueuedTask?.id || ''"
            :task-snapshot="taskSnapshot"
            :effective-controller-name="effectiveControllerName"
            :effective-resource-name="effectiveResourceName"
            @reorder-tasks="applyQueuedTaskIds"
            @add-task-cascader-change="handleAddTaskCascaderChange"
            @apply-preset-template="applyPresetTemplate"
            @select-task="selectTask"
            @move-task="moveTask"
            @task-drag-end="handleTaskDragEnd"
            @task-option-update="handleTaskOptionUpdate"
            @delete-selected-task="deleteSelectedTask"
            @delete-task="deleteTask"
          />

          <ExtraScriptSection
            v-model:form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
          />

          <UserNotifyConfig
            v-model="formData.Notify"
            :loading="loading"
            :script-id="scriptId"
            :user-id="userIdHolder.value"
            @save="handleFieldSave"
          />
        </a-form>
      </a-card>
    </ConfigLockPanel>

    <!-- ══ 配置恢复（通用组件：MAS 用户字段在前、MaaFW 项目配置在后）══ -->
    <ConfigRestoreSection
      v-model:open="restoreOpen"
      :disabled="configLocked"
      :script-name="MAAFW_DISPLAY_NAME"
      :targets="restoreTargets"
      :api="restoreApi"
      :user-desc="t('edit.maafwConfigRestoreUserDesc')"
      :script-desc="t('edit.maafwConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
    >
      <!-- mas 备份为字段侧车分区、native 备份为 interface 概览分区 -->
      <template #preview="{ raw }">
        <a-empty
          v-if="!previewSections(raw).length"
          :description="t('edit.configRestorePreviewEmpty')"
        />
        <div v-else>
          <template v-for="s in previewSections(raw)" :key="s.name">
            <h4 class="maafw-preview-title">{{ s.label }}</h4>
            <a-descriptions
              v-if="s.rows && s.rows.length"
              :column="1"
              size="small"
              bordered
              class="maafw-preview-box"
            >
              <a-descriptions-item v-for="row in s.rows" :key="row.key" :label="row.key">
                {{ row.value }}
              </a-descriptions-item>
            </a-descriptions>
          </template>
        </div>
      </template>
    </ConfigRestoreSection>
  </div>
</template>

<script setup lang="ts">
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useI18n } from 'vue-i18n'
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import type { FormInstance } from 'ant-design-vue/es/form'
import { HistoryOutlined } from '@ant-design/icons-vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import MaaFWFlavorSlot from '@/views/EditView/MaaFWFlavor/MaaFWFlavorSlot.vue'
import MaaFWUserEditHeader from './MaaFWUserEdit/MaaFWUserEditHeader.vue'
import BasicInfoSection from './MaaFWUserEdit/BasicInfoSection.vue'
import TaskQueueSection from './MaaFWUserEdit/TaskQueueSection.vue'
import { useMaaFWUserPage } from './MaaFWUserEdit/useMaaFWUserPage'

const { t } = useI18n()

const route = useRoute()

const scriptId = route.params.scriptId as string

const formRef = ref<FormInstance>()

const {
  loading,
  saveStatus,
  saveErrorMessage,
  userIdHolder,
  isEdit,
  configLocked,
  scriptName,
  flavor,
  previewData,
  interfaceLoading,
  projectIconUrl,
  handleProjectIconError,
  taskSnapshot,
  formData,
  rules,
  queueHintLines,
  accountRecordTooltip,
  managedQueueAlert,
  flavorSlotContext,
  taskByName,
  effectiveControllerName,
  effectiveResourceName,
  interfaceDependentDisabled,
  handleFieldSave,
  showPresetModal,
  orderedTasks,
  availableTasks,
  presetTemplates,
  selectedQueuedTask,
  selectedTask,
  applyQueuedTaskIds,
  selectTask,
  applyPresetTemplate,
  deleteSelectedTask,
  deleteTask,
  handleTaskOptionUpdate,
  moveTask,
  handleTaskDragEnd,
  addTaskCascaderValue,
  addTaskCascaderOptions,
  hasNewTasks,
  handleAddTaskCascaderChange,
  MAAFW_DISPLAY_NAME,
  restoreOpen,
  restoreTargets,
  restoreApi,
  previewSections,
  handleRestored,
  handleCancel,
} = useMaaFWUserPage({ scriptId, userId: route.params.userId as string })
</script>

<style scoped>
/* 每条提示一个框（文案里用 \n 分行），框之间留点空 */
.flavor-queue-hint {
  margin-bottom: 8px;
}

.flavor-queue-hint-last {
  margin-bottom: 16px;
}

.user-edit-container {
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

.user-edit-content {
  max-width: 1400px;
  margin: 0 auto;
}

.config-card {
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
}

.config-card :deep(.ant-card-body) {
  padding: 24px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-logo {
  width: 22px;
  height: 22px;
  object-fit: contain;
}

/* 配置恢复预览（分区行；弹窗内滚动由通用组件负责） */
.maafw-preview-title {
  font-size: 15px;
  font-weight: 600;
  margin: 12px 0 8px;
  color: var(--ant-color-text);
}

.maafw-preview-box {
  margin-bottom: 8px;
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }
}
</style>
