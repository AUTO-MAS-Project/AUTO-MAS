<template>
  <ScriptEditHeader
    :script-type="flavor.type"
    :title="pageTitle"
    :doc-url="flavor.docUrl"
    :logo-src="flavor.logo"
    :logo-alt="flavor.typeTagLabel"
    :cancel-disabled="shellImporting"
    @cancel="handleCancel"
  />

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
    <a-card :title="pageTitle" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag :color="flavor.typeTagColor" class="type-tag">{{ typeTagLabel }}</a-tag>
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
          <component
            :is="sections.basicInfo"
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
            :source-directory-label="t(flavor.scriptPage.text.sourceDirectoryKey)"
            :source-hint="t(flavor.scriptPage.text.sourceHintKey)"
            :source-placeholder="t(flavor.scriptPage.text.sourcePlaceholderKey)"
            :env-preparing="envPreparing"
            :env-ready="envReady"
            :env-failed="envFailed"
            :env-message="envMessage"
            :env-percent="envPercent"
            :env-logs="envLogs"
            :env-agents="envAgents"
            :env-outcome="envOutcome"
            @change="handleChange"
            @select-path="selectMaaFWPath"
            @preview-interface="handlePreviewInterface"
            @sync-source="syncFromSource"
          />
          <MaaFWFlavorSlot
            part="scriptPage"
            name="afterBasicInfo"
            :flavor="flavor"
            :context="flavorSlotContext"
            @change="handleChange"
          />
        </div>

        <div v-show="!isWizard || currentStep === 1">
          <MaaFWFlavorSlot
            part="scriptPage"
            name="beforeControl"
            :flavor="flavor"
            :context="flavorSlotContext"
            @change="handleChange"
          />
          <component
            :is="sections.control"
            :script-id="scriptId"
            :maafw-config="maafwConfig"
            :preview-data="previewData"
            :interface-loading="previewLoading"
            :emulator-loading="emulatorLoading"
            :emulator-options-ready="emulatorOptionsReady"
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
            :effective-resource-name="effectiveResourceName"
            :adb-control-strategy-items="adbControlStrategyItems"
            :selected-emulator-label="selectedEmulatorLabel"
            :interface-dependent-disabled="interfaceDependentDisabled"
            @change="handleChange"
            @controller-change="handleControllerChange"
            @resource-change="handleResourceChangeWithPackage"
            @emulator-select-change="handleEmulatorSelectChange"
            @select-launch-path="selectLaunchPath"
          >
            <template v-if="hasBesidePackageName" #besidePackageName>
              <MaaFWFlavorSlot
                part="scriptPage"
                name="besidePackageName"
                :flavor="flavor"
                :context="flavorSlotContext"
                @change="handleChange"
              />
            </template>
          </component>
          <MaaFWFlavorSlot
            part="scriptPage"
            name="afterControl"
            :flavor="flavor"
            :context="flavorSlotContext"
            @change="handleChange"
          />
        </div>

        <div v-show="!isWizard || currentStep === 2">
          <component
            :is="sections.update"
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
          <MaaFWFlavorSlot
            part="scriptPage"
            name="afterUpdate"
            :flavor="flavor"
            :context="flavorSlotContext"
            @change="handleChange"
          />
        </div>

        <div v-show="!isWizard || currentStep === 3">
          <component
            :is="sections.run"
            :maafw-config="maafwConfig"
            :daily-once-tasks="dailyOnceTasks"
            :weekly-once-tasks="weeklyOnceTasks"
            :monthly-once-tasks="monthlyOnceTasks"
            :period-task-options="periodTaskOptions"
            :interface-dependent-disabled="interfaceDependentDisabled"
            @change="handleChange"
            @period-task-change="handlePeriodTaskChange"
          />
          <MaaFWFlavorSlot
            part="scriptPage"
            name="afterRun"
            :flavor="flavor"
            :context="flavorSlotContext"
            @change="handleChange"
          />
        </div>
      </a-form>

      <!-- 只在引导最后一步出现：外壳里配好的实例导入成用户，扫不到就整块不显示 -->
      <component
        :is="sections.shellImport"
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
          {{ t('edit.previousStep') }}
        </a-button>
        <a-button
          v-if="currentStep < stepItems.length - 1"
          type="primary"
          size="large"
          :disabled="!canLeaveCurrentStep"
          @click="currentStep += 1"
        >
          {{ t('edit.next') }}
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
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { updateChannelOptions, updateSourceOptions } from '@/composables/useMaaFWScriptConfig'
import { resolveMaaFWFlavorSlot, useMaaFWSections } from '@/composables/useMaaFWFlavor'
import MaaFWFlavorSlot from '@/views/EditView/MaaFWFlavor/MaaFWFlavorSlot.vue'
// MFW 默认分节静态引入：通用 MFW 打开不闪；特调的替换分节由注册表按需加载
import { MAAFW_SCRIPT_PAGE_SECTIONS, useMaaFWScriptPage } from './MaaFWScriptEdit/pageKit'

const { t } = useI18n()

const route = useRoute()

const scriptId = route.params.id as string

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
  flavor,
  emulatorLoading,
  emulatorOptionsReady,
  emulatorDeviceLoading,
  emulatorOptions,
  emulatorDeviceOptions,
  emulatorTypeById,
  controllerOptions,
  effectiveControllerName,
  effectiveControllerType,
  isAdbController,
  isDesktopController,
  resourceOptions,
  effectiveResourceName,
  interfaceDependentDisabled,
  selectedEmulatorLabel,
  adbControlStrategyItems,
  handleControllerChange,
  handleResourceChangeWithPackage,
  handleEmulatorSelectChange,
  selectLaunchPath,
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
  flavorSlotContext,
} = useMaaFWScriptPage({ scriptId })

// 各分节：默认用 MFW 的，当前特调替换了哪节就换成它的（契约见 MaaFWFlavor/sectionContracts）
const sections = useMaaFWSections(flavor, 'scriptPage', MAAFW_SCRIPT_PAGE_SECTIONS)

// 包名旁的插入点在 control 分节里面：只有当前特调登记了组件才填这个 slot，否则包名独占一行
const hasBesidePackageName = computed(
  () => resolveMaaFWFlavorSlot(flavor.value, 'scriptPage', 'besidePackageName').length > 0
)
</script>

<style scoped>
.wizard-steps {
  margin-bottom: 28px;
}

.wizard-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
  padding-top: 20px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.script-edit-content {
  flex: 1;
}

.config-card {
  border-radius: 16px;
  box-shadow: none;
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
}

.config-form {
  max-width: none;
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 20px;
}
</style>
