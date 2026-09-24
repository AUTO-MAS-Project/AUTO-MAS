<template>
  <div class="launch-failure" aria-live="assertive">
    <div class="failure-body">
      <h2 class="failure-title">
        <i class="failure-dot" aria-hidden="true"></i>
        {{ t('init.step.failed', { title }) }}
      </h2>

      <p v-if="message" class="failure-message">{{ message }}</p>
      <p v-if="noticeText" class="failure-notice">{{ noticeText }}</p>

      <div class="failure-actions">
        <a-button
          v-for="(action, index) in failureActions"
          :key="action.kind"
          :type="index === 0 ? 'primary' : 'text'"
          :loading="action.kind === 'run-doctor' && doctorRunning"
          @click="emit('action', action.kind)"
        >
          {{ t(action.labelKey) }}
        </a-button>
        <a-button v-if="docsUrl" type="text" @click="emit('open-docs')">
          {{ t('init.backend.viewDocs') }}
        </a-button>
      </div>

      <div v-if="showMirrorSelection && mirrors.length > 0" class="failure-mirrors">
        <p class="mirrors-title">{{ t('init.failure.mirrorTitle') }}</p>
        <button
          v-for="mirror in mirrors"
          :key="mirror.key"
          type="button"
          class="mirror-option"
          :class="{ selected: selectedMirror === mirror.key }"
          role="radio"
          :aria-checked="selectedMirror === mirror.key"
          @click="emit('update:selected-mirror', mirror.key)"
        >
          <span class="mirror-radio" aria-hidden="true"></span>
          <span class="mirror-name">{{ mirror.name }}</span>
          <span class="mirror-note">
            {{ mirror.recommended ? t('init.failure.mirrorRecommended') : mirror.description }}
          </span>
        </button>
      </div>

      <details
        v-if="hasDetails"
        class="failure-details"
        :open="detailsOpen"
        @toggle="detailsOpen = ($event.target as HTMLDetailsElement).open"
      >
        <summary>{{ t('init.failure.details') }}</summary>

        <div v-if="doctorRunning" class="details-line">{{ t('init.failure.doctorRunning') }}</div>
        <template v-else-if="doctorChecks">
          <div v-if="doctorChecks.length > 0" class="doctor-checks">
            <span v-for="check in doctorChecks" :key="check.id" class="doctor-check">
              {{ check.name }}
              <b :class="{ bad: check.status !== 'ok' }">{{ check.message || check.status }}</b>
            </span>
          </div>
          <div v-else class="details-line">{{ t('init.failure.doctorEmpty') }}</div>
        </template>

        <pre v-if="failureLogs" class="failure-log">{{ failureLogs }}</pre>
      </details>

      <p v-if="showSkipButton" class="failure-skip">
        <button type="button" @click="emit('skip')">{{ t('init.step.skip') }}</button>
        {{ t('init.step.skipConsequence') }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { RuntimeDoctorCheck } from '@/types/electron'
import type { MirrorConfig } from '@/types/mirror'
import type {
  FailureAction,
  FailureActionKind,
  FailureNoticeKind,
} from '@/utils/initializationDecision'

defineOptions({ name: 'LaunchFailure' })

interface Props {
  /** 出问题的那一段，例如「安装依赖」。 */
  title: string
  /** 失败原因原文，来自 Runtime 或安装器。 */
  message?: string
  failureActions?: FailureAction[]
  failureNotice?: FailureNoticeKind | null
  failureLogs?: string
  showMirrorSelection?: boolean
  mirrors?: MirrorConfig[]
  selectedMirror?: string
  doctorChecks?: RuntimeDoctorCheck[] | null
  doctorRunning?: boolean
  showSkipButton?: boolean
  /** 有排障文档可看时给出链接，目前只有后端启动段有。 */
  docsUrl?: string
}

const props = withDefaults(defineProps<Props>(), {
  message: '',
  failureActions: () => [],
  failureNotice: null,
  failureLogs: '',
  showMirrorSelection: false,
  mirrors: () => [],
  selectedMirror: '',
  doctorChecks: null,
  doctorRunning: false,
  showSkipButton: false,
  docsUrl: '',
})

const emit = defineEmits<{
  action: [kind: FailureActionKind]
  'update:selected-mirror': [value: string]
  skip: []
  'open-docs': []
}>()

const { t } = useI18n()

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

// 诊断和日志合进同一个折叠，两者都没有时整块不出现。
const hasDetails = computed(
  () => Boolean(props.failureLogs) || props.doctorRunning || props.doctorChecks !== null
)

const detailsOpen = ref(false)

// 「检查运行环境」的结果就落在这个折叠里，跑完不自动展开的话点了等于没反应。
watch(
  () => props.doctorRunning || props.doctorChecks !== null,
  hasDoctorResult => {
    if (hasDoctorResult) detailsOpen.value = true
  }
)
</script>

<style scoped>
.launch-failure {
  display: flex;
  inline-size: 100%;
  height: 100%;
  min-height: 0;
  justify-content: center;
  overflow-y: auto;
  padding: 44px 32px;
}

/* 与等待态同一个视觉锚点：内容放得下就上下居中，放不下时自动外边距归零，
   从顶部开始滚动（`align-items: center` 在溢出时会把顶部裁掉，不能用）。 */
.failure-body {
  inline-size: min(100%, 520px);
  margin-block: auto;
}

.failure-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  color: var(--ant-color-text);
  font-size: 20px;
  font-weight: 500;
  line-height: 1.5;
}

.failure-dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ant-color-error);
}

.failure-message {
  margin: 12px 0 0;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.failure-notice {
  margin: 10px 0 0;
  color: var(--ant-color-warning-text, var(--ant-color-text-secondary));
  font-size: 13px;
  line-height: 1.7;
}

.failure-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 22px;
}

.failure-mirrors {
  margin-top: 18px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  overflow: hidden;
}

.mirrors-title {
  margin: 0;
  padding: 9px 14px;
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.mirror-option {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  border: 0;
  border-top: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.mirror-option:hover {
  background: var(--ant-color-fill-quaternary);
}

.mirror-radio {
  flex: none;
  width: 13px;
  height: 13px;
  border: 1px solid var(--ant-color-border);
  border-radius: 50%;
}

.mirror-option.selected .mirror-radio {
  border: 4px solid var(--ant-color-primary);
}

.mirror-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mirror-note {
  margin-left: auto;
  padding-left: 12px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  white-space: nowrap;
}

.failure-details {
  margin-top: 16px;
  font-size: 13px;
}

.failure-details summary {
  color: var(--ant-color-text-secondary);
  cursor: pointer;
}

.details-line {
  margin-top: 10px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.doctor-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin-top: 10px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.doctor-check b {
  font-weight: 500;
  color: var(--ant-color-text-secondary);
}

.doctor-check b.bad {
  color: var(--ant-color-error);
}

.failure-log {
  max-height: 240px;
  margin: 10px 0 0;
  padding: 11px 13px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text-secondary);
  font-family: Consolas, 'Courier New', monospace;
  font-size: 11.5px;
  line-height: 1.75;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.failure-skip {
  margin: 26px 0 0;
  color: var(--ant-color-text-tertiary);
  font-size: 12.5px;
}

.failure-skip button {
  padding: 0;
  border: 0;
  background: none;
  color: var(--ant-color-text-tertiary);
  font: inherit;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.failure-skip button:hover {
  color: var(--ant-color-text-secondary);
}

@media (max-width: 720px) {
  .launch-failure {
    padding: 28px 20px;
  }
}
</style>
