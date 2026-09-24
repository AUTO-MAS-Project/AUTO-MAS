<template>
  <div class="launch-page">
    <div class="launch-wash" aria-hidden="true"></div>

    <RuntimeBackendStartPanel
      v-if="isBackendStep"
      :retrying="flowKind === 'startup'"
      :show-skip-button="currentStep.canSkip"
      @update:status="handleBackendStatusChange"
      @complete="handleBackendComplete"
      @error="handleBackendError"
      @skip="handleSkip"
    />
    <LaunchFailure
      v-else-if="hasFailed"
      v-bind="failureProps"
      @action="handleFailureAction"
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
      :action-label="t('launch.viewLog')"
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

defineOptions({ name: 'RuntimeInitializationPage' })

const { t } = useI18n()
const {
  currentStep,
  failureProps,
  flowKind,
  handleBackendComplete,
  handleBackendError,
  handleBackendStatusChange,
  handleFailureAction,
  handleMirrorSelect,
  handleSkip,
  hasFailed,
  isBackendStep,
  launchSteps,
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
