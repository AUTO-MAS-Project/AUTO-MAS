<template>
  <UserEditShell
    :max-width="1400"
    script-type="M9A"
    :script-id="scriptId"
    :script-name="scriptName || 'MFW'"
    :script-route="scriptRoute"
    :is-edit="isEdit"
    :user-id="userIdHolder.value"
    :cancel-loading="leaving"
    :on-icon-error="handleProjectIconError"
    :user-name="formData.userName"
    @cancel="handleCancel"
  >
    <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
      <StateView :loading="loading">
        <a-form
          v-if="isEdit"
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <!-- 账号绑成切号任务的目标账号：占位与问号提示写清它的作用 -->
          <BasicInfoSection
            :heading="{
              isEdit,
              logoSrc: metadata.logo,
              saveStatus,
              saveErrorMessage,
              onIconError: handleProjectIconError,
            }"
            :form-data="formData"
            :interface-dependent-disabled="interfaceDependentDisabled"
            :account-record-tooltip="t('core.edit.m9aFlavorAccountTooltip')"
            :account-placeholder="t('core.edit.m9aFlavorAccountPlaceholder')"
            @save="handleFieldSave"
          />

          <!-- 启动游戏、切换账号、关闭游戏由后端全权控制：拆用户警告与残留提示在队列标题下 -->
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
          <SectionCard variant="plain">
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
          </SectionCard>

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
      </StateView>
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
          <div v-if="previewSections(raw).length">
            <template v-for="s in previewSections(raw)" :key="s.name">
              <h4 class="maafw-preview-title">{{ s.label }}</h4>
              <a-descriptions v-if="s.rows && s.rows.length" :column="1" size="small" bordered>
                <a-descriptions-item v-for="row in s.rows" :key="row.key" :label="row.key">
                  {{ row.value }}
                </a-descriptions-item>
              </a-descriptions>
            </template>
          </div>
          <NoData v-else :description="t('core.edit.configRestorePreviewEmpty')" />
        </template>
      </ConfigRestoreSection>
    </template>
  </UserEditShell>
</template>

<script setup lang="ts">
import UserEditShell from '@/components/UserEditShell.vue'
// M9A（重返未来：1999）专属用户页：用 MFW 用户页的分节与编排层拼，与通用 MFW 用户页结构相同。
// 账号绑成切号任务的目标账号；启动游戏、切换账号、关闭游戏是受管任务（由后端 app/task/M9A
// 全权控制，不能手动加），受管任务的名单与拆用户判据在下面交给编排层处理。
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { SectionCard, StateView } from '@/components/ui'
import { useI18n } from 'vue-i18n'
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import type { FormInstance } from 'ant-design-vue/es/form'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import {
  BasicInfoSection,
  MaaFWQueueHeaderSection,
  TaskQueueSection,
  useMaaFWUserPage,
} from '@/views/EditView/User/MaaFWUserEdit/pageKit'

const { t } = useI18n()

const route = useRoute()

const scriptId = route.params.scriptId as string

const metadata = SCRIPT_METADATA.M9A

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
} = useMaaFWUserPage({
  scriptId,
  userId: route.params.userId as string,
  type: 'M9A',
  managed: {
    // 与后端 app/task/M9A/managed.py 的 MANAGED_ENTRIES 同一组
    entries: ['StartUp', 'SwitchAccount', 'Close1999'],
    // 与 managed.py 同一判据：官服、有效切号 ≥ 2 才要拆用户（MAS 登录模式下切号不下发，由编排层按配置关掉）
    accountTask: { entry: 'SwitchAccount', resources: ['官服'] },
    warningKey: 'core.edit.m9aFlavorManagedTaskWarning',
    noticeKey: 'core.edit.m9aFlavorManagedTaskNotice',
  },
})
</script>

<style scoped src="../EditView/User/MaaFWUserEdit/userPage.css"></style>
