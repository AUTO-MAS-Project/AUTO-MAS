<template>
  <ScriptEditHeader
    script-type="MaaFW"
    :title="pageTitle"
    :doc-url="MAS_DOC_URLS.scripts"
    :logo-src="headerLogo"
    :logo-alt="metadata.label"
    :logo-fallback-src="metadata.logo"
    :cancel-disabled="shellImporting"
    @cancel="handleCancel"
  />

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
    <a-card :title="pageTitle" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag :color="metadata.typeTagColor" class="type-tag">{{ typeTagLabel }}</a-tag>
      </template>

      <a-steps
        v-if="isWizard"
        size="small"
        :current="currentStep"
        :items="stepItems"
        class="wizard-steps"
      />

      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div v-show="!isWizard || currentStep === 0">
          <BasicInfoSection
            :maafw-config="maafwConfig"
            :form-data="formData"
            :rules="rules"
            :preview-data="previewData"
            :interface-loading="previewLoading"
            :preview-project-title="previewProjectTitle"
            :interface-stats="interfaceStats"
            :update-applying="updateApplying"
            :embedded-status="embeddedStatus"
            :embedded-busy="embeddedBusy"
            :import-percent="importPercent"
            :import-message="importMessage"
            :import-error="importError"
            :preview-error="previewError"
            :env-preparing="envPreparing"
            :env-ready="envReady"
            :env-failed="envFailed"
            :env-message="envMessage"
            :env-percent="envPercent"
            :env-logs="envLogs"
            :env-agents="envAgents"
            :env-outcome="envOutcome"
            :is-wizard="isWizard"
            @change="handleChange"
            @select-path="selectMaaFWPath"
            @preview-interface="handlePreviewInterface"
            @sync-source="syncFromSource"
          />
        </div>

        <div v-show="!isWizard || currentStep === 1">
          <ControlConfigSection
            :script-id="scriptId"
            :maafw-config="maafwConfig"
            :preview-data="previewData"
            :interface-loading="previewLoading"
            :controller-options="controllerOptions"
            :effective-controller-name="effectiveControllerName"
            :effective-controller-type="effectiveControllerType"
            :is-adb-controller="isAdbController"
            :is-desktop-controller="isDesktopController"
            :resource-options="resourceOptions"
            :effective-resource-name="effectiveResourceName"
            :adb-control-strategy-items="adbControlStrategyItems"
            :interface-dependent-disabled="interfaceDependentDisabled"
            @change="handleChange"
            @controller-change="handleControllerChange"
            @resource-change="handleResourceChangeWithPackage"
            @select-launch-path="selectLaunchPath"
            @select-launcher-path="selectLauncherPath"
          />
        </div>

        <div v-show="!isWizard || currentStep === 2">
          <UpdateSettingsSection
            :script-id="scriptId"
            :maafw-config="maafwConfig"
            :preview-data="previewData"
            :is-auto-update-disabled="isAutoUpdateDisabled"
            :update-checking="updateChecking"
            :update-applying="updateApplying"
            :update-error="updateError"
            :update-result="updateResult"
            :update-progress="updateProgress"
            :cdk-prefilled="cdkPrefilled"
            :update-source-options="updateSourceOptions"
            :update-channel-options="updateChannelOptions"
            @change="handleChange"
            @check-update="runUpdateCheck"
            @apply-update="runUpdateApply"
          />
        </div>

        <div v-show="!isWizard || currentStep === 3">
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
        </div>
      </a-form>

      <!-- 只在引导最后一步出现：外壳里配好的实例导入成用户，扫不到就整块不显示 -->
      <ShellInstanceImportSection
        v-if="isWizard && currentStep === stepItems.length - 1 && shellInstances.length > 0"
        v-model:selected-ids="selectedShellInstanceIds"
        v-model:import-hotkeys="importShellHotkeys"
        :instances="shellInstances"
        :disabled="shellImporting"
      />

      <div v-if="isWizard" class="wizard-actions">
        <a-button
          v-if="currentStep > 0"
          size="large"
          :disabled="shellImporting"
          @click="currentStep -= 1"
        >
          {{ t('core.edit.previousStep') }}
        </a-button>
        <a-button
          v-if="currentStep < stepItems.length - 1"
          type="primary"
          size="large"
          :disabled="!canLeaveCurrentStep"
          @click="currentStep += 1"
        >
          {{ t('core.edit.next') }}
        </a-button>
        <a-button
          v-else
          type="primary"
          size="large"
          :loading="shellImporting"
          @click="handleFinishWizard"
        >
          {{ finishButtonLabel }}
        </a-button>
      </div>
    </a-card>
  </ConfigLockPanel>
</template>

<script setup lang="ts">
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { updateChannelOptions, updateSourceOptions } from '@/composables/useMaaFWScriptConfig'
import { buildMaaFWScriptIconUrl } from '@/utils/maafwProjectIcon'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'
// 通用 MFW 脚本页：只按 interface 渲染，不带任何专项分支（M9A、MSS 各有专属页面）
import {
  BasicInfoSection,
  ControlConfigSection,
  RunConfigSection,
  ShellInstanceImportSection,
  UpdateSettingsSection,
  useMaaFWScriptPage,
} from './MaaFWScriptEdit/pageKit'

const { t } = useI18n()

const route = useRoute()

const scriptId = route.params.id as string

const metadata = SCRIPT_METADATA.MaaFW

const formRef = ref<FormInstance>()

const {
  pageLoading,
  previewLoading,
  previewData,
  previewError,
  maafwConfig,
  formData,
  rules,
  handleChange,
  controllerOptions,
  effectiveControllerName,
  effectiveControllerType,
  isAdbController,
  isDesktopController,
  resourceOptions,
  effectiveResourceName,
  interfaceDependentDisabled,
  adbControlStrategyItems,
  handleControllerChange,
  handleResourceChangeWithPackage,
  selectLaunchPath,
  selectLauncherPath,
  dailyOnceTasks,
  weeklyOnceTasks,
  monthlyOnceTasks,
  periodTaskOptions,
  handlePeriodTaskChange,
  envPreparing,
  envReady,
  envFailed,
  envMessage,
  envPercent,
  envLogs,
  envAgents,
  envOutcome,
  embeddedStatus,
  embeddedBusy,
  importPercent,
  importMessage,
  importError,
  selectMaaFWPath,
  syncFromSource,
  isAutoUpdateDisabled,
  updateChecking,
  updateApplying,
  updateError,
  updateResult,
  updateProgress,
  runUpdateCheck,
  runUpdateApply,
  cdkPrefilled,
  isWizard,
  currentStep,
  stepItems,
  canLeaveCurrentStep,
  shellInstances,
  selectedShellInstanceIds,
  importShellHotkeys,
  shellImporting,
  finishButtonLabel,
  handleFinishWizard,
  previewProjectTitle,
  typeTagLabel,
  pageTitle,
  interfaceStats,
  handlePreviewInterface,
  handleCancel,
} = useMaaFWScriptPage({ scriptId, type: 'MaaFW' })

// 面包屑图标：与脚本列表同一个口径取项目图标（不等预览），取不到由 ScriptEditHeader 回退到
// MFW 图标。每读到一次 interface 换一次地址：老脚本首次打开时预览才顺手导入、向导里刚导入、
// 更新换了图标，都会重新取一次。
const projectIconRevision = ref(0)
watch(previewData, data => {
  if (data) projectIconRevision.value += 1
})
const headerLogo = computed(() => buildMaaFWScriptIconUrl(scriptId, projectIconRevision.value))
</script>

<style scoped src="./MaaFWScriptEdit/scriptPage.css"></style>
