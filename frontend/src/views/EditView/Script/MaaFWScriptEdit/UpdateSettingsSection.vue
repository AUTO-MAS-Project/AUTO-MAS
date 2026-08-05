<template>
  <div class="form-section">
    <div class="section-header">
      <h3>项目更新</h3>
    </div>
    <a-alert
      v-if="isAutoUpdateDisabled"
      class="update-alert"
      type="warning"
      show-icon
      message="当前脚本未声明版本，无法判断更新"
    />
    <a-row v-if="!isManagedProject" :gutter="24" class="update-config-row">
      <a-col :span="8">
        <a-form-item label="更新源">
          <a-select
            v-model:value="maafwConfig.Update.Source"
            size="large"
            :options="updateSourceOptions"
            @change="(value: string | number) => emit('change', 'Update', 'Source', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item label="渠道">
          <a-select
            v-model:value="maafwConfig.Update.Channel"
            size="large"
            :options="updateChannelOptions"
            @change="(value: string | number) => emit('change', 'Update', 'Channel', value)"
          />
        </a-form-item>
      </a-col>
      <a-col v-if="maafwConfig.Update.Source !== 'GitHub'" :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip
              title="填写后优先使用脚本自己的 Mirror 酱 CDK；留空时使用 MAS 全局更新配置中的 CDK"
            >
              <span class="form-label">
                Mirror 酱 CDK
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input-password
            v-model:value="maafwConfig.Update.MirrorChyanCDK"
            placeholder="留空时使用全局 Mirror 酱 CDK"
            size="large"
            class="modern-input"
            @blur="emit('change', 'Update', 'MirrorChyanCDK', maafwConfig.Update.MirrorChyanCDK)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-alert
      v-if="!isManagedProject && maafwConfig.Update.Source === 'GitHub'"
      class="update-alert"
      type="info"
      show-icon
      message="GitHub 更新源会自动读取项目 interface.json 中声明的仓库，并按项目与平台规则匹配可安装的 Release ZIP；无法唯一匹配时会明确报错。"
    />
    <a-alert
      v-else-if="!isManagedProject && projectUpdateMirrorSourceBlocked"
      class="update-alert"
      type="warning"
      show-icon
      message="MirrorChyan 当前只能发现版本，不能安装更新"
      description="当前仍可执行手动检查；安装需要项目或 MAS 全局 Mirror 酱 CDK，缺少时会显示后端返回的实际错误。"
    />
    <a-row :gutter="24" class="update-action-row">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip
              :title="
                isManagedProject
                  ? '运行任务前检查新版本；可无损迁移时自动切换，否则保留当前版本并生成待确认计划'
                  : '运行 MaaFW 任务前先检查项目更新，更新完成后再读取 interface 与加载资源'
              "
            >
              <span class="form-label">
                运行前自动更新
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-switch
            v-model:checked="maafwConfig.Update.IfAutoUpdate"
            :disabled="isAutoUpdateDisabled"
            checked-children="开启"
            un-checked-children="关闭"
            @change="emit('change', 'Update', 'IfAutoUpdate', maafwConfig.Update.IfAutoUpdate)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item :label="isManagedProject ? '手动管理' : '手动更新'">
          <a-button
            type="primary"
            size="large"
            class="manual-update-button"
            :loading="projectUpdateLoading"
            :disabled="projectUpdateDisabled"
            @click="emit('manual-update')"
          >
            <template #icon>
              <SyncOutlined />
            </template>
            {{
              isManagedProject
                ? '打开项目与依赖'
                : projectUpdateAction === 'apply'
                  ? '开始更新资源'
                  : '检查更新'
            }}
          </a-button>
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item label="更新进度">
          <div
            class="project-update-progress"
            :class="`project-update-progress-${projectUpdateStatus}`"
          >
            <div v-if="isManagedProject" class="project-update-progress-idle">
              运行前自动更新结果写入本次运行日志；手动升级进度请在项目管理页查看
            </div>
            <div v-else-if="projectUpdateStatus === 'idle'" class="project-update-progress-idle">
              尚未开始更新
            </div>
            <template v-else>
              <div class="project-update-progress-header">
                <span>{{ projectUpdateStage || '正在更新项目资源' }}</span>
                <span v-if="displayProgressPercent !== null">
                  总体 {{ displayProgressPercent }}%
                </span>
              </div>
              <a-progress
                v-if="displayProgressPercent !== null"
                :percent="displayProgressPercent"
                :status="progressStatus"
                :show-info="false"
                :stroke-width="8"
              />
              <div
                v-else-if="projectUpdateStatus === 'running'"
                class="project-update-indeterminate-track"
                aria-label="更新进行中，暂时没有可用的总大小"
              >
                <span />
              </div>
              <div v-else class="project-update-failure-track" />
              <div v-if="downloadSummary" class="project-update-progress-detail">
                {{ downloadSummary }}
              </div>
              <div v-if="discoverySummary" class="project-update-progress-detail">
                {{ discoverySummary }}
              </div>
              <div
                v-if="projectUpdateMessage && projectUpdateMessage !== projectUpdateStage"
                class="project-update-progress-message"
              >
                {{ projectUpdateMessage }}
              </div>
              <div
                v-if="projectUpdateProviderErrorCode != null"
                class="project-update-progress-message"
              >
                更新源错误码：{{ projectUpdateProviderErrorCode }}
              </div>
            </template>
          </div>
        </a-form-item>
      </a-col>
    </a-row>
    <div v-if="projectUpdateLogs.length" class="agent-env-log-box project-update-log-box">
      <div
        v-for="(log, index) in projectUpdateLogs"
        :key="`${index}-${log}`"
        class="agent-env-log-line"
      >
        {{ log }}
      </div>
    </div>
    <div v-if="previewData || isManagedProject" class="update-info-grid">
      <div class="update-info-item">
        <div class="update-info-label">当前版本</div>
        <div class="update-info-value">
          {{ maafwConfig.Managed?.Version || previewData?.project.version || '未声明' }}
        </div>
      </div>
      <div class="update-info-item">
        <div class="update-info-label">GitHub</div>
        <div class="update-info-value">
          {{ previewData?.project.github || maafwConfig.Update.GitHubRepo || '未声明' }}
        </div>
      </div>
      <div class="update-info-item">
        <div class="update-info-label">MirrorChyan RID</div>
        <div class="update-info-value">
          {{ previewData?.project.mirrorchyanRid || '未声明' }}
        </div>
      </div>
      <div class="update-info-item">
        <div class="update-info-label">多平台</div>
        <div class="update-info-value">
          {{ previewData?.project.mirrorchyanMultiplatform ? '是' : '否' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QuestionCircleOutlined, SyncOutlined } from '@ant-design/icons-vue'
import type { MaaFWProjectUpdateStatus } from '@/composables/useMaaFWScriptConfig'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'

const props = defineProps<{
  maafwConfig: MaaFWScriptConfig
  previewData: MaaFWInterfacePreviewData | null
  isManagedProject?: boolean
  projectUpdateAction?: 'check' | 'apply'
  isAutoUpdateDisabled: boolean
  projectUpdateLoading: boolean
  projectUpdateDisabled: boolean
  projectUpdateMirrorSourceBlocked: boolean
  projectUpdateStatus: MaaFWProjectUpdateStatus
  projectUpdateStage: string
  projectUpdateProgress: number | null
  projectUpdateDownloadPercent: number | null
  projectUpdateDownloadedBytes: number | null
  projectUpdateTotalBytes: number | null
  projectUpdateMessage: string
  projectUpdateProviderErrorCode?: number | null
  projectUpdateDiscoveredVersion: string
  projectUpdateMetadataSource: string
  projectUpdatePackageSource: string
  projectUpdateLogs: string[]
  updateSourceOptions: Array<{ label: string; value: string }>
  updateChannelOptions: Array<{ label: string; value: string }>
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
  'manual-update': []
}>()

const displayProgressPercent = computed(() => {
  if (props.projectUpdateProgress === null) return null
  return Math.round(Math.min(Math.max(props.projectUpdateProgress, 0), 100))
})

const progressStatus = computed<'active' | 'success' | 'exception'>(() => {
  if (props.projectUpdateStatus === 'completed') return 'success'
  if (props.projectUpdateStatus === 'failed') return 'exception'
  return 'active'
})

const formatBytes = (bytes: number) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const base = 1024
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(base)), units.length - 1)
  return `${Number((bytes / Math.pow(base, unitIndex)).toFixed(2))} ${units[unitIndex]}`
}

const downloadSummary = computed(() => {
  const parts: string[] = []
  if (props.projectUpdateDownloadPercent !== null) {
    parts.push(`下载 ${Math.round(props.projectUpdateDownloadPercent)}%`)
  }
  if (props.projectUpdateDownloadedBytes !== null) {
    const downloaded = formatBytes(props.projectUpdateDownloadedBytes)
    if (props.projectUpdateTotalBytes !== null && props.projectUpdateTotalBytes > 0) {
      parts.push(`${downloaded} / ${formatBytes(props.projectUpdateTotalBytes)}`)
    } else {
      parts.push(`已下载 ${downloaded}`)
    }
  }
  return parts.join(' · ')
})

const discoverySummary = computed(() => {
  const parts: string[] = []
  if (props.projectUpdateDiscoveredVersion) {
    parts.push(`版本 ${props.projectUpdateDiscoveredVersion}`)
  }
  if (props.projectUpdateMetadataSource) {
    parts.push(`元数据 ${props.projectUpdateMetadataSource}`)
  }
  if (props.projectUpdatePackageSource) {
    parts.push(`安装 ${props.projectUpdatePackageSource}`)
  }
  return parts.join(' · ')
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

.update-alert {
  margin-bottom: 16px;
}

.manual-update-button {
  min-width: 160px;
}

.project-update-progress {
  min-height: 40px;
  padding-top: 2px;
}

.project-update-progress-idle,
.project-update-progress-detail,
.project-update-progress-message {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.project-update-progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
  color: var(--ant-color-text);
  font-size: 12px;
  font-weight: 600;
}

.project-update-progress-completed .project-update-progress-header {
  color: var(--ant-color-success);
}

.project-update-progress-failed .project-update-progress-header,
.project-update-progress-failed .project-update-progress-message {
  color: var(--ant-color-error);
}

.project-update-indeterminate-track,
.project-update-failure-track {
  position: relative;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--ant-color-fill-secondary);
}

.project-update-indeterminate-track span {
  position: absolute;
  inset-block: 0;
  width: 38%;
  border-radius: inherit;
  background: var(--ant-color-primary);
  animation: project-update-indeterminate 1.2s ease-in-out infinite;
}

.project-update-failure-track {
  border: 1px solid var(--ant-color-error-border);
  background: var(--ant-color-error-bg);
}

.project-update-progress-detail,
.project-update-progress-message {
  margin-top: 5px;
  overflow-wrap: anywhere;
}

@keyframes project-update-indeterminate {
  from {
    transform: translateX(-110%);
  }
  to {
    transform: translateX(280%);
  }
}

.project-update-log-box {
  margin-bottom: 16px;
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

.update-info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 24px;
  margin-top: 4px;
}

.update-info-item {
  min-width: 0;
}

.update-info-label {
  margin-bottom: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.update-info-value {
  min-height: 22px;
  color: var(--ant-color-text);
  line-height: 1.5;
  overflow-wrap: anywhere;
}

@media (max-width: 768px) {
  .update-info-grid {
    grid-template-columns: 1fr;
  }
}
</style>
