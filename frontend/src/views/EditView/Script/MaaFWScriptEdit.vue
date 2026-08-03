<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img
              :src="getScriptIcon(formData.type, scriptIconUrl)"
              :alt="formData.type"
              width="20"
              height="20"
              class="breadcrumb-logo"
              @error="event => handleScriptIconError(event, formData.type)"
            />
            项目配置
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
      <Transition name="save-chip-fade">
        <span
          v-if="saveStatus !== 'idle'"
          :class="['save-status-chip', `save-status-chip-${saveStatus}`]"
        >
          <LoadingOutlined v-if="saveStatus === 'saving'" spin />
          <CheckCircleOutlined v-else-if="saveStatus === 'saved'" />
          <a-tooltip v-else :title="saveErrorMessage || '保存失败，请重试'">
            <CloseCircleOutlined />
          </a-tooltip>
          <span>{{
            saveStatus === 'saving' ? '保存中…' : saveStatus === 'saved' ? '已自动保存' : '保存失败'
          }}</span>
        </span>
      </Transition>
    </div>

    <a-space size="middle">
      <a-tooltip
        v-if="formData.type === 'MaaFW' || formData.type === 'MaaFWManaged'"
        :title="
          hasUnsavedChanges || isSaving
            ? '请等待当前配置自动保存完成'
            : isProjectUpdateRunning || isAgentEnvPreparing
              ? '请等待当前项目更新或运行环境准备完成'
              : '管理项目资源与运行依赖'
        "
      >
        <a-button
          size="large"
          :disabled="hasUnsavedChanges || isSaving || isProjectUpdateRunning || isAgentEnvPreparing"
          @click="openProjectManager"
        >
          <template #icon>
            <DatabaseOutlined />
          </template>
          项目与依赖
        </a-button>
      </a-tooltip>
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </a-space>
  </div>

  <div class="script-edit-content">
    <a-card
      :title="formData.type === 'M9A' ? 'M9A 项目配置' : 'MaaFramework 项目配置'"
      :loading="pageLoading"
      class="config-card"
    >
      <template #extra>
        <a-tag color="geekblue" class="type-tag">
          {{ formData.type === 'MaaFWManaged' ? 'MaaFramework 项目' : formData.type }}
        </a-tag>
      </template>

      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <BasicInfoSection
          :maafw-config="maafwConfig"
          :form-data="formData"
          :rules="rules"
          :preview-data="previewData"
          :agent-env-result="agentEnvResult"
          :agent-env-progress-status="agentEnvProgressStatus"
          :agent-env-progress-stage="agentEnvProgressStage"
          :agent-env-progress-percent="agentEnvProgressPercent"
          :agent-env-progress-message="agentEnvProgressMessage"
          :agent-env-progress-logs="agentEnvProgressLogs"
          :agent-env-progress-downloaded-bytes="agentEnvProgressDownloadedBytes"
          :agent-env-progress-total-bytes="agentEnvProgressTotalBytes"
          :interface-loading="interfaceLoading"
          :agent-env-loading="agentEnvLoading"
          :is-agent-env-preparing="isAgentEnvPreparing"
          :is-project-update-running="isProjectUpdateRunning"
          :is-setup-mode="false"
          :is-managed-project="formData.type === 'MaaFWManaged'"
          :preview-project-title="previewProjectTitle"
          :interface-stats="interfaceStats"
          :is-interface-ready="isInterfaceReady"
          :is-agent-env-ready="isAgentEnvReady"
          :is-agent-env-failed="isAgentEnvFailed"
          :agent-env-alert-type="agentEnvAlertType"
          :agent-env-summary="agentEnvSummary"
          :agent-env-description="agentEnvDescription"
          :agent-env-checklist-description="agentEnvChecklistDescription"
          @change="handleChange"
          @select-path="selectMaaFWPath"
          @preview-interface="handlePreviewInterface"
          @prepare-agent-env="handlePrepareAgentEnv"
          @copy="copyToClipboard"
        />

        <ControlConfigSection
          :maafw-config="maafwConfig"
          :preview-data="previewData"
          :interface-loading="interfaceLoading"
          :emulator-loading="emulatorLoading"
          :emulator-device-loading="emulatorDeviceLoading"
          :emulator-options="emulatorOptions"
          :emulator-device-options="emulatorDeviceOptions"
          :emulator-type-by-id="emulatorTypeById"
          :controller-options="controllerOptions"
          :effective-controller-name="effectiveControllerName"
          :effective-controller-type="effectiveControllerType"
          :is-adb-controller="isAdbController"
          :is-desktop-controller="isDesktopController"
          :resource-options="resourceOptions"
          :unsupported-controller-options="unsupportedControllerOptions"
          :unsupported-controller-message="unsupportedControllerMessage"
          :adb-control-strategy-message="adbControlStrategyMessage"
          :adb-control-strategy-items="adbControlStrategyItems"
          :selected-emulator-label="selectedEmulatorLabel"
          :interface-dependent-disabled="interfaceDependentDisabled"
          @change="handleChange"
          @controller-change="handleControllerChange"
          @resource-change="handleResourceChange"
          @emulator-select-change="handleEmulatorSelectChange"
          @select-game-path="selectGamePath"
        />

        <a-alert
          v-if="formData.type === 'MaaFWManaged'"
          type="info"
          show-icon
          message="项目资源由 MAS 托管"
          description="托管项目的目录、版本、更新和运行依赖只能通过“项目与依赖”管理，以保护不可变版本。"
        />

        <UpdateSettingsSection
          v-else
          :maafw-config="maafwConfig"
          :preview-data="previewData"
          :is-auto-update-disabled="isAutoUpdateDisabled"
          :project-update-loading="projectUpdateLoading"
          :project-update-disabled="projectUpdateDisabled"
          :project-update-mirror-source-blocked="projectUpdateMirrorSourceBlocked"
          :project-update-status="projectUpdateStatus"
          :project-update-stage="projectUpdateStage"
          :project-update-progress="projectUpdateProgress"
          :project-update-download-percent="projectUpdateDownloadPercent"
          :project-update-downloaded-bytes="projectUpdateDownloadedBytes"
          :project-update-total-bytes="projectUpdateTotalBytes"
          :project-update-message="projectUpdateMessage"
          :project-update-discovered-version="projectUpdateDiscoveredVersion"
          :project-update-metadata-source="projectUpdateMetadataSource"
          :project-update-package-source="projectUpdatePackageSource"
          :project-update-logs="projectUpdateLogs"
          :update-source-options="updateSourceOptions"
          :update-channel-options="updateChannelOptions"
          @change="handleChange"
          @manual-update="handleManualProjectUpdate"
        />

        <RunConfigSection
          :maafw-config="maafwConfig"
          :daily-once-tasks="dailyOnceTasks"
          :weekly-once-tasks="weeklyOnceTasks"
          :monthly-once-tasks="monthlyOnceTasks"
          :period-task-options="periodTaskOptions"
          :interface-dependent-disabled="interfaceDependentDisabled"
          @change="handleChange"
          @period-task-change="handlePeriodTaskChange"
        />
      </a-form>
    </a-card>

    <div v-if="scriptEditHint" class="script-edit-hint">
      <img
        :src="getScriptIcon(formData.type, scriptIconUrl)"
        :alt="formData.type"
        width="28"
        height="28"
        class="script-edit-hint-logo"
        @error="event => handleScriptIconError(event, formData.type)"
      />
      <div class="script-edit-hint-message">
        <span>{{ scriptEditHint.text }}</span>
        <a
          v-if="scriptEditHint.url"
          :href="scriptEditHint.url"
          target="_blank"
          rel="noopener noreferrer"
          class="script-edit-hint-link"
        >
          {{ scriptEditHint.link_text || scriptEditHint.url }}
        </a>
        <span>{{ scriptEditHint.suffix }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  LoadingOutlined,
} from '@ant-design/icons-vue'
import { getScriptIcon, handleScriptIconError } from '@/utils/scriptRegistry'
import { useMaaFWScriptConfig } from '@/composables/useMaaFWScriptConfig'
import BasicInfoSection from './MaaFWScriptEdit/BasicInfoSection.vue'
import ControlConfigSection from './MaaFWScriptEdit/ControlConfigSection.vue'
import UpdateSettingsSection from './MaaFWScriptEdit/UpdateSettingsSection.vue'
import RunConfigSection from './MaaFWScriptEdit/RunConfigSection.vue'

const logger = window.electronAPI.getLogger('MaaFW脚本编辑')

const route = useRoute()
const router = useRouter()
const scriptId = route.params.id as string

const formRef = ref<FormInstance>()

const {
  maafwConfig,
  formData,
  rules,
  previewData,
  agentEnvResult,
  agentEnvProgressStatus,
  agentEnvProgressStage,
  agentEnvProgressPercent,
  agentEnvProgressMessage,
  agentEnvProgressLogs,
  agentEnvProgressDownloadedBytes,
  agentEnvProgressTotalBytes,
  projectUpdateLogs,
  projectUpdateStatus,
  projectUpdateStage,
  projectUpdateProgress,
  projectUpdateDownloadPercent,
  projectUpdateDownloadedBytes,
  projectUpdateTotalBytes,
  projectUpdateMessage,
  projectUpdateDiscoveredVersion,
  projectUpdateMetadataSource,
  projectUpdatePackageSource,
  scriptEditHint,
  scriptIconUrl,
  pageLoading,
  isInitializing,
  isSaving,
  saveStatus,
  saveErrorMessage,
  hasUnsavedChanges,
  interfaceLoading,
  agentEnvLoading,
  projectUpdateLoading,
  emulatorLoading,
  emulatorDeviceLoading,
  emulatorOptions,
  emulatorDeviceOptions,
  emulatorTypeById,
  dailyOnceTasks,
  weeklyOnceTasks,
  monthlyOnceTasks,
  isAutoUpdateDisabled,
  isInterfaceReady,
  isAgentEnvReady,
  isAgentEnvFailed,
  isAgentEnvPreparing,
  projectUpdateMirrorSourceBlocked,
  isProjectUpdateRunning,
  projectUpdateDisabled,
  periodTaskOptions,
  previewProjectTitle,
  interfaceStats,
  controllerOptions,
  unsupportedControllerOptions,
  unsupportedControllerMessage,
  effectiveControllerName,
  effectiveControllerType,
  isAdbController,
  isDesktopController,
  resourceOptions,
  interfaceDependentDisabled,
  selectedEmulatorLabel,
  adbControlStrategyMessage,
  adbControlStrategyItems,
  agentEnvAlertType,
  agentEnvSummary,
  agentEnvDescription,
  agentEnvChecklistDescription,
  updateSourceOptions,
  updateChannelOptions,
  copyToClipboard,
  handleChange,
  handlePeriodTaskChange,
  handlePreviewInterface,
  handlePrepareAgentEnv,
  handleManualProjectUpdate,
  handleControllerChange,
  handleResourceChange,
  handleEmulatorSelectChange,
  selectMaaFWPath,
  selectGamePath,
  loadScript,
  loadEmulatorOptions,
  handleBeforeUnload,
  dispose,
} = useMaaFWScriptConfig(scriptId)

const openProjectManager = () => {
  void router.push({ name: 'MaaFWProjects', query: { scriptId, from: 'edit' } })
}

const handleCancel = () => {
  if (hasUnsavedChanges.value || isSaving.value) {
    Modal.confirm({
      title: '有未保存的更改',
      content: '确定要离开吗？未保存的更改可能会丢失。',
      okText: '离开',
      cancelText: '继续编辑',
      onOk: () => router.push('/scripts'),
    })
    return
  }
  router.push('/scripts')
}

onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  try {
    await Promise.all([loadScript(), loadEmulatorOptions()])
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    router.replace('/scripts')
    return
  }
  isInitializing.value = false
  if (maafwConfig.Info.Path && previewData.value) {
    void handlePrepareAgentEnv()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  dispose()
})
</script>

<style scoped>
.script-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-nav {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.save-status-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  white-space: nowrap;
}

.save-status-chip-saving {
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-tertiary);
}

.save-status-chip-saved {
  color: var(--ant-color-success);
  background: var(--ant-color-success-bg);
}

.save-status-chip-error {
  color: var(--ant-color-error);
  background: var(--ant-color-error-bg);
}

.save-chip-fade-enter-active,
.save-chip-fade-leave-active {
  transition: opacity 0.2s ease;
}

.save-chip-fade-enter-from,
.save-chip-fade-leave-to {
  opacity: 0;
}

.breadcrumb :deep(ol) {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
}

.breadcrumb :deep(.ant-breadcrumb-link),
.breadcrumb :deep(.ant-breadcrumb-separator) {
  display: inline-flex;
  align-items: center;
}

.breadcrumb-current,
.breadcrumb-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.breadcrumb-link {
  color: var(--ant-color-text-secondary);
  text-decoration: none;
}

.breadcrumb-current {
  color: var(--ant-color-text);
  font-weight: 600;
}

.breadcrumb-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.script-edit-content {
  flex: 1;
}

.config-card {
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 20px 24px;
}

.config-card :deep(.ant-card-body) {
  padding: 24px;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 6px;
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 20px;
}

.script-edit-hint {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding: 14px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text-secondary);
}

.script-edit-hint-logo {
  width: 28px;
  height: 28px;
  object-fit: contain;
  flex: 0 0 auto;
}

.script-edit-hint-message {
  min-width: 0;
  font-size: 14px;
  line-height: 1.6;
}

.script-edit-hint-link {
  margin: 0 4px;
  color: var(--ant-color-primary);
  font-weight: 600;
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-body) {
    padding: 16px;
  }
}
</style>
