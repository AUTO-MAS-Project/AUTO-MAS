<template>
  <div class="initialization-page">
    <header class="page-header">
      <h1>{{ pageTitle }}</h1>
    </header>

    <section class="initialization-shell">
      <aside class="stage-sidebar" :aria-label="t('init.page.stageTitle')">
        <h2 class="stage-sidebar-title">{{ t('init.page.stageTitle') }}</h2>

        <ol class="stage-list">
          <li
            v-for="(stage, index) in presentationStages"
            :key="stage.key"
            class="stage-item"
            :class="[stage.status, { active: stage.key === activeStageKey }]"
            :aria-label="`${t(`init.steps.${stage.key}`)}，${t(stageStatusKey(stage.status))}`"
            :aria-current="stage.key === activeStageKey ? 'step' : undefined"
          >
            <div class="stage-marker" aria-hidden="true">
              <CheckCircleFilled v-if="stage.status === 'success'" />
              <CloseCircleFilled v-else-if="stage.status === 'failed'" />
              <LoadingOutlined v-else-if="stage.status === 'processing'" spin />
              <span v-else>{{ index + 1 }}</span>
            </div>
            <div class="stage-copy">
              <strong>{{ t(`init.steps.${stage.key}`) }}</strong>
            </div>
          </li>
        </ol>
      </aside>

      <main class="stage-content">
        <RuntimeBackendStartPanel
          v-if="currentStep.key === 'backend'"
          :show-skip-button="currentStep.canSkip"
          :elapsed-text="elapsedText"
          @update:status="handleBackendStatusChange"
          @complete="handleBackendComplete"
          @error="handleBackendError"
          @skip="handleSkip"
        />
        <RuntimeSetupPanel
          v-else
          v-bind="currentStepProps"
          @update:selected-mirror="handleMirrorSelect"
          @action="handleFailureAction"
          @skip="handleSkip"
        />
      </main>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { CheckCircleFilled, CloseCircleFilled, LoadingOutlined } from '@ant-design/icons-vue'
import RuntimeBackendStartPanel from './components/RuntimeBackendStartPanel.vue'
import RuntimeSetupPanel from './components/RuntimeSetupPanel.vue'
import { useInitializationFlow } from './useInitializationFlow'

defineOptions({ name: 'RuntimeInitializationPage' })

const { t } = useI18n()
const {
  activeStageKey,
  currentStep,
  currentStepProps,
  elapsedText,
  handleBackendComplete,
  handleBackendError,
  handleBackendStatusChange,
  handleFailureAction,
  handleMirrorSelect,
  handleSkip,
  pageTitle,
  presentationStages,
  stageStatusKey,
} = useInitializationFlow()
</script>

<style scoped>
.initialization-page {
  display: flex;
  min-height: 100%;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  padding: clamp(20px, 3vw, 40px);
  background: var(--ant-color-bg-layout);
  color: var(--ant-color-text);
}

.page-header {
  width: 100%;
}

.page-header h1 {
  margin: 0;
  color: var(--ant-color-text-heading);
  font-size: 28px;
  line-height: 1.35;
}

.initialization-shell {
  display: grid;
  grid-template-columns: clamp(15rem, 24%, 19rem) minmax(0, 1fr);
  width: 100%;
  min-height: 460px;
  flex: 1;
  overflow: hidden;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
  background: var(--ant-color-bg-container);
}

.stage-sidebar {
  display: flex;
  flex-direction: column;
  padding: 24px 20px;
  border-right: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-fill-quaternary);
}

.stage-sidebar-title {
  margin: 0;
  color: var(--ant-color-text-heading);
  font-size: 16px;
}

.stage-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 24px 0;
  padding: 0;
  list-style: none;
}

.stage-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 8px;
}

.stage-item.active {
  border-color: var(--ant-color-primary-border);
  background: var(--ant-color-primary-bg);
}

.stage-marker {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 1px solid var(--ant-color-border);
  border-radius: 50%;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  font-weight: 600;
}

.stage-item.processing .stage-marker {
  border-color: var(--ant-color-primary-border);
  color: var(--ant-color-primary);
}

.stage-item.success .stage-marker {
  border-color: transparent;
  color: var(--ant-color-success);
  font-size: 22px;
}

.stage-item.failed .stage-marker {
  border-color: transparent;
  color: var(--ant-color-error);
  font-size: 22px;
}

.stage-copy {
  min-width: 0;
}

.stage-copy strong {
  display: block;
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
}

.stage-content {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

@media (max-width: 760px) {
  .initialization-page {
    gap: 16px;
    padding: 20px 16px;
  }

  .page-header h1 {
    font-size: 24px;
  }

  .initialization-shell {
    display: flex;
    min-height: 0;
    flex-direction: column;
    overflow: visible;
  }

  .stage-sidebar {
    padding: 16px;
    border-right: 0;
    border-bottom: 1px solid var(--ant-color-border-secondary);
  }

  .stage-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin: 16px 0 0;
  }

  .stage-item {
    grid-template-columns: 26px minmax(0, 1fr);
  }

  .stage-content {
    overflow: visible;
  }
}

@media (max-width: 480px) {
  .stage-list {
    grid-template-columns: 1fr;
  }
}
</style>
