<template>
  <ConfigEditShell :surface="false" class="user-edit-container">
    <template #header>
      <MaaFWUserEditHeader
        :save-status="saveStatus"
        :save-error-message="saveErrorMessage"
        :script-id="scriptId"
        :script-name="scriptName"
        :script-route="scriptRoute"
        :is-edit="isEdit"
        :user-id="userIdHolder.value"
        :leaving="leaving"
        @cancel="handleCancel"
      />
    </template>

    <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
      <a-card class="config-card" :loading="loading">
        <a-form
          v-if="isEdit"
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <BasicInfoSection
            :heading="{
              isEdit,
              logoSrc: projectIconUrl || metadata.logo,
              saveStatus,
              saveErrorMessage,
              onIconError: handleProjectIconError,
            }"
            :form-data="formData"
            :interface-dependent-disabled="interfaceDependentDisabled"
            account-record-tooltip=""
            @save="handleFieldSave"
          />

          <MaaFWQueueHeaderSection
            :queue-hint-lines="queueHintLines"
            :managed-queue-alert="managedQueueAlert"
            :user-import-candidates="userImportCandidates"
            :user-import-loading="userImportLoading"
            @open-restore="restoreOpen = true"
            @load-user-import="loadUserImportCandidates"
            @import-from-user="importQueueFromUser"
            @imported="handleShellImported"
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
            :queue-templates="queueTemplates"
            :queue-template-draft="queueTemplateDraft"
            :task-by-name="taskByName"
            :selected-task="selectedTask"
            :selected-task-id="selectedQueuedTask?.id || ''"
            :task-snapshot="taskSnapshot"
            :effective-controller-name="effectiveControllerName"
            :effective-resource-name="effectiveResourceName"
            :managed-task-entries="managedTaskEntries"
            :deleting-task="deletingTask"
            @reorder-tasks="applyQueuedTaskIds"
            @add-task-cascader-change="handleAddTaskCascaderChange"
            @apply-preset-template="applyPresetTemplate"
            @save-queue-template="saveQueueTemplate"
            @apply-queue-template="applyQueueTemplate"
            @rename-queue-template="renameQueueTemplate"
            @delete-queue-template="deleteQueueTemplate"
            @select-task="selectTask"
            @toggle-task-checked="toggleTaskChecked"
            @move-task="moveTask"
            @task-drag-end="handleTaskDragEnd"
            @task-option-update="handleTaskOptionUpdate"
            @global-option-update="handleGlobalOptionUpdate"
            @delete-selected-task="deleteSelectedTask"
            @delete-task="deleteTask"
            @duplicate-task="duplicateTask"
            @rename-task="renameTask"
            @task-weekdays-update="updateTaskWeekdays"
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

    <template #overlay>
      <!-- ══ 配置恢复（通用组件：MAS 用户字段在前、MaaFW 项目配置在后）══ -->
      <ConfigRestoreSection
        v-model:open="restoreOpen"
        :disabled="configLocked"
        :script-name="MAAFW_DISPLAY_NAME"
        :targets="restoreTargets"
        :api="restoreApi"
        :user-desc="t('core.edit.maafwConfigRestoreUserDesc')"
        :script-desc="t('core.edit.maafwConfigRestoreScriptDesc')"
        :on-restored="handleRestored"
      >
        <!-- mas 备份为字段侧车分区、native 备份为 interface 概览分区 -->
        <template #preview="{ raw }">
          <NoData
            v-if="!previewSections(raw).length"
            :description="t('core.edit.configRestorePreviewEmpty')"
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
    </template>
  </ConfigEditShell>
</template>

<script setup lang="ts">
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { ConfigEditShell } from '@/components/ui'
import { useI18n } from 'vue-i18n'
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import type { FormInstance } from 'ant-design-vue/es/form'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'
// 通用 MFW 用户页：只按 interface 渲染，不带任何专项分支（M9A、MSS 各有专属页面）
import {
  BasicInfoSection,
  MaaFWQueueHeaderSection,
  MaaFWUserEditHeader,
  TaskQueueSection,
  useMaaFWUserPage,
} from './MaaFWUserEdit/pageKit'

const { t } = useI18n()

const route = useRoute()

const scriptId = route.params.scriptId as string

const metadata = SCRIPT_METADATA.MaaFW

const formRef = ref<FormInstance>()

const {
  loading,
  saveStatus,
  saveErrorMessage,
  userIdHolder,
  isEdit,
  configLocked,
  scriptName,
  scriptRoute,
  previewData,
  interfaceLoading,
  projectIconUrl,
  handleProjectIconError,
  taskSnapshot,
  formData,
  rules,
  queueHintLines,
  managedQueueAlert,
  handleShellImported,
  taskByName,
  effectiveControllerName,
  effectiveResourceName,
  managedTaskEntries,
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
  toggleTaskChecked,
  applyPresetTemplate,
  deleteSelectedTask,
  deleteTask,
  deletingTask,
  duplicateTask,
  renameTask,
  updateTaskWeekdays,
  handleTaskOptionUpdate,
  handleGlobalOptionUpdate,
  moveTask,
  handleTaskDragEnd,
  addTaskCascaderValue,
  addTaskCascaderOptions,
  hasNewTasks,
  handleAddTaskCascaderChange,
  userImportCandidates,
  userImportLoading,
  loadUserImportCandidates,
  importQueueFromUser,
  queueTemplates,
  queueTemplateDraft,
  saveQueueTemplate,
  applyQueueTemplate,
  renameQueueTemplate,
  deleteQueueTemplate,
  MAAFW_DISPLAY_NAME,
  restoreOpen,
  restoreTargets,
  restoreApi,
  previewSections,
  handleRestored,
  leaving,
  handleCancel,
} = useMaaFWUserPage({ scriptId, userId: route.params.userId as string, type: 'MaaFW' })
</script>

<style scoped src="./MaaFWUserEdit/userPage.css"></style>
