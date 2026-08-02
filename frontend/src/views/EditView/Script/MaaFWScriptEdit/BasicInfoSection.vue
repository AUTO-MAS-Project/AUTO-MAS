<template>
  <div class="form-section">
    <div class="section-header">
      <h3>基本信息</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item name="name">
          <template #label>
            <a-tooltip title="为项目设置一个易于识别的名称">
              <span class="form-label">
                脚本名称
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.name"
            placeholder="请输入脚本名称"
            size="large"
            class="modern-input"
            @blur="emit('change', 'Info', 'Name', formData.name)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="16">
        <a-form-item name="path" :rules="rules.path">
          <template #label>
            <a-tooltip
              :title="
                isManagedProject
                  ? '托管项目目录由 MAS 的不可变 Project Store 维护'
                  : '选择包含 interface.json 的 MaaFramework 项目目录'
              "
            >
              <span class="form-label">
                项目目录
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input-group compact class="path-input-group">
            <a-input
              v-model:value="formData.path"
              placeholder="请选择 MaaFramework 项目目录"
              size="large"
              class="path-input"
              readonly
              aria-readonly="true"
            />
            <a-button
              size="large"
              class="path-button"
              :disabled="
                isManagedProject ||
                interfaceLoading ||
                isAgentEnvPreparing ||
                isProjectUpdateRunning
              "
              @click="emit('select-path')"
            >
              <template #icon>
                <FolderOpenOutlined />
              </template>
              {{ isManagedProject ? '由 MAS 托管' : '选择文件夹' }}
            </a-button>
          </a-input-group>
          <div v-if="!isSetupMode" class="path-secondary-actions">
            <a-button
              size="middle"
              class="path-button"
              :loading="interfaceLoading"
              :disabled="!maafwConfig.Info.Path || isAgentEnvPreparing || isProjectUpdateRunning"
              @click="emit('preview-interface')"
            >
              <template #icon>
                <FileSearchOutlined />
              </template>
              读取 interface
            </a-button>
            <a-button
              size="middle"
              class="path-button"
              :loading="agentEnvLoading"
              :disabled="
                !maafwConfig.Info.Path ||
                interfaceLoading ||
                isAgentEnvPreparing ||
                isProjectUpdateRunning
              "
              @click="emit('prepare-agent-env')"
            >
              <template #icon>
                <ToolOutlined />
              </template>
              准备运行环境
            </a-button>
          </div>
        </a-form-item>
      </a-col>
    </a-row>

    <div v-if="isSetupMode && maafwConfig.Info.Path" class="setup-checklist">
      <div class="setup-check-item">
        <span class="setup-check-status">
          <LoadingOutlined v-if="interfaceLoading" spin class="setup-icon-pending" />
          <CheckCircleOutlined v-else-if="isInterfaceReady" class="setup-icon-done" />
          <ExclamationCircleOutlined v-else class="setup-icon-todo" />
        </span>
        <div class="setup-check-copy">
          <div class="setup-check-title">第 1 步 · 读取 interface</div>
          <div class="setup-check-desc">
            {{
              isInterfaceReady
                ? `已读取 ${previewProjectTitle}，共 ${previewData?.tasks.length ?? 0} 个任务`
                : '解析项目声明的任务、控制器和资源，是后续所有配置的基础'
            }}
          </div>
        </div>
        <a-button
          :type="isInterfaceReady ? 'default' : 'primary'"
          size="large"
          :loading="interfaceLoading"
          :disabled="!maafwConfig.Info.Path || isAgentEnvPreparing || isProjectUpdateRunning"
          @click="emit('preview-interface')"
        >
          {{ isInterfaceReady ? '重新读取' : '读取 interface' }}
        </a-button>
      </div>
      <div class="setup-check-item">
        <span class="setup-check-status">
          <LoadingOutlined v-if="agentEnvLoading" spin class="setup-icon-pending" />
          <CheckCircleOutlined v-else-if="isAgentEnvReady" class="setup-icon-done" />
          <CloseCircleOutlined v-else-if="isAgentEnvFailed" class="setup-icon-error" />
          <ExclamationCircleOutlined v-else class="setup-icon-todo" />
        </span>
        <div class="setup-check-copy">
          <div class="setup-check-title">第 2 步 · 准备运行环境</div>
          <div class="setup-check-desc">{{ agentEnvChecklistDescription }}</div>
        </div>
        <a-button
          :type="isAgentEnvReady ? 'default' : 'primary'"
          size="large"
          :loading="agentEnvLoading"
          :disabled="
            !maafwConfig.Info.Path ||
            interfaceLoading ||
            isAgentEnvPreparing ||
            isProjectUpdateRunning
          "
          @click="emit('prepare-agent-env')"
        >
          {{ isAgentEnvReady ? '重新准备' : isAgentEnvFailed ? '重试准备' : '准备运行环境' }}
        </a-button>
      </div>
    </div>

    <div v-if="previewData" class="interface-summary">
      <div class="interface-project-bar">
        <span class="project-bar-name">{{ previewProjectTitle }}</span>
        <span v-if="previewData.project.version" class="project-bar-meta">
          {{ previewData.project.version }}
          <template v-if="previewData.project?.description">
            · {{ previewData.project.description }}
          </template>
        </span>
      </div>
      <div class="interface-stat-grid">
        <div v-for="item in interfaceStats" :key="item.label" class="interface-stat-card">
          <div class="interface-stat-value">{{ item.value }}</div>
          <div class="interface-stat-label">{{ item.label }}</div>
        </div>
      </div>
    </div>
    <div v-else-if="interfaceLoading" class="interface-loading">
      <a-spin tip="正在读取 interface.json…">
        <a-alert
          type="info"
          show-icon
          message="正在加载 MaaFW 项目接口"
          description="请稍候，正在解析 interface.json 中的控制器、资源、任务和选项定义"
        />
      </a-spin>
    </div>
    <div v-else class="interface-guide-card">
      <InboxOutlined class="interface-guide-icon" aria-hidden="true" />
      <h3>开始配置 MaaFW 项目</h3>
      <p>选择一个包含 interface.json 的项目目录，系统将自动解析可用的控制器、资源、任务和选项。</p>
      <a-button
        type="primary"
        size="large"
        :disabled="interfaceLoading || isAgentEnvPreparing || isProjectUpdateRunning"
        @click="emit('select-path')"
      >
        <template #icon>
          <FolderOpenOutlined />
        </template>
        选择项目目录
      </a-button>
      <a href="#" class="interface-guide-link" @click.prevent>如何获取 interface.json</a>
    </div>

    <div
      v-if="isAgentEnvPreparing || agentEnvProgressStatus !== 'idle' || agentEnvResult"
      class="agent-env-panel"
    >
      <div class="agent-env-progress" :class="`agent-env-progress-${agentEnvProgressStatus}`">
        <div class="agent-env-progress-header">
          <span>{{ agentEnvProgressStage || '正在准备 MaaFW 运行环境' }}</span>
          <span v-if="agentEnvDisplayPercent !== null">{{ agentEnvDisplayPercent }}%</span>
        </div>
        <a-progress
          v-if="agentEnvDisplayPercent !== null"
          :percent="agentEnvDisplayPercent"
          :status="agentEnvAntProgressStatus"
          :show-info="false"
          :stroke-width="8"
        />
        <div
          v-else-if="isAgentEnvPreparing"
          class="agent-env-indeterminate-track"
          aria-label="环境准备进行中，暂时没有可用的进度百分比"
        >
          <span />
        </div>
        <div v-else-if="agentEnvProgressStatus === 'failed'" class="agent-env-failure-track" />
        <div v-if="agentEnvProgressMessage" class="agent-env-progress-message">
          {{ agentEnvProgressMessage }}
        </div>
        <div v-if="agentEnvDownloadSummary" class="agent-env-progress-message">
          {{ agentEnvDownloadSummary }}
        </div>
      </div>
      <a-alert
        v-if="agentEnvProgressStatus === 'failed'"
        type="error"
        show-icon
        :message="agentEnvProgressStage || 'MaaFW 运行环境准备失败'"
        :description="agentEnvProgressMessage || '请查看准备日志后重试'"
      />
      <a-alert
        v-else-if="isAgentEnvPreparing"
        type="info"
        show-icon
        message="正在准备 MaaFW 运行环境"
        description="将预热 AUTO-MAS Runner 隔离 venv，并检查或准备项目 Agent Python 环境。"
      />
      <div
        v-if="agentEnvProgressLogs.length && (isAgentEnvPreparing || !agentEnvResult?.logs.length)"
        class="agent-env-log-box"
      >
        <div class="agent-env-log-header">
          <span>实时准备日志</span>
          <a-button size="small" @click="emit('copy', agentEnvProgressLogs.join('\n'))">
            <template #icon><CopyOutlined /></template>
            复制日志
          </a-button>
        </div>
        <pre>{{ agentEnvProgressLogs.join('\n') }}</pre>
      </div>
      <template v-if="!isAgentEnvPreparing && agentEnvResult">
        <a-alert
          :type="agentEnvAlertType"
          show-icon
          :message="agentEnvSummary"
          :description="agentEnvDescription"
        />
        <a-collapse
          v-if="agentEnvResult.agents.length"
          class="agent-env-collapse"
          :default-active-key="agentEnvResult.agents.map((_, index) => String(index))"
        >
          <a-collapse-panel v-for="(agent, index) in agentEnvResult.agents" :key="String(index)">
            <template #header>
              <div class="agent-env-agent-header">
                <span class="agent-env-agent-title">{{ agent.childExec }}</span>
                <a-tag :color="getAgentRuntimeColor(agent.runtimeKind)">
                  {{ getAgentRuntimeLabel(agent.runtimeKind) }}
                </a-tag>
              </div>
            </template>
            <a-descriptions size="small" :column="1">
              <a-descriptions-item label="解释器">
                <span class="copyable-code">
                  <code>{{ agent.executable }}</code>
                  <a-button
                    type="text"
                    size="small"
                    aria-label="复制解释器路径"
                    @click="emit('copy', agent.executable)"
                  >
                    <template #icon><CopyOutlined /></template>
                  </a-button>
                </span>
              </a-descriptions-item>
              <a-descriptions-item v-if="agent.isolatedVenvPath" label="隔离 venv">
                <span class="copyable-code">
                  <code>{{ agent.isolatedVenvPath }}</code>
                  <a-button
                    type="text"
                    size="small"
                    aria-label="复制隔离 venv 路径"
                    @click="emit('copy', agent.isolatedVenvPath || '')"
                  >
                    <template #icon><CopyOutlined /></template>
                  </a-button>
                </span>
              </a-descriptions-item>
              <a-descriptions-item v-if="agent.fallbackReason" label="准备说明">
                {{ agent.fallbackReason }}
              </a-descriptions-item>
            </a-descriptions>
          </a-collapse-panel>
        </a-collapse>
        <a-empty v-else description="当前项目没有声明 Agent" />
        <div v-if="agentEnvResult.logs.length" class="agent-env-log-box">
          <div class="agent-env-log-header">
            <span>准备日志</span>
            <a-button size="small" @click="emit('copy', agentEnvResult.logs.join('\n'))">
              <template #icon><CopyOutlined /></template>
              复制日志
            </a-button>
          </div>
          <pre>{{ agentEnvResult.logs.join('\n') }}</pre>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  LoadingOutlined,
  QuestionCircleOutlined,
  ToolOutlined,
} from '@ant-design/icons-vue'
import { getAgentRuntimeColor, getAgentRuntimeLabel } from '@/composables/useMaaFWScriptConfig'
import type { MaaFWAgentEnvProgressStatus } from '@/composables/useMaaFWScriptConfig'
import type {
  MaaFWAgentEnvPrepareData,
  MaaFWInterfacePreviewData,
  MaaFWScriptConfig,
  ScriptType,
} from '@/types/script'

const props = defineProps<{
  maafwConfig: MaaFWScriptConfig
  formData: { type: ScriptType; name: string; path: string }
  rules: { name: unknown[]; path: unknown[] }
  previewData: MaaFWInterfacePreviewData | null
  agentEnvResult: MaaFWAgentEnvPrepareData | null
  agentEnvProgressStatus: MaaFWAgentEnvProgressStatus
  agentEnvProgressStage: string
  agentEnvProgressPercent: number | null
  agentEnvProgressMessage: string
  agentEnvProgressLogs: string[]
  agentEnvProgressDownloadedBytes: number | null
  agentEnvProgressTotalBytes: number | null
  interfaceLoading: boolean
  agentEnvLoading: boolean
  isAgentEnvPreparing: boolean
  isProjectUpdateRunning: boolean
  isSetupMode: boolean
  isManagedProject?: boolean
  previewProjectTitle: string
  interfaceStats: Array<{ label: string; value: number }>
  isInterfaceReady: boolean
  isAgentEnvReady: boolean
  isAgentEnvFailed: boolean
  agentEnvAlertType: 'error' | 'info' | 'success'
  agentEnvSummary: string
  agentEnvDescription: string
  agentEnvChecklistDescription: string
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
  'select-path': []
  'preview-interface': []
  'prepare-agent-env': []
  copy: [text: string]
}>()

const agentEnvDisplayPercent = computed(() => {
  if (props.agentEnvProgressPercent === null) return null
  return Math.round(Math.min(Math.max(props.agentEnvProgressPercent, 0), 100))
})

const agentEnvAntProgressStatus = computed<'active' | 'success' | 'exception'>(() => {
  if (props.agentEnvProgressStatus === 'completed') return 'success'
  if (props.agentEnvProgressStatus === 'failed') return 'exception'
  return 'active'
})

const formatBytes = (bytes: number) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const base = 1024
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(base)), units.length - 1)
  return `${Number((bytes / Math.pow(base, unitIndex)).toFixed(2))} ${units[unitIndex]}`
}

const agentEnvDownloadSummary = computed(() => {
  if (props.agentEnvProgressDownloadedBytes === null) return ''
  const downloaded = formatBytes(props.agentEnvProgressDownloadedBytes)
  if (props.agentEnvProgressTotalBytes !== null && props.agentEnvProgressTotalBytes > 0) {
    return `${downloaded} / ${formatBytes(props.agentEnvProgressTotalBytes)}`
  }
  return `已下载 ${downloaded}`
})
</script>

<style scoped>
.form-section {
  margin-bottom: 40px;
}

.section-header {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 20px;
  background: var(--ant-color-text-quaternary);
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.modern-input {
  border-radius: 8px;
}

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
}

.path-input:focus {
  box-shadow: none !important;
}

.path-button {
  border: none;
  border-left: 1px solid var(--ant-color-border-secondary);
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
}

.path-secondary-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.path-secondary-actions .path-button {
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font-weight: 500;
}

.setup-checklist {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.setup-check-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.setup-check-status {
  display: inline-flex;
  flex: 0 0 auto;
  font-size: 22px;
}

.setup-icon-done {
  color: var(--ant-color-success);
}

.setup-icon-error {
  color: var(--ant-color-error);
}

.setup-icon-pending {
  color: var(--ant-color-primary);
}

.setup-icon-todo {
  color: var(--ant-color-text-quaternary);
}

.setup-check-copy {
  flex: 1;
  min-width: 0;
}

.setup-check-title {
  color: var(--ant-color-text);
  font-weight: 600;
}

.setup-check-desc {
  margin-top: 2px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.interface-summary {
  margin-top: 8px;
}

.interface-project-bar {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 12px;
  border-radius: 8px;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
}

.project-bar-name {
  max-width: 300px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 16px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.project-bar-meta {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
}

.interface-stat-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
}

.interface-stat-card {
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.interface-stat-value {
  color: var(--ant-color-text);
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.interface-stat-label {
  margin-top: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.interface-guide-card {
  display: flex;
  max-width: 480px;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin: 8px auto 0;
  padding: 28px 24px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  text-align: center;
}

.interface-guide-card h3 {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 18px;
}

.interface-guide-card p {
  max-width: 380px;
  margin: 0;
  color: var(--ant-color-text-secondary);
  line-height: 1.6;
}

.interface-guide-icon {
  color: var(--ant-color-primary);
  font-size: 64px;
}

.interface-guide-link {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.interface-loading {
  margin-top: 8px;
  padding: 16px;
}

.interface-loading :deep(.ant-spin-container) {
  opacity: 1;
}

.agent-env-panel {
  margin-top: 16px;
}

.agent-env-progress {
  margin-bottom: 12px;
  padding: 12px 14px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.agent-env-progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
}

.agent-env-progress-completed .agent-env-progress-header {
  color: var(--ant-color-success);
}

.agent-env-progress-failed .agent-env-progress-header,
.agent-env-progress-failed .agent-env-progress-message {
  color: var(--ant-color-error);
}

.agent-env-progress-message {
  margin-top: 5px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.agent-env-indeterminate-track,
.agent-env-failure-track {
  position: relative;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--ant-color-fill-secondary);
}

.agent-env-indeterminate-track span {
  position: absolute;
  inset-block: 0;
  width: 38%;
  border-radius: inherit;
  background: var(--ant-color-primary);
  animation: agent-env-indeterminate 1.2s ease-in-out infinite;
}

.agent-env-failure-track {
  border: 1px solid var(--ant-color-error-border);
  background: var(--ant-color-error-bg);
}

@keyframes agent-env-indeterminate {
  from {
    transform: translateX(-110%);
  }
  to {
    transform: translateX(280%);
  }
}

.agent-env-collapse {
  margin-top: 12px;
}

.agent-env-agent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.agent-env-agent-title {
  min-width: 0;
  color: var(--ant-color-text);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.copyable-code {
  display: inline-flex;
  max-width: 100%;
  gap: 8px;
  align-items: center;
}

.copyable-code code {
  min-width: 0;
  color: var(--ant-color-text);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.agent-env-log-box {
  max-height: 220px;
  margin-top: 12px;
  padding: 10px 12px;
  overflow: auto;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  font-family: var(--font-mono, Consolas, 'Courier New', monospace);
  font-size: 12px;
  line-height: 1.6;
}

.agent-env-log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: var(--ant-color-text);
  font-family: var(--font-family, inherit);
  font-size: 13px;
  font-weight: 600;
}

.agent-env-log-box pre {
  margin: 0;
  color: var(--ant-color-text-secondary);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 768px) {
  .setup-check-item {
    flex-direction: column;
    align-items: stretch;
    text-align: center;
  }

  .path-secondary-actions {
    flex-direction: column;
  }

  .path-secondary-actions .ant-btn {
    width: 100%;
  }

  .interface-stat-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
