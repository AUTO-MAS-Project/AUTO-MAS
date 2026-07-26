<template>
  <div class="step-panel">
    <!-- 进行中状态 -->
    <div
      v-if="status === 'processing' || status === 'running' || status === 'retry'"
      class="processing-state"
    >
      <div class="status-text">
        <a-tag v-if="status === 'retry'" color="orange" class="status-tag">重试中</a-tag>
        <a-tag v-else color="processing" class="status-tag">运行中</a-tag>
        <span class="status-message">{{ message }}</span>
      </div>
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
          <div class="info-title">环境检查</div>
          <div class="info-items">
            <a-tag
              v-if="checkInfo.exeExists !== undefined"
              :color="checkInfo.exeExists ? 'green' : 'orange'"
            >
              可执行文件: {{ checkInfo.exeExists ? '存在' : '不存在' }}
            </a-tag>
            <a-tag
              v-if="checkInfo.canRun !== undefined"
              :color="checkInfo.canRun ? 'green' : 'orange'"
            >
              运行状态: {{ checkInfo.canRun ? '正常' : '异常' }}
            </a-tag>
            <a-tag v-if="checkInfo.version" color="blue"> 版本: {{ checkInfo.version }} </a-tag>
          </div>
        </div>

        <!-- 仓库检查信息 -->
        <div
          v-if="checkInfo && (checkInfo.exists !== undefined || checkInfo.isGitRepo !== undefined)"
          class="info-section"
        >
          <div class="info-title">仓库检查</div>
          <div class="info-items">
            <a-tag
              v-if="checkInfo.exists !== undefined"
              :color="checkInfo.exists ? 'green' : 'orange'"
            >
              本地仓库: {{ checkInfo.exists ? '存在' : '不存在' }}
            </a-tag>
            <a-tag
              v-if="checkInfo.isGitRepo !== undefined"
              :color="checkInfo.isGitRepo ? 'green' : 'orange'"
            >
              Git仓库: {{ checkInfo.isGitRepo ? '是' : '否' }}
            </a-tag>
            <a-tag
              v-if="checkInfo.isHealthy !== undefined"
              :color="checkInfo.isHealthy ? 'green' : 'orange'"
            >
              健康状态: {{ checkInfo.isHealthy ? '健康' : '异常' }}
            </a-tag>
            <a-tag v-if="checkInfo.currentBranch" color="blue">
              当前分支: {{ checkInfo.currentBranch }}
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
          <div class="info-title">依赖检查</div>
          <div class="info-items">
            <a-tag
              v-if="checkInfo.requirementsExists !== undefined"
              :color="checkInfo.requirementsExists ? 'green' : 'orange'"
            >
              requirements.txt: {{ checkInfo.requirementsExists ? '存在' : '不存在' }}
            </a-tag>
            <a-tag
              v-if="checkInfo.needsInstall !== undefined"
              :color="checkInfo.needsInstall ? 'orange' : 'green'"
            >
              需要安装: {{ checkInfo.needsInstall ? '是' : '否' }}
            </a-tag>
          </div>
        </div>

        <!-- 镜像源信息 -->
        <div v-if="currentMirror || mirrorProgress" class="info-section">
          <div class="info-title">镜像源信息</div>
          <div class="info-items">
            <a-tag v-if="currentMirror" color="blue"> 当前镜像源: {{ currentMirror }} </a-tag>
            <a-tag v-if="mirrorProgress" color="purple">
              尝试进度: {{ mirrorProgress.current }}/{{ mirrorProgress.total }}
            </a-tag>
          </div>
        </div>

        <!-- 下载信息 -->
        <div v-if="downloadSpeed || downloadSize" class="info-section">
          <div class="info-title">下载信息</div>
          <div class="info-items">
            <a-tag v-if="downloadSpeed" color="green"> 下载速度: {{ downloadSpeed }} </a-tag>
            <a-tag v-if="downloadSize" color="cyan"> 已下载: {{ downloadSize }} </a-tag>
          </div>
        </div>

        <!-- 安装信息 -->
        <div v-if="installMessage" class="info-section">
          <div class="info-title">安装进度</div>
          <div class="info-items">
            <a-tag color="blue">
              {{ installMessage }}
            </a-tag>
            <a-tag v-if="installProgress !== undefined" color="cyan">
              进度: {{ installProgress }}%
            </a-tag>
          </div>
        </div>

        <!-- 部署信息 -->
        <div v-if="deployMessage" class="info-section">
          <div class="info-title">部署进度</div>
          <div class="info-items">
            <a-tag color="purple">
              {{ deployMessage }}
            </a-tag>
            <a-tag v-if="deployProgress !== undefined" color="magenta">
              进度: {{ deployProgress }}%
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
      <a-result status="success" :title="`${title}完成`" :sub-title="message" />

      <!-- Lane 8：成功但携带非致命警告时仍需展示版本锁冲突 -->
      <div v-if="hasPluginConflicts" class="plugin-conflicts-success">
        <a-alert
          type="warning"
          message="插件版本锁冲突（非致命，但需要关注）"
          show-icon
          style="margin-bottom: 12px"
        />
        <div class="plugin-conflicts-list">
          <div
            v-for="(conflict, idx) in pluginVersionConflicts"
            :key="`pc-${idx}-${conflict.distribution}`"
            class="plugin-conflict-card"
          >
            <div class="plugin-conflict-header">
              <a-tag :color="conflictKindColor(conflict.kind)">
                {{ conflictKindLabel(conflict.kind) }}
              </a-tag>
              <span class="plugin-conflict-distribution">{{ conflict.distribution }}</span>
            </div>
            <div class="plugin-conflict-grid">
              <div class="plugin-conflict-row">
                <span class="detail-label">锁定版本：</span>
                <span class="detail-value">
                  {{ conflict.locked || '未提供（参考 plugins/wheels/runtime-lock.json）' }}
                </span>
              </div>
              <div class="plugin-conflict-row">
                <span class="detail-label">请求版本：</span>
                <span class="detail-value">{{ conflict.requested || '未指定' }}</span>
              </div>
              <div class="plugin-conflict-row">
                <span class="detail-label">已安装版本：</span>
                <span class="detail-value">{{ conflict.installed || '未知' }}</span>
              </div>
            </div>
            <div class="plugin-conflict-suggestion">{{ conflict.suggestion }}</div>
            <details class="failure-raw-details">
              <summary>原始后端消息</summary>
              <pre class="failure-raw-text">{{ conflict.rawMessage }}</pre>
            </details>
          </div>
        </div>
      </div>
    </div>

    <!-- 跳过状态 -->
    <div v-else-if="status === 'skipped'" class="skipped-state">
      <a-result
        status="info"
        :title="`${title}已跳过`"
        :sub-title="message || '用户主动跳过此步骤，可能影响后续功能'"
      >
        <template #extra>
          <a-button type="primary" @click="$emit('retry')">重新执行此步骤</a-button>
        </template>
      </a-result>
    </div>

    <!-- 失败状态 - 显示镜像源选择 -->
    <div
      v-else-if="(status === 'failed' || status === 'failure') && showMirrorSelection"
      class="failed-state"
    >
      <a-alert
        type="error"
        :message="`${title}失败`"
        :description="failureDetails?.reason || message"
        show-icon
        style="margin-bottom: 16px"
      />

      <!-- 具体失败诊断（Lane 8 要求：不得只给"请选择镜像源"） -->
      <div v-if="failureDetails" class="failure-details">
        <div class="failure-details-header">失败诊断</div>
        <div class="failure-details-grid">
          <div class="failure-detail-row">
            <span class="detail-label">错误阶段：</span>
            <a-tag :color="stageColor(failureDetails.stage)">{{
              stageLabel(failureDetails.stage)
            }}</a-tag>
          </div>
          <div v-if="failureDetails.mirrorTried" class="failure-detail-row">
            <span class="detail-label">最后尝试镜像源：</span>
            <span class="detail-value">{{ failureDetails.mirrorTried }}</span>
          </div>
          <div v-if="failureDetails.mirrorProgress" class="failure-detail-row">
            <span class="detail-label">镜像源尝试进度：</span>
            <span class="detail-value">
              {{ failureDetails.mirrorProgress.current }} /
              {{ failureDetails.mirrorProgress.total }}
            </span>
          </div>
          <div class="failure-detail-row">
            <span class="detail-label">已重试次数：</span>
            <span class="detail-value">{{ failureDetails.retryCount }}</span>
          </div>
          <div class="failure-detail-row">
            <span class="detail-label">最后失败时间：</span>
            <span class="detail-value">{{ formatFailureTime(failureDetails.lastAttemptAt) }}</span>
          </div>
        </div>
        <a-alert
          type="warning"
          message="可执行建议"
          :description="failureDetails.suggestion"
          show-icon
          style="margin-top: 12px"
        />
        <details class="failure-raw-details">
          <summary>查看完整错误信息</summary>
          <pre class="failure-raw-text">{{ failureDetails.reason }}</pre>
        </details>
      </div>

      <!-- Lane 8：插件版本锁冲突展示（失败状态下） -->
      <div v-if="hasPluginConflicts" class="plugin-conflicts-failed">
        <div class="plugin-conflicts-header">插件版本锁冲突</div>
        <div class="plugin-conflicts-list">
          <div
            v-for="(conflict, idx) in pluginVersionConflicts"
            :key="`pc-fail-${idx}-${conflict.distribution}`"
            class="plugin-conflict-card"
          >
            <div class="plugin-conflict-header">
              <a-tag :color="conflictKindColor(conflict.kind)">
                {{ conflictKindLabel(conflict.kind) }}
              </a-tag>
              <span class="plugin-conflict-distribution">{{ conflict.distribution }}</span>
            </div>
            <div class="plugin-conflict-grid">
              <div class="plugin-conflict-row">
                <span class="detail-label">分发包：</span>
                <span class="detail-value">{{ conflict.distribution }}</span>
              </div>
              <div class="plugin-conflict-row">
                <span class="detail-label">锁定版本：</span>
                <span class="detail-value">
                  {{ conflict.locked || '未提供（参考 plugins/wheels/runtime-lock.json）' }}
                </span>
              </div>
              <div class="plugin-conflict-row">
                <span class="detail-label">请求版本：</span>
                <span class="detail-value">{{ conflict.requested || '未指定' }}</span>
              </div>
              <div class="plugin-conflict-row">
                <span class="detail-label">已安装版本：</span>
                <span class="detail-value">{{ conflict.installed || '未知' }}</span>
              </div>
            </div>
            <a-alert
              type="warning"
              message="可执行建议"
              :description="conflict.suggestion"
              show-icon
              style="margin-top: 8px"
            />
            <details class="failure-raw-details">
              <summary>原始后端消息</summary>
              <pre class="failure-raw-text">{{ conflict.rawMessage }}</pre>
            </details>
          </div>
        </div>
      </div>

      <!-- 镜像源选择 -->
      <div class="mirror-selection">
        <h4>请选择镜像源重试</h4>

        <!-- 镜像源 -->
        <div v-if="mirrorMirrors.length > 0" class="mirror-section">
          <div class="section-header">
            <h4>镜像源</h4>
            <a-tag color="green">推荐使用</a-tag>
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
                  <a-tag v-if="mirror.recommended" color="gold" size="small">推荐</a-tag>
                </div>
              </div>
              <div class="mirror-description">{{ mirror.description }}</div>
            </div>
          </div>
        </div>

        <!-- 官方源 -->
        <div v-if="officialMirrors.length > 0" class="mirror-section">
          <div class="section-header">
            <h4>官方源</h4>
            <a-tag color="orange">中国大陆连通性不佳</a-tag>
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

        <div class="retry-actions">
          <a-space size="large">
            <a-button v-if="showSkipButton" size="large" @click="$emit('skip')">
              跳过此步骤
            </a-button>
            <a-button type="primary" size="large" @click="$emit('retry')">
              使用选中的镜像源重试
            </a-button>
          </a-space>
          <div v-if="countdown > 0" class="countdown-text">{{ countdown }} 秒后自动重试</div>
        </div>
      </div>
    </div>

    <!-- 简单失败状态 -->
    <div v-else-if="status === 'failed' || status === 'failure'" class="simple-failed-state">
      <a-result
        status="error"
        :title="`${title}失败`"
        :sub-title="failureDetails?.reason || message"
      >
        <template #extra>
          <a-space>
            <a-button v-if="showSkipButton" @click="$emit('skip')">跳过此步骤</a-button>
            <a-button type="primary" @click="$emit('retry')">重试</a-button>
          </a-space>
        </template>
      </a-result>
      <div v-if="failureDetails" class="failure-details">
        <a-alert
          type="warning"
          message="可执行建议"
          :description="failureDetails.suggestion"
          show-icon
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MirrorConfig } from '@/types/mirror'
import type {
  InitStepFailureDetails,
  InitStepCheckInfo,
  PluginVersionConflict,
} from '@/composables/useInitializationStateMachine'

interface MirrorProgress {
  current: number
  total: number
}

interface Props {
  title: string
  // 接受新旧两套状态名：processing/failed（旧）和 running/failure/skipped/retry（新）
  status:
    | 'waiting'
    | 'processing'
    | 'running'
    | 'success'
    | 'failed'
    | 'failure'
    | 'skipped'
    | 'retry'
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
  checkInfo?: InitStepCheckInfo
  mirrorProgress?: MirrorProgress
  /** Lane 8：结构化失败诊断 */
  failureDetails?: InitStepFailureDetails
  /** Lane 8：插件版本锁冲突结构化展示 */
  pluginVersionConflicts?: PluginVersionConflict[]
}

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
  failureDetails: undefined,
  pluginVersionConflicts: undefined,
})

defineEmits<{
  'update:selected-mirror': [value: string]
  retry: []
  skip: []
}>()

const mirrorMirrors = computed(() => props.mirrors.filter((m: MirrorConfig) => m.type === 'mirror'))
const officialMirrors = computed(() =>
  props.mirrors.filter((m: MirrorConfig) => m.type === 'official')
)

const hasPluginConflicts = computed(
  () => Array.isArray(props.pluginVersionConflicts) && props.pluginVersionConflicts.length > 0
)

const conflictKindLabel = (kind: string): string => {
  const labels: Record<string, string> = {
    'version-mismatch': '版本不匹配',
    'install-failed': '安装失败',
    'missing-entry-point': '缺少入口点',
  }
  return labels[kind] || kind
}

const conflictKindColor = (kind: string): string => {
  const colors: Record<string, string> = {
    'version-mismatch': 'red',
    'install-failed': 'volcano',
    'missing-entry-point': 'orange',
  }
  return colors[kind] || 'default'
}

const stageLabel = (stage: string): string => {
  const labels: Record<string, string> = {
    download: '下载',
    install: '安装',
    deploy: '部署',
    check: '检查',
    network: '网络',
    unknown: '未知',
  }
  return labels[stage] || stage
}

const stageColor = (stage: string): string => {
  const colors: Record<string, string> = {
    download: 'blue',
    install: 'cyan',
    deploy: 'purple',
    check: 'geekblue',
    network: 'orange',
    unknown: 'default',
  }
  return colors[stage] || 'default'
}

const formatFailureTime = (iso: string): string => {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}
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

.simple-failed-state {
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

.skipped-state {
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

.status-text {
  font-size: 16px;
  color: var(--ant-color-text);
  text-align: center;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
}

.status-tag {
  margin: 0;
  flex-shrink: 0;
}

.status-message {
  flex: 1;
  min-width: 0;
}

.failure-details {
  background: var(--ant-color-error-bg);
  border: 1px solid var(--ant-color-error-border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  width: 100%;
  box-sizing: border-box;
}

.failure-details-header {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-error);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.failure-details-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.failure-detail-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  flex-wrap: wrap;
}

.detail-label {
  color: var(--ant-color-text-secondary);
  font-weight: 500;
  flex-shrink: 0;
}

.detail-value {
  color: var(--ant-color-text);
  word-break: break-all;
}

.failure-raw-details {
  margin-top: 12px;
  border-top: 1px dashed var(--ant-color-border-secondary);
  padding-top: 8px;
}

.failure-raw-details summary {
  cursor: pointer;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  user-select: none;
}

.failure-raw-details summary:hover {
  color: var(--ant-color-primary);
}

.failure-raw-text {
  margin: 8px 0 0;
  padding: 12px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 4px;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow: auto;
  color: var(--ant-color-text);
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

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.section-header h4 {
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

/* Lane 8：插件版本锁冲突展示 */
.plugin-conflicts-success {
  width: 100%;
  margin-top: 16px;
  text-align: left;
}

.plugin-conflicts-failed {
  width: 100%;
  margin-top: 8px;
  margin-bottom: 16px;
  background: var(--ant-color-warning-bg);
  border: 1px solid var(--ant-color-warning-border);
  border-radius: 8px;
  padding: 16px;
  box-sizing: border-box;
}

.plugin-conflicts-header {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-warning);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.plugin-conflicts-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plugin-conflict-card {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  padding: 12px 14px;
}

.plugin-conflict-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.plugin-conflict-distribution {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
  word-break: break-all;
}

.plugin-conflict-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

.plugin-conflict-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  flex-wrap: wrap;
}

.plugin-conflict-suggestion {
  font-size: 13px;
  color: var(--ant-color-text);
  line-height: 1.5;
  margin-top: 8px;
  padding: 8px 10px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 4px;
}
</style>
