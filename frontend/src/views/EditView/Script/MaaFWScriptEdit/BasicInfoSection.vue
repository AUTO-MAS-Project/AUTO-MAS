<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.basicInfo') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item name="name">
          <template #label>
            <a-tooltip :title="t('edit.giveProjectNameYou')">
              <span class="form-label">
                {{ t('edit.scriptName') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="formData.name"
            :placeholder="t('edit.enterScriptName')"
            size="large"
            class="modern-input"
            @blur="emit('change', 'Info', 'Name', formData.name)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="16">
        <a-form-item name="path" :rules="rules.path">
          <template #label>
            <a-tooltip :title="t('edit.pickMfwProjectDirectory')">
              <span class="form-label">
                {{ t('edit.localProjectDirectory') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input-group compact class="path-input-group">
            <a-input
              v-model:value="formData.path"
              :placeholder="t('edit.pickActualMfwProject')"
              size="large"
              class="path-input"
              readonly
              aria-readonly="true"
            />
            <a-button
              size="large"
              class="path-button"
              :disabled="interfaceLoading || updateApplying"
              @click="emit('select-path')"
            >
              <template #icon>
                <FolderOpenOutlined />
              </template>
              {{ t('edit.pickLocalDirectory') }}
            </a-button>
            <a-button
              size="large"
              class="path-button"
              :loading="interfaceLoading"
              :disabled="!maafwConfig.Info.Path || updateApplying"
              @click="emit('preview-interface')"
            >
              <template #icon>
                <FileSearchOutlined />
              </template>
              {{ t('edit.readInterface') }}
            </a-button>
          </a-input-group>
        </a-form-item>
      </a-col>
    </a-row>

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
      <!-- 左边 interface 各项数值，右边运行环境准备面板：状态词用强调色，日志框定高内部滚动 -->
      <div class="interface-body">
        <div class="interface-stat-grid">
          <div v-for="item in interfaceStats" :key="item.label" class="interface-stat-card">
            <div class="interface-stat-value">{{ item.value }}</div>
            <div class="interface-stat-label">{{ item.label }}</div>
          </div>
        </div>
        <div class="env-panel">
          <div class="env-panel-header">
            <span class="env-panel-title">{{ t('edit.envPanelTitle') }}</span>
            <a-button
              v-if="envTone === 'failed'"
              size="small"
              :loading="envPreparing"
              @click="emit('retry-env')"
            >
              {{ t('edit.envRetry') }}
            </a-button>
          </div>
          <div v-if="envTone === 'idle'" class="env-panel-placeholder">
            {{ t('edit.envPanelPlaceholder') }}
          </div>
          <div v-else class="env-panel-summary" :class="`env-panel-summary--${envTone}`">
            <LoadingOutlined v-if="envTone === 'running'" spin class="env-panel-icon" />
            <CheckCircleOutlined v-else-if="envTone === 'success'" class="env-panel-icon" />
            <CloseCircleOutlined v-else class="env-panel-icon" />
            <span class="env-panel-phase">{{ envPhaseLabel }}</span>
            <span v-if="envDetail" class="env-panel-detail">{{ envDetail }}</span>
          </div>
          <div v-if="envTone === 'failed'" class="env-panel-hint">
            {{ t('edit.envFailedHint') }}
          </div>
          <a-progress
            v-if="envTone === 'running' && envPercent !== null"
            :percent="envPercent"
            size="small"
            status="active"
            class="env-panel-bar"
          />
          <div ref="envLogBoxRef" class="env-log-box">
            <div
              v-if="envTone !== 'idle' && !envLogs.length"
              class="env-log-line env-log-line--empty"
            >
              {{ t('edit.updateProcessNoLogYet') }}
            </div>
            <div v-for="(line, index) in envLogs" :key="index" class="env-log-line">
              {{ line }}
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="interfaceLoading" class="interface-loading">
      <a-spin :tip="t('edit.readingInterfaceJson')">
        <a-alert
          type="info"
          show-icon
          :message="t('edit.loadingMfwInterface')"
          :description="t('edit.readingControllersResourcesTasks')"
        />
      </a-spin>
    </div>
    <div v-else class="interface-guide-card">
      <InboxOutlined class="interface-guide-icon" aria-hidden="true" />
      <h3>{{ t('edit.pickMfwProject') }}</h3>
      <p>{{ t('edit.pickProjectDirectoryContaining') }}</p>
      <a-button
        type="primary"
        size="large"
        :disabled="interfaceLoading || updateApplying"
        @click="emit('select-path')"
      >
        <template #icon>
          <FolderOpenOutlined />
        </template>
        {{ t('edit.pickProjectDirectory') }}
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, nextTick, ref, watch } from 'vue'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  LoadingOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig, ScriptType } from '@/types/script'

/** 一次准备的结果：首次准备 / 更新了已有环境 / 项目没变直接沿用。 */
export type MaaFWEnvOutcome = 'prepared' | 'updated' | 'cached'

const { t } = useI18n()

const props = defineProps<{
  maafwConfig: MaaFWScriptConfig
  formData: { type: ScriptType; name: string; path: string }
  rules: { name: unknown[]; path: unknown[] }
  previewData: MaaFWInterfacePreviewData | null
  interfaceLoading: boolean
  previewProjectTitle: string
  interfaceStats: Array<{ label: string; value: number }>
  /** 项目更新正在落盘：此时读 interface 会读到半成品，按钮一律禁用。 */
  updateApplying: boolean
  envPreparing: boolean
  envReady: boolean
  envFailed: boolean
  /** 准备中是后端当前阶段那句话；成功后是 MaaFramework 版本；失败时是错误原因。 */
  envMessage: string
  envPercent: number | null
  envLogs: string[]
  envAgents: Array<{ runtimeKind?: string | null; executable: string }>
  envOutcome: MaaFWEnvOutcome | null
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
  'select-path': []
  'preview-interface': []
  'retry-env': []
}>()

const envTone = computed<'idle' | 'running' | 'success' | 'failed'>(() => {
  if (props.envPreparing) return 'running'
  if (props.envFailed) return 'failed'
  if (props.envReady) return 'success'
  return 'idle'
})

// 状态词就是结论本身：准备完成 / 更新完成 / 无需更新 / 失败，不再另起一条绿色 alert
const envPhaseLabel = computed(() => {
  switch (envTone.value) {
    case 'running': {
      const label = t('edit.envStatusPreparing')
      return props.envPercent === null ? label : `${label} ${Math.round(props.envPercent)}%`
    }
    case 'failed':
      return t('edit.envStatusFailed')
    case 'success':
      if (props.envOutcome === 'cached') return t('edit.envStatusCached')
      if (props.envOutcome === 'updated') return t('edit.envStatusUpdated')
      return t('edit.envStatusPrepared')
    default:
      return ''
  }
})

const envDetail = computed(() => {
  if (envTone.value !== 'success') return props.envMessage
  const parts: string[] = []
  if (props.envMessage) parts.push(props.envMessage)
  if (props.envAgents.length) {
    const agents = props.envAgents.map(a => a.runtimeKind || t('common.unknown')).join('、')
    parts.push(`${t('edit.envReadyAgents')}: ${agents}`)
  }
  return parts.join('  ·  ')
})

// 新日志来了就贴到底部；用户手动往上翻时不打断
const envLogBoxRef = ref<HTMLElement | null>(null)
watch(
  () => props.envLogs.length,
  async () => {
    const box = envLogBoxRef.value
    if (!box) return
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40
    await nextTick()
    if (nearBottom) box.scrollTop = box.scrollHeight
  }
)
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
  /* flex 子项默认 min-width:auto，窄屏下会被内容撑住不肯让位，
     把两个按钮挤出圆角容器；显式归零才能正常收缩。 */
  min-width: 0;
  border: none !important;
  border-radius: 0 !important;
}

.path-input:focus {
  box-shadow: none !important;
}

.path-button {
  /* 两个按钮共用一套样式：各自带左分隔线，与输入框拼成一条完整控件。 */
  flex: 0 0 auto;
  white-space: nowrap;
  border: none;
  border-left: 1px solid var(--ant-color-border-secondary);
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
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

/* 左右各半：左边六个数值格排两行，右边运行环境面板；两边等高 */
.interface-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  align-items: stretch;
}

.interface-stat-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-auto-rows: 1fr;
  gap: 12px;
  min-width: 0;
}

/* 运行环境面板只用边框分隔，不铺底色；样式与项目更新区的过程面板一致 */
.env-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}

.env-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.env-panel-title {
  font-weight: 600;
  color: var(--ant-color-text);
}

.env-panel-placeholder {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.env-panel-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 13px;
  color: var(--ant-color-text);
}

.env-panel-icon {
  font-size: 14px;
}

/* 状态词用强调色：成功绿、失败红、进行中主色 */
.env-panel-phase {
  font-weight: 600;
}

.env-panel-summary--running .env-panel-icon,
.env-panel-summary--running .env-panel-phase {
  color: var(--ant-color-primary);
}

.env-panel-summary--success .env-panel-icon,
.env-panel-summary--success .env-panel-phase {
  color: var(--ant-color-success);
}

.env-panel-summary--failed .env-panel-icon,
.env-panel-summary--failed .env-panel-phase {
  color: var(--ant-color-error);
}

.env-panel-detail {
  color: var(--ant-color-text-secondary);
  overflow-wrap: anywhere;
}

.env-panel-hint {
  margin-top: 2px;
  padding-left: 22px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.env-panel-bar {
  margin: 6px 0 2px;
}

/* 定高、内部滚动：日志再长面板也不长个，左边的数值格才对得齐 */
.env-log-box {
  margin-top: 8px;
  height: 150px;
  overflow-y: auto;
  padding: 8px 10px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  font-family: var(--ant-font-family-code, monospace);
  font-size: 12px;
  line-height: 1.6;
}

.env-log-line {
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--ant-color-text-secondary);
}

.env-log-line--empty {
  color: var(--ant-color-text-tertiary);
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

.interface-loading {
  margin-top: 8px;
  padding: 16px;
}

.interface-loading :deep(.ant-spin-container) {
  opacity: 1;
}

@media (max-width: 768px) {
  .interface-body {
    grid-template-columns: 1fr;
  }
}
</style>
