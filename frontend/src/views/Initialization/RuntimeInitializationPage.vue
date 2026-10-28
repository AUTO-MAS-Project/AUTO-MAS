<template>
  <div class="launch-page">
    <div class="launch-wash" aria-hidden="true"></div>
    <div v-if="!resources.requested || resources.ready" class="launch-language">
      <BootstrapLanguageSelect />
    </div>

    <I18nResourceGate
      v-if="resources.requested && !resources.ready"
      @retry="handleLocalEnterApp(true)"
      @recover="recoverInitialization"
    />
    <RuntimeBackendStartPanel
      v-else-if="isBackendStep"
      :retrying="flowKind === 'startup'"
      :runtime-mode="runtimeMode"
      :show-skip-button="currentStep.canSkip"
      @update:status="handleBackendStatusChange"
      @complete="handleBackendComplete"
      @error="handleBackendError"
      @recovery-action="handleBackendRecoveryAction"
      @runtime-updated="handleRuntimeUpdated"
      @skip="handleSkip"
    />
    <LaunchFailure
      v-else-if="hasFailed"
      v-bind="failureProps"
      @action="handleFailureAction"
      @runtime-updated="handleRuntimeUpdated"
      @update:selected-mirror="handleMirrorSelect"
      @skip="handleSkip"
    />
    <LaunchStatus
      v-else
      :title="statusTitle"
      :hint="statusHint"
      :progress="statusProgress"
      :details="statusDetails"
      :steps="launchSteps"
      :action-label="t('bootstrap.launch.viewLog')"
      @action="openLaunchLogWindow('初始化流程')"
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import LaunchStatus from '@/components/LaunchStatus.vue'
import { openLaunchLogWindow } from '@/utils/launch'
import LaunchFailure from './components/LaunchFailure.vue'
import RuntimeBackendStartPanel from './components/RuntimeBackendStartPanel.vue'
import { useInitializationFlow } from './useInitializationFlow'
import BootstrapLanguageSelect from '@/components/BootstrapLanguageSelect.vue'
import I18nResourceGate from '@/components/I18nResourceGate.vue'
import { useBackendI18nStore } from '@/stores/backendI18n'
import { cancelAppEntry } from '@/utils/appEntry'
import { isDevelopmentEnvironment as isDev } from '@/utils/environment'

defineOptions({ name: 'RuntimeInitializationPage' })

const { t } = useI18n()
const resources = useBackendI18nStore()
const recoverInitialization = async () => {
  cancelAppEntry()
  resources.cancelEntry()
  if (isDev) await handleLocalEnterApp(true)
}
const {
  currentStep,
  failureProps,
  flowKind,
  handleBackendComplete,
  handleBackendError,
  handleBackendRecoveryAction,
  handleBackendStatusChange,
  handleFailureAction,
  handleMirrorSelect,
  handleRuntimeUpdated,
  handleSkip,
  handleLocalEnterApp,
  hasFailed,
  isBackendStep,
  launchSteps,
  runtimeMode,
  statusDetails,
  statusHint,
  statusProgress,
  statusTitle,
} = useInitializationFlow()
</script>

<style scoped>
.launch-page {
  position: relative;
  display: grid;
  place-items: center;
  height: 100%;
  min-height: 100%;
  background: var(--ant-color-bg-layout);
  color: var(--ant-color-text);
}

.launch-language {
  position: absolute;
  top: 16px;
  right: 24px;
  z-index: 1;
}

/* 与标题栏 logo 的主题色晕开同一套语言，给空屏一点纵深。 */
.launch-wash {
  position: absolute;
  inset: 0;
  background: radial-gradient(
    56% 46% at 50% 42%,
    var(--ant-color-primary) 0%,
    rgba(0, 0, 0, 0) 72%
  );
  opacity: 0.09;
  pointer-events: none;
}

html.dark .launch-wash {
  opacity: 0.16;
}
</style>
