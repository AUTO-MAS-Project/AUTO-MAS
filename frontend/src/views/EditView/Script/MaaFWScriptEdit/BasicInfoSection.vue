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
            <!-- interface 是选完目录自动读的、项目不更新就不会变，这个按钮真正的用处是
                 手动重新准备运行环境（不沿用指纹缓存）；顺带把 interface 再读一遍 -->
            <a-button
              size="large"
              class="path-button"
              :loading="interfaceLoading || envPreparing"
              :disabled="!maafwConfig.Info.Path || updateApplying"
              @click="emit('preview-interface')"
            >
              <template #icon>
                <ToolOutlined />
              </template>
              {{ t('edit.prepareRuntimeEnv') }}
            </a-button>
          </a-input-group>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 左边 interface 概览表（表头是项目名与简介），右边运行环境准备面板：
         结论直接作为日志的最后一行用强调色写出来，不另起状态行 -->
    <div v-if="previewData" class="interface-body">
      <a-descriptions bordered size="small" :column="2" class="interface-table">
        <template #title>
          <div class="interface-table-head">
            <span class="interface-table-title">{{ previewProjectTitle }}</span>
            <span v-if="previewData.project.version" class="interface-table-subtitle">
              {{ previewData.project.version }}
              <template v-if="previewData.project?.description">
                · {{ previewData.project.description }}
              </template>
            </span>
          </div>
        </template>
        <a-descriptions-item v-for="item in interfaceStats" :key="item.label" :label="item.label">
          {{ item.value }}
        </a-descriptions-item>
      </a-descriptions>
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
        <div ref="envLogBoxRef" class="env-log-box">
          <div v-if="envTone === 'idle'" class="env-log-line env-log-line--empty">
            {{ t('edit.envPanelPlaceholder') }}
          </div>
          <div v-for="(line, index) in envLogs" :key="index" class="env-log-line">
            {{ line }}
          </div>
          <div
            v-if="envTone !== 'idle'"
            class="env-log-status"
            :class="`env-log-status--${envTone}`"
          >
            <LoadingOutlined v-if="envTone === 'running'" spin class="env-log-status-icon" />
            <CheckCircleOutlined v-else-if="envTone === 'success'" class="env-log-status-icon" />
            <CloseCircleOutlined v-else class="env-log-status-icon" />
            <span>{{ envStatusText }}</span>
            <div v-if="envTone === 'failed'" class="env-log-status-hint">
              {{ t('edit.envFailedHint') }}
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
  FolderOpenOutlined,
  InboxOutlined,
  LoadingOutlined,
  QuestionCircleOutlined,
  ToolOutlined,
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

// 整行一个颜色：状态词 · MaaFramework 版本 · 已就绪的 Agent；失败时后端那句原因就是整行
const envStatusText = computed(() => {
  if (envTone.value === 'failed') return props.envMessage || envPhaseLabel.value
  const parts: string[] = [envPhaseLabel.value]
  if (props.envMessage) parts.push(props.envMessage)
  if (envTone.value === 'success' && props.envAgents.length) {
    const agents = props.envAgents.map(a => a.runtimeKind || t('common.unknown')).join('、')
    parts.push(`${t('edit.envReadyAgents')}: ${agents}`)
  }
  return parts.filter(Boolean).join('  ·  ')
})

// 新日志或结论行变了就贴到底部；用户手动往上翻时不打断
const envLogBoxRef = ref<HTMLElement | null>(null)
watch(
  () => [props.envLogs.length, envTone.value, envStatusText.value],
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

/* 左边 interface 概览表（四列：两组「项 / 值」），右边运行环境面板；两边等高，面板里的日志框撑满 */
.interface-body {
  display: grid;
  grid-template-columns: minmax(300px, 2fr) 3fr;
  gap: 12px;
  align-items: stretch;
  margin-top: 8px;
}

.interface-table {
  min-width: 0;
}

.interface-table :deep(.ant-descriptions-header) {
  margin-bottom: 8px;
}

/* 六个数字而已，用不着 small 档默认的 8px 16px 内距，压紧一点 */
.interface-table :deep(.ant-descriptions-item-label),
.interface-table :deep(.ant-descriptions-item-content) {
  padding: 4px 12px;
  font-size: 13px;
}

.interface-table :deep(.ant-descriptions-item-label) {
  width: 22%;
  color: var(--ant-color-text-secondary);
}

.interface-table :deep(.ant-descriptions-item-content) {
  width: 28%;
}

/* 表头一行：项目名在左，版本 · 简介跟在右边 */
.interface-table-head {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 12px;
  white-space: normal;
}

.interface-table-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--ant-color-text);
  overflow-wrap: anywhere;
}

.interface-table-subtitle {
  min-width: 0;
  font-size: 13px;
  font-weight: 400;
  color: var(--ant-color-text-tertiary);
  overflow-wrap: anywhere;
}

/* 面板本身不画框：标题 + 日志框就够了，外面再套一层边框显得重 */
.env-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
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

/* 定高、内部滚动：日志再长面板也不长个（flex:1 会让面板跟着内容长，grid 行高被它撑开） */
.env-log-box {
  height: 170px;
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

/* 结论就是日志的最后一行，整行一个强调色：成功绿、失败红、进行中主色 */
.env-log-status {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}

.env-log-status--running {
  color: var(--ant-color-primary);
}

.env-log-status--success {
  color: var(--ant-color-success);
}

.env-log-status--failed {
  color: var(--ant-color-error);
}

.env-log-status-hint {
  flex-basis: 100%;
  color: var(--ant-color-text-secondary);
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
