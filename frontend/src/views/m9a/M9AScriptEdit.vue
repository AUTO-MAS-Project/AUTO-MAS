<template>
  <ConfigEditShell :surface="false">
    <template #header>
      <ScriptEditHeader
        script-type="M9A"
        :title="pageTitle"
        :doc-url="MAS_DOC_URLS.scriptTypes.M9A"
        :logo-src="metadata.logo"
        :logo-alt="metadata.label"
        :logo-fallback-src="metadata.logo"
        :cancel-disabled="shellImporting"
        @cancel="handleCancel"
      />
    </template>

    <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
      <a-spin :spinning="pageLoading">
        <SectionCard v-if="isWizard" variant="card">
          <a-steps size="small" :current="currentStep" :items="stepItems" class="wizard-steps" />
        </SectionCard>

        <a-form
          ref="formRef"
          :aria-label="pageTitle"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
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
              :source-hint="t('core.edit.m9aFlavorSourceHint')"
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
              :beside-package-name-count="2"
              @change="handleChange"
              @controller-change="handleControllerChange"
              @resource-change="handleResourceChangeWithPackage"
              @select-launch-path="selectLaunchPath"
              @select-launcher-path="selectLauncherPath"
            >
              <!-- 游戏包名、等待时间之后各占一格：先登录方式（MAS 原生完成 B 服登录），再游戏更新 -->
              <template #besidePackageName="{ index }">
                <M9ALoginModeField
                  v-if="index === 0"
                  :maafw-config="maafwConfig"
                  @change="handleChange"
                />
                <M9AGameUpdateField v-else :maafw-config="maafwConfig" @change="handleChange" />
              </template>
            </ControlConfigSection>
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
      </a-spin>
    </ConfigLockPanel>
  </ConfigEditShell>
</template>

<script setup lang="ts">
// M9A（重返未来：1999）专属脚本页：用 MFW 脚本页的分节与编排层拼，与通用 MFW 脚本页结构相同，
// 只在控制方式分节里多「登录方式」「游戏更新」两格（M9A 后端独有的两个钩子）。
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import { ConfigEditShell, SectionCard } from '@/components/ui'
import { useI18n } from 'vue-i18n'
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
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
import M9AGameUpdateField from './M9AGameUpdateField.vue'
import M9ALoginModeField from './M9ALoginModeField.vue'

const { t } = useI18n()

const route = useRoute()

const scriptId = route.params.id as string

const metadata = SCRIPT_METADATA.M9A

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
  pageTitle,
  interfaceStats,
  handlePreviewInterface,
  handleCancel,
} = useMaaFWScriptPage({ scriptId, type: 'M9A' })
</script>

<style scoped src="../EditView/Script/MaaFWScriptEdit/scriptPage.css"></style>
