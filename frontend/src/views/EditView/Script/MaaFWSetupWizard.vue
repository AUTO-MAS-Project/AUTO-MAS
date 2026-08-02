<template>
  <div class="wizard-page">
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
              项目引导
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
              saveStatus === 'saving'
                ? '保存中…'
                : saveStatus === 'saved'
                  ? '已自动保存'
                  : '保存失败'
            }}</span>
          </span>
        </Transition>
      </div>

      <a-space size="middle">
        <a-button size="large" class="cancel-button" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          返回
        </a-button>
      </a-space>
    </div>

    <div class="wizard-content">
      <a-card
        :title="formData.type === 'M9A' ? 'M9A 项目引导' : 'MaaFramework 项目引导'"
        :loading="pageLoading"
        class="wizard-card"
      >
        <template #extra>
          <a-tag color="geekblue" class="type-tag">
            {{ formData.type === 'MaaFWManaged' ? 'MaaFramework 项目' : formData.type }}
          </a-tag>
        </template>

        <a-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form wizard-form"
        >
          <a-steps size="small" :current="currentStep" :items="stepItems" class="config-steps" />

          <div class="wizard-step-area">
            <Transition name="step-fade" mode="out-in">
              <BasicInfoSection
                v-if="currentStep === 0"
                key="basic"
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
                :is-setup-mode="true"
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
              <MaaFWConfigurationReusePanel
                v-else-if="currentStep === 1"
                key="configuration-reuse"
                :script-id="scriptId"
                mode="first-user"
                :default-source-path="maafwConfig.Info.Path"
                @skipped="handleReuseSkipped"
                @applied="handleReuseApplied"
              />
              <ControlConfigSection
                v-else-if="currentStep === 2"
                key="control"
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
              <UpdateSettingsSection
                v-else-if="currentStep === 3 && formData.type !== 'MaaFWManaged'"
                key="update"
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
              <a-alert
                v-else-if="currentStep === 3"
                type="info"
                show-icon
                message="项目资源由 MAS 托管"
                description="托管项目的目录、版本、更新和运行依赖只能通过统一项目管理页维护。"
              />
              <section v-else-if="currentStep === 4" key="managed" class="managed-step">
                <a-alert
                  type="info"
                  show-icon
                  :message="
                    formData.type === 'MaaFW'
                      ? '是否将当前 MaaFW 项目转为托管项目？'
                      : '当前项目包保持普通模式'
                  "
                  :description="
                    formData.type === 'MaaFW'
                      ? '托管后仍使用当前脚本、用户与任务配置；MAS 会保存不可变项目版本，并统一管理项目资源、运行依赖、升级、切换与回收。'
                      : `${formData.type} 的资源升级由对应项目包插件维护，当前不会转换为通用 MaaFWManaged。`
                  "
                />

                <div class="managed-choice-grid">
                  <button
                    type="button"
                    :class="[
                      'managed-choice-card',
                      { 'managed-choice-card-selected': managedDecision === 'ordinary' },
                    ]"
                    :disabled="managedOperationRunning"
                    @click="chooseOrdinaryProject"
                  >
                    <span class="managed-choice-title">保持普通项目</span>
                    <span>继续直接使用当前 MaaFW 目录，稍后仍可从项目配置页转换。</span>
                  </button>
                  <button
                    type="button"
                    :class="[
                      'managed-choice-card',
                      { 'managed-choice-card-selected': managedDecision === 'managed' },
                    ]"
                    :disabled="!managedConversionAvailable || managedOperationRunning"
                    @click="openManagedProjectManager"
                  >
                    <span class="managed-choice-title">
                      {{ managedDecision === 'managed' ? '已转为托管项目' : '转为托管项目' }}
                    </span>
                    <span>导入当前资源版本，并在统一页面管理项目版本与运行依赖。</span>
                  </button>
                </div>

                <a-alert
                  v-if="managedCapabilitiesLoaded && !managedConversionAvailable"
                  type="warning"
                  show-icon
                  message="当前插件版本暂不支持原地转换"
                  :description="managedUnavailableReason"
                />
                <a-alert
                  v-else-if="managedDecision === 'ordinary'"
                  type="success"
                  show-icon
                  message="将保持普通 MaaFW 项目"
                  :description="
                    formData.type === 'MaaFW'
                      ? '这不会影响当前配置；完成向导后可随时打开“项目与依赖”进行转换。'
                      : `${formData.type} 继续使用对应项目包插件提供的资源升级能力。`
                  "
                />
                <a-alert
                  v-else-if="managedDecision === 'managed'"
                  type="success"
                  show-icon
                  message="当前脚本已由 MAS 托管"
                  description="脚本 ID、全部用户和任务配置保持不变；可以继续设置运行参数。"
                >
                  <template #action>
                    <a-button size="small" @click="openManagedProjectManager">
                      管理项目与依赖
                    </a-button>
                  </template>
                </a-alert>
                <div v-else-if="managedCapabilitiesLoading" class="managed-capability-loading">
                  <a-spin tip="正在检查托管能力" />
                </div>
              </section>
              <RunConfigSection
                v-else
                key="run"
                :maafw-config="maafwConfig"
                :daily-once-tasks="dailyOnceTasks"
                :weekly-once-tasks="weeklyOnceTasks"
                :monthly-once-tasks="monthlyOnceTasks"
                :period-task-options="periodTaskOptions"
                :interface-dependent-disabled="interfaceDependentDisabled"
                @change="handleChange"
                @period-task-change="handlePeriodTaskChange"
              />
            </Transition>
          </div>

          <div class="step-nav">
            <a-button
              v-if="currentStep > 0"
              size="large"
              class="step-nav-button"
              @click="goToStep(currentStep - 1)"
            >
              上一步
            </a-button>
            <div class="step-nav-right">
              <a-button
                v-if="currentStep < 5"
                type="primary"
                size="large"
                class="step-nav-button step-nav-main"
                :disabled="!canAdvanceNext"
                @click="goToStep(currentStep + 1)"
              >
                下一步
              </a-button>
              <template v-else>
                <a-button size="large" class="step-nav-button" @click="handleFinish">
                  完成
                </a-button>
                <a-button
                  type="primary"
                  size="large"
                  class="step-nav-button step-nav-main"
                  @click="goCreateFirstUser"
                >
                  {{ importedUserId ? '编辑已导入用户' : '创建第一个用户！' }}
                </a-button>
              </template>
            </div>
          </div>
        </a-form>
      </a-card>
    </div>

    <MaaFWProjectManagerModal
      v-model:open="managerOpen"
      :script-id="scriptId"
      @converted="handleManagedConverted"
      @refreshed="handleManagedRefreshed"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons-vue'
import { getScriptIcon, handleScriptIconError } from '@/utils/scriptRegistry'
import { useMaaFWScriptConfig } from '@/composables/useMaaFWScriptConfig'
import type { MaaFWConfigurationApplyResult } from '@/composables/useMaaFWConfigurationReuse'
import MaaFWConfigurationReusePanel from '@/components/MaaFWConfigurationReusePanel.vue'
import BasicInfoSection from './MaaFWScriptEdit/BasicInfoSection.vue'
import ControlConfigSection from './MaaFWScriptEdit/ControlConfigSection.vue'
import UpdateSettingsSection from './MaaFWScriptEdit/UpdateSettingsSection.vue'
import RunConfigSection from './MaaFWScriptEdit/RunConfigSection.vue'
import MaaFWProjectManagerModal from './MaaFWScriptEdit/MaaFWProjectManagerModal.vue'
import { useMaaFWManagedApi } from '@/composables/useMaaFWManagedApi'

const logger = window.electronAPI.getLogger('MaaFW引导')

const route = useRoute()
const router = useRouter()
const scriptId = route.params.id as string

const formRef = ref<FormInstance>()
const currentStep = ref(0)
const reuseComplete = ref(false)
const importedUserId = ref('')
const managerOpen = ref(false)
const managedDecision = ref<'pending' | 'ordinary' | 'managed'>('pending')
const managedCapabilitiesLoaded = ref(false)
const managedApi = useMaaFWManagedApi()

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
  scriptIconUrl,
  pageLoading,
  isInitializing,
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

const isStepZeroReady = computed(
  () => isInterfaceReady.value && isAgentEnvReady.value && !isAgentEnvPreparing.value
)
const isControlStepComplete = computed(() =>
  Boolean(maafwConfig.Info.Controller && maafwConfig.Info.Resource)
)
const managedCapabilitiesLoading = computed(
  () => !managedCapabilitiesLoaded.value || managedApi.loading.value
)
const managedOperationRunning = computed(
  () =>
    managedApi.loading.value ||
    managedApi.progress.value.status === 'running' ||
    isProjectUpdateRunning.value ||
    isAgentEnvPreparing.value ||
    hasUnsavedChanges.value ||
    saveStatus.value === 'saving'
)
const managedConversionAvailable = computed(
  () =>
    formData.type === 'MaaFW' &&
    managedApi.capabilities.value?.available === true &&
    managedApi.capabilities.value.features.inPlaceConversion === true
)
const managedUnavailableReason = computed(() => {
  if (formData.type !== 'MaaFW') {
    return `${formData.type} 项目包暂不支持转换为通用托管项目；请保持普通项目，并使用其项目包提供的升级能力。`
  }
  return (
    managedApi.capabilities.value?.unavailableReason ||
    '请更新 automas-script-maafw-managed 至支持原地转换的版本；当前仍可保持普通项目继续使用。'
  )
})
const maxReachableStep = computed(() => {
  if (!isStepZeroReady.value) return 0
  if (!reuseComplete.value) return 1
  if (!isControlStepComplete.value) return 2
  if (isProjectUpdateRunning.value) return 3
  if (managedDecision.value === 'pending' || managedOperationRunning.value) return 4
  return 5
})
const STEP_TITLES = [
  '选择项目',
  '复用配置',
  '控制配置',
  '更新设置',
  '项目托管',
  '运行参数',
] as const
const stepItems = computed(() =>
  STEP_TITLES.map((title, index) => ({
    title,
    status: index === currentStep.value ? 'process' : index < currentStep.value ? 'finish' : 'wait',
  }))
)
const canAdvanceNext = computed(() => {
  if (currentStep.value === 0) return isStepZeroReady.value
  if (currentStep.value === 1) return reuseComplete.value
  if (currentStep.value === 2) return isControlStepComplete.value
  if (currentStep.value === 3) return !isProjectUpdateRunning.value
  if (currentStep.value === 4) {
    return managedDecision.value !== 'pending' && !managedOperationRunning.value
  }
  return true
})

const goToStep = (step: number) => {
  if (step < 0 || step > 5) return
  if (step > currentStep.value && step > maxReachableStep.value) return
  currentStep.value = step
}

const goCreateFirstUser = () => {
  if (importedUserId.value) {
    router.push(`/scripts/${scriptId}/users/${importedUserId.value}/edit/maafw`)
    return
  }
  router.push(`/scripts/${scriptId}/users/add/maafw`)
}

const handleReuseSkipped = () => {
  reuseComplete.value = true
}

const handleReuseApplied = async (result: MaaFWConfigurationApplyResult) => {
  importedUserId.value = result.createdUser.id
  reuseComplete.value = true
  await loadScript()
}

const loadManagedDecision = async () => {
  managedCapabilitiesLoaded.value = false
  try {
    if (formData.type !== 'MaaFW' && formData.type !== 'MaaFWManaged') {
      managedDecision.value = 'ordinary'
      return
    }
    const capabilities = await managedApi.getCapabilities()
    if (!capabilities.available) return
    const binding = await managedApi.getCurrentBinding(scriptId)
    if (binding.managed) managedDecision.value = 'managed'
  } catch (error) {
    logger.warn(`托管能力读取失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    managedCapabilitiesLoaded.value = true
  }
}

const chooseOrdinaryProject = () => {
  if (managedOperationRunning.value || managedDecision.value === 'managed') return
  managedDecision.value = 'ordinary'
}

const openManagedProjectManager = () => {
  if (managedDecision.value !== 'managed' && !managedConversionAvailable.value) return
  managerOpen.value = true
}

const handleManagedConverted = async () => {
  managedDecision.value = 'managed'
  await loadScript()
}

const handleManagedRefreshed = async () => {
  if (managedDecision.value !== 'managed') return
  await loadScript()
}

const handleFinish = () => {
  router.push(`/scripts/${scriptId}/edit/maafw`)
}

const handleCancel = () => {
  if (hasUnsavedChanges.value || isInitializing.value) {
    Modal.confirm({
      title: '有未保存的更改',
      content: '确定要离开吗？未保存的更改可能会丢失。',
      okText: '离开',
      cancelText: '继续引导',
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
    if (maafwConfig.Info.Path) {
      router.replace(`/scripts/${scriptId}/edit/maafw`)
      return
    }
    void loadManagedDecision()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`引导加载失败: ${errorMsg}`)
    router.replace('/scripts')
    return
  }
  isInitializing.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  dispose()
  managedApi.dispose()
})
</script>

<style scoped>
.wizard-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.script-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 0 8px;
  flex: 0 0 auto;
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

.wizard-content {
  flex: 1;
  min-height: 0;
  display: flex;
}

.wizard-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
}

.wizard-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 20px 24px;
  flex: 0 0 auto;
}

.wizard-card :deep(.ant-card-body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 24px;
  overflow: hidden;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 6px;
}

.config-steps {
  margin-bottom: 24px;
  flex: 0 0 auto;
}

.wizard-form {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.wizard-step-area {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  padding-right: 4px;
}

/* 引导卡片内统一使用白色背景，不使用 form-section-alt 的灰色底 */
.wizard-step-area :deep(.form-section-alt) {
  background: transparent;
  margin: 0;
  padding: 0;
}

.wizard-step-area :deep(.form-section) {
  margin-bottom: 32px;
}

.managed-step {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.managed-choice-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.managed-choice-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  min-height: 132px;
  padding: 22px;
  border: 1px solid var(--ant-color-border);
  border-radius: 10px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text-secondary);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s,
    box-shadow 0.2s,
    background 0.2s;
}

.managed-choice-card:hover:not(:disabled),
.managed-choice-card-selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  box-shadow: 0 0 0 2px var(--ant-color-primary-border);
}

.managed-choice-card:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.managed-choice-title {
  color: var(--ant-color-text);
  font-size: 17px;
  font-weight: 600;
}

.managed-capability-loading {
  display: flex;
  justify-content: center;
  padding: 24px;
}

.step-nav {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 0 0;
  margin-top: 16px;
  border-top: 1px solid var(--ant-color-border-secondary);
  flex: 0 0 auto;
}

.step-nav-button {
  height: 40px;
}

.step-nav-right {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.step-nav-main {
  min-width: 120px;
}

.step-fade-enter-active,
.step-fade-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.step-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.step-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 20px;
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .wizard-card :deep(.ant-card-body) {
    padding: 16px;
  }

  .managed-choice-grid {
    grid-template-columns: 1fr;
  }
}
</style>
