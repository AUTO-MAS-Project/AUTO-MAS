<template>
  <div class="step-panel">
    <h3>{{ title }}</h3>

    <!-- 进行中状态 -->
    <div v-if="status === 'processing'" class="processing-state">
      <div class="status-text">{{ message }}</div>
      <a-progress v-if="showProgress" :percent="progress" :status="progressStatus">
        <template #format="percent">
          <span>{{ percent }}%</span>
        </template>
      </a-progress>

      <!-- 详细信息展示区域 -->
      <div class="detail-info-container">
        <!-- 环境检查信息（Python/Pip/Git） -->
        <div
          v-if="checkInfo && (checkInfo.exeExists !== undefined || checkInfo.canRun !== undefined)"
          class="info-section"
        >
          <div class="info-title">{{ t('init.check.envTitle') }}</div>
          <div class="info-items">
            <a-tag
              v-if="checkInfo.exeExists !== undefined"
              :color="checkInfo.exeExists ? 'green' : 'orange'"
            >
              {{ t('init.check.executable') }}:
              {{ checkInfo.exeExists ? t('init.value.exists') : t('init.value.notExists') }}
            </a-tag>
            <a-tag
              v-if="checkInfo.canRun !== undefined"
              :color="checkInfo.canRun ? 'green' : 'orange'"
            >
              {{ t('init.check.runState') }}:
              {{ checkInfo.canRun ? t('init.value.normal') : t('init.value.abnormal') }}
            </a-tag>
            <a-tag v-if="checkInfo.version" color="blue">
              {{ t('init.check.version') }}: {{ checkInfo.version }}
            </a-tag>
          </div>
        </div>

        <!-- 仓库检查信息 -->
        <div
          v-if="checkInfo && (checkInfo.exists !== undefined || checkInfo.isGitRepo !== undefined)"
          class="info-section"
        >
          <div class="info-title">{{ t('init.check.repoTitle') }}</div>
          <div class="info-items">
            <a-tag
              v-if="checkInfo.exists !== undefined"
              :color="checkInfo.exists ? 'green' : 'orange'"
            >
              {{ t('init.check.localRepo') }}:
              {{ checkInfo.exists ? t('init.value.exists') : t('init.value.notExists') }}
            </a-tag>
            <a-tag
              v-if="checkInfo.isGitRepo !== undefined"
              :color="checkInfo.isGitRepo ? 'green' : 'orange'"
            >
              {{ t('init.check.gitRepo') }}:
              {{ checkInfo.isGitRepo ? t('init.value.yes') : t('init.value.no') }}
            </a-tag>
            <a-tag
              v-if="checkInfo.isHealthy !== undefined"
              :color="checkInfo.isHealthy ? 'green' : 'orange'"
            >
              {{ t('init.check.health') }}:
              {{ checkInfo.isHealthy ? t('init.value.healthy') : t('init.value.abnormal') }}
            </a-tag>
            <a-tag v-if="checkInfo.currentBranch" color="blue">
              {{ t('init.check.branch') }}: {{ checkInfo.currentBranch }}
            </a-tag>
          </div>
        </div>

        <!-- 依赖检查信息 -->
        <div
          v-if="
            checkInfo &&
            (checkInfo.requirementsExists !== undefined || checkInfo.needsInstall !== undefined)
          "
          class="info-section"
        >
          <div class="info-title">{{ t('init.check.depTitle') }}</div>
          <div class="info-items">
            <a-tag
              v-if="checkInfo.requirementsExists !== undefined"
              :color="checkInfo.requirementsExists ? 'green' : 'orange'"
            >
              requirements.txt:
              {{
                checkInfo.requirementsExists ? t('init.value.exists') : t('init.value.notExists')
              }}
            </a-tag>
            <a-tag
              v-if="checkInfo.needsInstall !== undefined"
              :color="checkInfo.needsInstall ? 'orange' : 'green'"
            >
              {{ t('init.check.needsInstall') }}:
              {{ checkInfo.needsInstall ? t('init.value.yes') : t('init.value.no') }}
            </a-tag>
          </div>
        </div>

        <!-- 镜像源信息 -->
        <div v-if="currentMirror || mirrorProgress" class="info-section">
          <div class="info-title">{{ t('init.check.mirrorTitle') }}</div>
          <div class="info-items">
            <a-tag v-if="currentMirror" color="blue">
              {{ t('init.check.currentMirrorTag') }}: {{ currentMirror }}
            </a-tag>
            <a-tag v-if="mirrorProgress" color="purple">
              {{ t('init.check.attemptProgress') }}: {{ mirrorProgress.current }}/{{
                mirrorProgress.total
              }}
            </a-tag>
          </div>
        </div>

        <!-- 下载信息 -->
        <div v-if="downloadSpeed || downloadSize" class="info-section">
          <div class="info-title">{{ t('init.check.downloadTitle') }}</div>
          <div class="info-items">
            <a-tag v-if="downloadSpeed" color="green">
              {{ t('init.check.downloadSpeed') }}: {{ downloadSpeed }}
            </a-tag>
            <a-tag v-if="downloadSize" color="cyan">
              {{ t('init.check.downloaded') }}: {{ downloadSize }}
            </a-tag>
          </div>
        </div>

        <!-- 安装信息 -->
        <div v-if="installMessage" class="info-section">
          <div class="info-title">{{ t('init.check.installTitle') }}</div>
          <div class="info-items">
            <a-tag color="blue">
              {{ installMessage }}
            </a-tag>
            <a-tag v-if="installProgress !== undefined" color="cyan">
              {{ t('init.check.progress') }}: {{ installProgress }}%
            </a-tag>
          </div>
        </div>

        <!-- 部署信息 -->
        <div v-if="deployMessage" class="info-section">
          <div class="info-title">{{ t('init.check.deployTitle') }}</div>
          <div class="info-items">
            <a-tag color="purple">
              {{ deployMessage }}
            </a-tag>
            <a-tag v-if="deployProgress !== undefined" color="magenta">
              {{ t('init.check.progress') }}: {{ deployProgress }}%
            </a-tag>
          </div>
        </div>

        <!-- 操作描述 -->
        <div v-if="operationDesc" class="info-section">
          <div class="operation-desc">{{ operationDesc }}</div>
        </div>
      </div>
    </div>

    <!-- 成功状态 -->
    <div v-else-if="status === 'success'" class="success-state">
      <a-result
        status="success"
        :title="t('init.step.succeeded', { title })"
        :sub-title="message"
      />
    </div>

    <!-- 失败状态 -->
    <div v-else-if="status === 'failed'" class="failed-state">
      <a-alert
        type="error"
        :message="t('init.step.failed', { title })"
        :description="message"
        show-icon
      />

      <!-- 需要额外说清楚的失败：运行时内部错误、需要携带日志反馈 -->
      <a-alert v-if="noticeText" type="warning" :message="noticeText" show-icon />

      <!-- 镜像源选择 -->
      <div v-if="showMirrorSelection" class="mirror-selection">
        <h4>{{ t('init.step.chooseMirrorRetry') }}</h4>

        <!-- 镜像源 -->
        <div v-if="mirrorMirrors.length > 0" class="mirror-section">
          <div class="step-section-header">
            <h4>{{ t('init.env.mirrorSection') }}</h4>
            <a-tag color="green">{{ t('init.env.recommendedUse') }}</a-tag>
          </div>
          <div class="mirror-grid">
            <div
              v-for="mirror in mirrorMirrors"
              :key="mirror.key"
              class="mirror-card"
              :class="{ active: selectedMirror === mirror.key }"
              @click="$emit('update:selected-mirror', mirror.key)"
            >
              <div class="mirror-header">
                <div class="mirror-title">
                  <h4>{{ mirror.name }}</h4>
                  <a-tag v-if="mirror.recommended" color="gold" size="small">{{
                    t('init.env.recommended')
                  }}</a-tag>
                </div>
              </div>
              <div class="mirror-description">{{ mirror.description }}</div>
            </div>
          </div>
        </div>

        <!-- 官方源 -->
        <div v-if="officialMirrors.length > 0" class="mirror-section">
          <div class="step-section-header">
            <h4>{{ t('init.env.officialSection') }}</h4>
            <a-tag color="orange">{{ t('init.env.officialWarning') }}</a-tag>
          </div>
          <div class="mirror-grid">
            <div
              v-for="mirror in officialMirrors"
              :key="mirror.key"
              class="mirror-card"
              :class="{ active: selectedMirror === mirror.key }"
              @click="$emit('update:selected-mirror', mirror.key)"
            >
              <div class="mirror-header">
                <div class="mirror-title">
                  <h4>{{ mirror.name }}</h4>
                </div>
              </div>
              <div class="mirror-description">{{ mirror.description }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 运行诊断结果 -->
      <div v-if="doctorRunning || doctorChecks" class="info-section">
        <div class="info-title">{{ t('init.failure.doctorTitle') }}</div>
        <div v-if="doctorRunning" class="operation-desc">
          {{ t('init.failure.doctorRunning') }}
        </div>
        <div v-else-if="doctorChecks && doctorChecks.length > 0" class="doctor-checks">
          <div v-for="check in doctorChecks" :key="check.id" class="doctor-check">
            <a-tag :color="check.status === 'ok' ? 'green' : 'orange'">{{ check.name }}</a-tag>
            <span class="doctor-check-message">{{ check.message || check.status }}</span>
          </div>
        </div>
        <div v-else class="operation-desc">{{ t('init.failure.doctorEmpty') }}</div>
      </div>

      <!-- 处置动作：顺序与内容全部由 decideFailureActions 决定 -->
      <div class="retry-actions">
        <a-space size="large" wrap>
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
        <div v-if="countdown > 0" class="countdown-text">
          {{ t('init.step.autoRetryIn', { seconds: countdown }) }}
        </div>
      </div>

      <!-- 失败日志整块展示，与后端启动步骤的失败界面一致 -->
      <a-card
        v-if="failureLogs"
        size="small"
        :title="t('init.failure.logTitle')"
        class="failed-log-card"
      >
        <pre class="failure-log-output">{{ failureLogs }}</pre>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import type { MirrorConfig } from '@/types/mirror'
import type { RuntimeDoctorCheck } from '@/types/electron'
import type {
  FailureAction,
  FailureActionKind,
  FailureNoticeKind,
} from '@/utils/initializationDecision'

interface CheckInfo {
  // 环境检查信息（Python/Pip/Git）
  exeExists?: boolean
  canRun?: boolean
  version?: string
  // 仓库检查信息
  exists?: boolean
  isGitRepo?: boolean
  isHealthy?: boolean
  currentBranch?: string
  // 依赖检查信息
  requirementsExists?: boolean
  needsInstall?: boolean
}

interface MirrorProgress {
  current: number
  total: number
}

interface Props {
  title: string
  status: 'waiting' | 'processing' | 'success' | 'failed'
  message: string
  progress?: number
  showProgress?: boolean
  progressStatus?: 'normal' | 'exception' | 'success'
  successTitle?: string
  showMirrorSelection?: boolean
  showSkipButton?: boolean
  mirrors?: MirrorConfig[]
  selectedMirror?: string
  countdown?: number
  currentMirror?: string
  downloadSpeed?: string
  downloadSize?: string
  installMessage?: string
  installProgress?: number
  deployMessage?: string
  deployProgress?: number
  operationDesc?: string
  checkInfo?: CheckInfo
  mirrorProgress?: MirrorProgress
  /** 失败时该给哪些按钮，由 decideFailureActions 算好，本组件只负责渲染。 */
  failureActions?: FailureAction[]
  /** 按钮之外还要说的一句话；不需要时为 null。 */
  failureNotice?: FailureNoticeKind | null
  /** `[stdout]…

[stderr]…` 整块失败日志。 */
  failureLogs?: string
  /** 运行诊断的逐项结果；未诊断过为 null。 */
  doctorChecks?: RuntimeDoctorCheck[] | null
  doctorRunning?: boolean
}

const { t } = useI18n()

const props = withDefaults(defineProps<Props>(), {
  progress: 0,
  showProgress: true,
  progressStatus: 'normal',
  successTitle: '完成',
  showMirrorSelection: false,
  showSkipButton: false,
  mirrors: () => [],
  selectedMirror: '',
  countdown: 0,
  currentMirror: '',
  downloadSpeed: '',
  downloadSize: '',
  installMessage: '',
  installProgress: undefined,
  deployMessage: '',
  deployProgress: undefined,
  operationDesc: '',
  checkInfo: undefined,
  mirrorProgress: undefined,
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

// 词表只能在 setup 里取，模板里按种类查这一句提示。
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

const mirrorMirrors = computed(() => props.mirrors.filter((m: MirrorConfig) => m.type === 'mirror'))
const officialMirrors = computed(() =>
  props.mirrors.filter((m: MirrorConfig) => m.type === 'official')
)
</script>

<style scoped>
.step-panel {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}

.step-panel * {
  box-sizing: border-box;
}

.step-panel h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 20px;
}

.processing-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 20px;
  overflow-y: auto;
  overflow-x: hidden;
  width: 100%;
  min-height: 0;
}

.processing-state :deep(.ant-progress) {
  width: 98%;
  min-width: 200px;
}

.success-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  overflow-y: auto;
  overflow-x: hidden;
  width: 100%;
}

.failed-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  gap: 20px;
  overflow-y: auto;
  overflow-x: hidden;
  width: 100%;
  min-height: 0;
  padding: 8px;
}

.status-text {
  font-size: 16px;
  color: var(--ant-color-text);
  text-align: center;
}

.mirror-selection {
  width: 100%;
  flex-shrink: 0;
}

.mirror-selection h4 {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 20px;
  text-align: center;
}

.mirror-section {
  margin-bottom: 20px;
  flex-shrink: 0;
}

@media (max-height: 700px) {
  .mirror-section {
    margin-bottom: 12px;
  }
}

.step-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.step-section-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.mirror-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  width: 100%;
  box-sizing: border-box;
}

@media (max-height: 700px) {
  .mirror-grid {
    gap: 8px;
  }
}

.mirror-card {
  padding: 16px;
  border: 2px solid var(--ant-color-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--ant-color-bg-container);
}

@media (max-height: 700px) {
  .mirror-card {
    padding: 12px;
  }
}

.mirror-card:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.mirror-card.active {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.mirror-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.mirror-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mirror-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.mirror-description {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  line-height: 1.4;
}

.retry-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin-top: 20px;
}

.doctor-checks {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.doctor-check {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.doctor-check-message {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  word-break: break-word;
}

.failed-log-card {
  width: 100%;
  min-height: 0;
  overflow: hidden;
}

.failed-log-card :deep(.ant-card-body) {
  padding: 0;
}

.failure-log-output {
  margin: 0;
  max-height: 260px;
  width: 100%;
  overflow: auto;
  padding: 12px 16px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.countdown-text {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

.detail-info-container {
  width: 100%;
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-section {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  padding: 12px 16px;
}

.info-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
  margin-bottom: 8px;
}

.info-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.operation-desc {
  font-size: 13px;
  color: var(--ant-color-text);
  line-height: 1.5;
}
</style>
