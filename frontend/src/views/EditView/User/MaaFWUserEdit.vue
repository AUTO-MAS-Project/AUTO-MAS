<template>
  <div class="user-edit-container">
    <component
      :is="sections.header"
      :save-status="saveStatus"
      :save-error-message="saveErrorMessage"
      :script-id="scriptId"
      :script-name="scriptName"
      :script-route="scriptRoute"
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
          <component
            :is="sections.basicInfo"
            :form-data="formData"
            :interface-dependent-disabled="interfaceDependentDisabled"
            :account-record-tooltip="accountRecordTooltip"
            :account-placeholder="t(flavor.userPage.text.accountPlaceholderKey)"
            @save="handleFieldSave"
          />

          <!-- 特调独有区块，由特调注册表按需加载 -->
          <MaaFWFlavorSlot
            part="userPage"
            name="afterBasicInfo"
            :flavor="flavor"
            :context="flavorSlotContext"
            @save="handleFieldSave"
          />

          <component
            :is="sections.queueHeader"
            :queue-hint-lines="queueHintLines"
            :managed-queue-alert="managedQueueAlert"
            :user-import-candidates="userImportCandidates"
            :user-import-loading="userImportLoading"
            @open-restore="restoreOpen = true"
            @load-user-import="loadUserImportCandidates"
            @import-from-user="importQueueFromUser"
            @imported="handleShellImported"
          />
          <!-- 特调独有区块（如 MSS 的计划表与活动优先），由特调注册表按需加载 -->
          <MaaFWFlavorSlot
            part="userPage"
            name="beforeTaskQueue"
            :flavor="flavor"
            :context="flavorSlotContext"
            @save="handleFieldSave"
          />
          <component
            :is="sections.taskQueue"
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
            @reorder-tasks="applyQueuedTaskIds"
            @add-task-cascader-change="handleAddTaskCascaderChange"
            @apply-preset-template="applyPresetTemplate"
            @save-queue-template="saveQueueTemplate"
            @apply-queue-template="applyQueueTemplate"
            @rename-queue-template="renameQueueTemplate"
            @delete-queue-template="deleteQueueTemplate"
            @select-task="selectTask"
            @move-task="moveTask"
            @task-drag-end="handleTaskDragEnd"
            @task-option-update="handleTaskOptionUpdate"
            @delete-selected-task="deleteSelectedTask"
            @delete-task="deleteTask"
          />
          <MaaFWFlavorSlot
            part="userPage"
            name="afterTaskQueue"
            :flavor="flavor"
            :context="flavorSlotContext"
            @save="handleFieldSave"
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
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import MaaFWFlavorSlot from '@/views/EditView/MaaFWFlavor/MaaFWFlavorSlot.vue'
import { useMaaFWSections } from '@/composables/useMaaFWFlavor'
import { normalizeTaskSnapshot } from './MaaFWUserEdit/maafwTaskSnapshot'
// MFW 默认分节静态引入：通用 MFW 打开不闪；特调的替换分节由注册表按需加载
import { MAAFW_USER_PAGE_SECTIONS, useMaaFWUserPage } from './MaaFWUserEdit/pageKit'

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
  scriptRoute,
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
  handleCancel,
} = useMaaFWUserPage({ scriptId, userId: route.params.userId as string })

// 各分节：默认用 MFW 的，当前特调替换了哪节就换成它的（契约见 MaaFWFlavor/sectionContracts）
const sections = useMaaFWSections(flavor, 'userPage', MAAFW_USER_PAGE_SECTIONS)

/**
 * 「配置导入」把外壳里的队列写进了用户：把实际落盘的快照规整成用户页自己的形状换进本地状态就行——
 * 写库那次请求后端已经做完了，这里再来一次 persistQueuedSnapshot 就是同一个动作写两遍。
 * 特调整理时一并改掉的账号 / 备注（M9A 把切换账号收进账号）也同步过来，否则页面上还是旧值。
 */
const handleShellImported = (snapshot: Record<string, unknown>, info: Record<string, unknown>) => {
  taskSnapshot.value = normalizeTaskSnapshot(snapshot, previewData.value, {
    keepMissing: true,
  })
  // 队列被换掉了，原来选的预设不再对得上（后端那次写入也清了它）
  formData.Task.SelectedPreset = ''
  if (typeof info.Account === 'string') formData.Info.Account = info.Account
  if (typeof info.Notes === 'string') formData.Info.Notes = info.Notes
}
</script>

<style scoped>
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
