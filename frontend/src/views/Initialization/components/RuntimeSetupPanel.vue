<template>
  <div class="setup-panel">
    <div v-if="status === 'processing'" class="processing-state" aria-live="polite">
      <div class="working-symbol" aria-hidden="true">
        <LoadingOutlined spin />
      </div>
      <div class="state-copy">
        <h2>{{ title }}</h2>
        <p class="status-text">{{ message || t('init.msg.running') }}</p>
      </div>

      <div class="stage-progress">
        <div class="progress-heading">
          <span>{{ t('init.page.stageProgress') }}</span>
          <strong>
            {{
              progressIndeterminate
                ? t('init.page.progressing')
                : t('init.page.progressPercent', { percent: displayProgress })
            }}
          </strong>
        </div>
        <div
          v-if="progressIndeterminate"
          class="indeterminate-progress"
          role="progressbar"
          :aria-label="t('init.page.stageProgress')"
          :aria-valuetext="t('init.page.progressing')"
        >
          <span></span>
        </div>
        <a-progress
          v-else
          :percent="displayProgress"
          :show-info="false"
          :stroke-width="8"
          status="active"
        />
      </div>

      <div class="duration-note">
        <ClockCircleOutlined aria-hidden="true" />
        <span>{{ t('init.page.firstRunEstimate') }}</span>
      </div>

      <div class="elapsed-time">{{ t('init.page.elapsed', { time: elapsedText }) }}</div>
    </div>

    <div v-else-if="status === 'success'" class="success-state" aria-live="polite">
      <CheckCircleFilled class="success-icon" aria-hidden="true" />
      <div class="state-copy">
        <h2>{{ title }}</h2>
        <p class="status-text">{{ message || t('init.msg.stageDone') }}</p>
      </div>
    </div>

    <div v-else-if="status === 'failed'" class="failed-state" aria-live="assertive">
      <div class="failed-summary">
        <CloseCircleFilled class="failed-icon" aria-hidden="true" />
        <div class="failed-copy">
          <h2>{{ t('init.step.failed', { title }) }}</h2>
          <p>{{ message }}</p>
        </div>
      </div>

      <a-alert v-if="noticeText" type="warning" :message="noticeText" show-icon />

      <div v-if="showMirrorSelection" class="mirror-selection">
        <div class="section-heading">
          <h3>{{ t('init.step.chooseMirrorRetry') }}</h3>
          <span>{{ t('init.env.mirrorHelp') }}</span>
        </div>

        <div class="mirror-grid">
          <button
            v-for="mirror in mirrors"
            :key="mirror.key"
            type="button"
            class="mirror-option"
            :class="{ selected: selectedMirror === mirror.key }"
            :aria-pressed="selectedMirror === mirror.key"
            @click="$emit('update:selected-mirror', mirror.key)"
          >
            <span class="mirror-option-title">
              {{ mirror.name }}
              <a-tag v-if="mirror.recommended" color="blue">{{ t('init.env.recommended') }}</a-tag>
            </span>
            <span class="mirror-description">{{ mirror.description }}</span>
          </button>
        </div>
      </div>

      <div class="retry-actions">
        <a-space size="middle" wrap>
          <a-button v-if="showSkipButton" size="large" @click="$emit('skip')">
            {{ t('init.step.skip') }}
          </a-button>
          <a-button
            v-for="(action, index) in failureActions"
            :key="action.kind"
            :type="index === 0 ? 'primary' : 'default'"
            size="large"
            :loading="action.kind === 'run-doctor' && doctorRunning"
            @click="$emit('action', action.kind)"
          >
            {{ t(action.labelKey) }}
          </a-button>
        </a-space>
        <span v-if="countdown > 0" class="countdown-text">
          {{ t('init.step.autoRetryIn', { seconds: countdown }) }}
        </span>
      </div>

      <a-card
        v-if="doctorRunning || doctorChecks"
        size="small"
        :title="t('init.failure.doctorTitle')"
        class="detail-card"
      >
        <div v-if="doctorRunning" class="detail-placeholder">
          <LoadingOutlined spin />
          {{ t('init.failure.doctorRunning') }}
        </div>
        <div v-else-if="doctorChecks && doctorChecks.length > 0" class="doctor-checks">
          <div v-for="check in doctorChecks" :key="check.id" class="doctor-check">
            <a-tag :color="check.status === 'ok' ? 'green' : 'orange'">{{ check.name }}</a-tag>
            <span>{{ check.message || check.status }}</span>
          </div>
        </div>
        <div v-else class="detail-placeholder">{{ t('init.failure.doctorEmpty') }}</div>
      </a-card>

      <a-card
        v-if="failureLogs"
        size="small"
        :title="t('init.failure.logTitle')"
        class="failed-log-card"
      >
        <pre class="failure-log-output">{{ failureLogs }}</pre>
      </a-card>
    </div>

    <div v-else class="waiting-state">
      <ClockCircleOutlined class="waiting-icon" aria-hidden="true" />
      <h2>{{ title }}</h2>
      <p>{{ t('init.state.waiting') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CheckCircleFilled,
  ClockCircleOutlined,
  CloseCircleFilled,
  LoadingOutlined,
} from '@ant-design/icons-vue'
import type { RuntimeDoctorCheck } from '@/types/electron'
import type { MirrorConfig } from '@/types/mirror'
import type {
  FailureAction,
  FailureActionKind,
  FailureNoticeKind,
} from '@/utils/initializationDecision'

interface Props {
  title: string
  status: 'waiting' | 'processing' | 'success' | 'failed'
  message: string
  progress?: number
  progressIndeterminate?: boolean
  elapsedText?: string
  showMirrorSelection?: boolean
  showSkipButton?: boolean
  mirrors?: MirrorConfig[]
  selectedMirror?: string
  countdown?: number
  failureActions?: FailureAction[]
  failureNotice?: FailureNoticeKind | null
  failureLogs?: string
  doctorChecks?: RuntimeDoctorCheck[] | null
  doctorRunning?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  elapsedText: '00:00',
  progress: 0,
  progressIndeterminate: true,
  showMirrorSelection: false,
  showSkipButton: false,
  mirrors: () => [],
  selectedMirror: '',
  countdown: 0,
  failureActions: () => [],
  failureNotice: null,
  failureLogs: '',
  doctorChecks: null,
  doctorRunning: false,
})

defineEmits<{
  'update:selected-mirror': [value: string]
  action: [kind: FailureActionKind]
  skip: []
}>()

const { t } = useI18n()

const displayProgress = computed(() => Math.min(100, Math.max(0, Math.round(props.progress))))

const noticeText = computed(() => {
  switch (props.failureNotice) {
    case 'internal-error':
      return t('init.failure.internalErrorNotice')
    case 'contact-support':
      return t('init.failure.contactSupportNotice')
    default:
      return ''
  }
})
</script>

<style scoped>
.setup-panel {
  min-height: 0;
  height: 100%;
}

.processing-state,
.success-state,
.waiting-state {
  display: flex;
  min-height: 360px;
  height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px;
  text-align: center;
}

.working-symbol {
  display: grid;
  place-items: center;
  width: 72px;
  height: 72px;
  margin-bottom: 24px;
  border: 1px solid var(--ant-color-primary-border);
  border-radius: 50%;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-size: 32px;
}

.state-copy,
.stage-progress {
  inline-size: min(100%, 72ch);
}

.stage-progress {
  margin-top: 24px;
  text-align: left;
}

.progress-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.progress-heading strong {
  color: var(--ant-color-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.indeterminate-progress {
  height: 8px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--ant-color-fill-quaternary);
}

.indeterminate-progress span {
  display: block;
  width: 36%;
  height: 100%;
  border-radius: inherit;
  background: var(--ant-color-primary);
  animation: progress-sweep 1.4s ease-in-out infinite;
}

@keyframes progress-sweep {
  from {
    transform: translateX(-110%);
  }

  to {
    transform: translateX(310%);
  }
}

.state-copy h2,
.failed-copy h2,
.waiting-state h2 {
  margin: 0;
  color: var(--ant-color-text-heading);
  font-size: 24px;
  line-height: 1.35;
}

.status-text,
.waiting-state p {
  margin: 12px 0 0;
  color: var(--ant-color-text-secondary);
  font-size: 15px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.duration-note {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 24px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.duration-note :deep(.anticon) {
  color: var(--ant-color-text-tertiary);
}

.elapsed-time {
  margin-top: 16px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.success-icon {
  margin-bottom: 20px;
  color: var(--ant-color-success);
  font-size: 56px;
}

.failed-state {
  display: flex;
  min-height: 0;
  height: 100%;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
  overflow-y: auto;
}

.failed-summary {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 18px;
  border: 1px solid var(--ant-color-error-border);
  border-radius: 10px;
  background: var(--ant-color-error-bg);
}

.failed-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--ant-color-error);
  font-size: 28px;
}

.failed-copy {
  min-width: 0;
}

.failed-copy p {
  margin: 10px 0 0;
  color: var(--ant-color-text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.mirror-selection {
  padding: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
}

.section-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.section-heading h3 {
  margin: 0;
  color: var(--ant-color-text-heading);
  font-size: 16px;
}

.section-heading span {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.mirror-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
}

.mirror-option {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.mirror-option:hover,
.mirror-option:focus-visible,
.mirror-option.selected {
  border-color: var(--ant-color-primary);
}

.mirror-option:focus-visible {
  outline: 2px solid var(--ant-color-primary-border);
  outline-offset: 2px;
}

.mirror-option.selected {
  background: var(--ant-color-primary-bg);
}

.mirror-option-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 600;
}

.mirror-description {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.retry-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.countdown-text,
.detail-placeholder,
.doctor-check span {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.detail-card,
.failed-log-card {
  width: 100%;
}

.detail-placeholder {
  display: flex;
  align-items: center;
  gap: 8px;
}

.doctor-checks {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.doctor-check {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.failed-log-card :deep(.ant-card-body) {
  padding: 0;
}

.failure-log-output {
  max-height: 260px;
  margin: 0;
  padding: 14px 16px;
  overflow: auto;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.waiting-icon {
  margin-bottom: 20px;
  color: var(--ant-color-text-tertiary);
  font-size: 48px;
}

@media (prefers-reduced-motion: reduce) {
  .indeterminate-progress span {
    width: 100%;
    animation: none;
  }
}

@media (max-width: 720px) {
  .processing-state,
  .success-state,
  .waiting-state {
    min-height: 300px;
    padding: 24px 16px;
  }

  .failed-state {
    padding: 16px;
  }

  .section-heading,
  .retry-actions {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
