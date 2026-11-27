<template>
  <ScriptEditLayout
    :script-id="scriptId"
    :loading="pageLoading"
    :header="{
      scriptType: 'MSS',
      title: pageTitle,
      docUrl: MAS_DOC_URLS.scripts,
      logoSrc: metadata.logo,
      logoAlt: metadata.label,
      logoFallbackSrc: metadata.logo,
      cancelDisabled: shellImporting,
    }"
    :form="{ model: formData, rules }"
    :body-form="{ model: maafwConfig }"
    :form-label="pageTitle"
    :binding-visible="false"
    @cancel="handleCancel"
  >
    <template #before-basic>
      <SectionCard v-if="isWizard" variant="card">
        <a-steps size="small" :current="currentStep" :items="stepItems" class="wizard-steps" />
      </SectionCard>
    </template>

    <template #basic>
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
          :source-hint="t('core.edit.mssFlavorSourceHint')"
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
    </template>

    <template #game-config>
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
        >
          <template #notice>
            <MSSControllerHint :controller-type="effectiveControllerType" />
          </template>
        </ControlConfigSection>
      </div>
    </template>

    <template #run>
      <div v-show="!isWizard || currentStep === 2">
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
    </template>

    <template #program-update>
      <div v-show="!isWizard || currentStep === 3">
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
    </template>

    <template #after-form>
      <!-- 只在引导最后一步出现：外壳里配好的实例导入成用户，扫不到就整块不显示 -->
      <ShellInstanceImportSection
        v-if="isWizard && currentStep === stepItems.length - 1 && shellInstances.length > 0"
        v-model:selected-ids="selectedShellInstanceIds"
        v-model:import-hotkeys="importShellHotkeys"
        :instances="shellInstances"
        :disabled="shellImporting"
      />

      <SectionCard v-if="isWizard" variant="card">
        <div class="wizard-actions">
          <a-button v-if="currentStep > 0" :disabled="shellImporting" @click="currentStep -= 1">
            {{ t('core.edit.previousStep') }}
          </a-button>
          <a-button
            v-if="currentStep < stepItems.length - 1"
            type="primary"
            :disabled="!canLeaveCurrentStep"
            @click="currentStep += 1"
          >
            {{ t('core.edit.next') }}
          </a-button>
          <a-button v-else type="primary" :loading="shellImporting" @click="handleFinishWizard">
            {{ finishButtonLabel }}
          </a-button>
        </div>
      </SectionCard>
    </template>
  </ScriptEditLayout>
</template>

<script setup lang="ts">
// MSS（星塔旅人 / MaaStellaSora）专属脚本页：用 MFW 脚本页的分节与编排层拼，与通用 MFW 脚本页结构相同，
// 控制配置卡片内多一条「只适配桌面端」的提醒。
import ScriptEditLayout from '@/components/ScriptEditLayout.vue'
import { SectionCard } from '@/components/ui'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { updateChannelOptions, updateSourceOptions } from '@/composables/useMaaFWScriptConfig'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { SCRIPT_METADATA } from '@/utils/scriptMetadata'
import {
  BasicInfoSection,
  ControlConfigSection,
  RunConfigSection,
  ShellInstanceImportSection,
  UpdateSettingsSection,
  useMaaFWScriptPage,
} from '@/views/EditView/Script/MaaFWScriptEdit/pageKit'
import MSSControllerHint from './MSSControllerHint.vue'

const { t } = useI18n()

const route = useRoute()

const scriptId = route.params.id as string

const metadata = SCRIPT_METADATA.MSS

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
  pageTitle,
  interfaceStats,
  handlePreviewInterface,
  handleCancel,
} = useMaaFWScriptPage({ scriptId, type: 'MSS' })
</script>

<style scoped src="../EditView/Script/MaaFWScriptEdit/scriptPage.css"></style>
