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
            <a-tooltip
              :title="
                embeddedStatus.enabled
                  ? t('edit.maafwEmbeddedSourceHint')
                  : t('edit.pickMfwProjectDirectory')
              "
            >
              <span class="form-label">
                {{
                  embeddedStatus.enabled
                    ? t('edit.maafwEmbeddedSourceDirectory')
                    : t('edit.localProjectDirectory')
                }}
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
              :disabled="interfaceLoading || updateApplying || embeddedBusy"
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
              :disabled="!maafwConfig.Info.Path || updateApplying || embeddedBusy"
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

    <!-- 内嵌：AUTO-MAS 按 interface 白名单投影一份瘦副本并在副本上运行、更新；
         副本目录由脚本 ID 推出，不展示为可编辑项；来源目录（Info.Path）保持不动。 -->
    <div class="embedded-panel" :class="{ 'embedded-panel-on': embeddedStatus.enabled }">
      <div class="embedded-head">
        <div class="embedded-switch">
          <a-switch
            :checked="embeddedStatus.enabled"
            :loading="embeddedBusy"
            :disabled="!maafwConfig.Info.Path || interfaceLoading || updateApplying"
            @change="
              (checked: boolean | string | number) => emit('toggle-embedded', Boolean(checked))
            "
          />
          <a-tooltip :title="t('edit.maafwEmbeddedHint')">
            <span class="form-label">
              {{ t('edit.maafwEmbeddedTitle') }}
              <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
            </span>
          </a-tooltip>
        </div>
        <a-space v-if="embeddedStatus.enabled" size="small">
          <a-tooltip :title="t('edit.maafwEmbeddedReimportHint')">
            <a-button
              size="small"
              :loading="embeddedBusy"
              :disabled="!embeddedStatus.sourceExists || interfaceLoading || updateApplying"
              @click="emit('reimport-embedded')"
            >
              <template #icon>
                <ReloadOutlined />
              </template>
              {{ t('edit.maafwEmbeddedReimport') }}
            </a-button>
          </a-tooltip>
        </a-space>
      </div>
      <div v-if="embeddedStatus.enabled" class="embedded-meta">
        <a-tag v-if="embeddedStatus.copyHealthy" color="success" class="embedded-tag">
          {{ t('edit.maafwEmbeddedCopyHealthy') }}
        </a-tag>
        <a-tag v-else color="warning" class="embedded-tag">
          {{ t('edit.maafwEmbeddedCopyMissing') }}
        </a-tag>
        <span v-if="embeddedStatus.report" class="embedded-meta-item">
          {{
            t('edit.maafwEmbeddedSaved', {
              percent: (embeddedStatus.report.savedPercent ?? 0).toFixed(1),
              source: formatEmbeddedBytes(embeddedStatus.report.sourceSizeBytes),
              copy: formatEmbeddedBytes(embeddedStatus.report.payloadSizeBytes),
            })
          }}
        </span>
        <span v-if="embeddedShellFamilies" class="embedded-meta-item">
          {{ t('edit.maafwEmbeddedShell', { shell: embeddedShellFamilies }) }}
        </span>
        <span v-if="embeddedStatus.report?.bundledMaaFWVersion" class="embedded-meta-item">
          {{
            t('edit.maafwEmbeddedRuntime', { version: embeddedStatus.report.bundledMaaFWVersion })
          }}
        </span>
        <span v-if="embeddedStatus.report?.bundledPythonVersion" class="embedded-meta-item">
          {{
            t('edit.maafwEmbeddedPython', { version: embeddedStatus.report.bundledPythonVersion })
          }}
        </span>
        <span v-if="embeddedStatus.sourceVersion" class="embedded-meta-item">
          {{ t('edit.maafwEmbeddedSourceVersion', { version: embeddedStatus.sourceVersion }) }}
        </span>
        <span v-if="embeddedImportedAt" class="embedded-meta-item">
          {{ t('edit.maafwEmbeddedImportedAt', { time: embeddedImportedAt }) }}
        </span>
        <span v-if="!embeddedStatus.sourceExists" class="embedded-meta-item embedded-meta-warn">
          {{ t('edit.maafwEmbeddedSourceMissing') }}
        </span>
      </div>
      <div v-else class="embedded-meta embedded-meta-off">
        {{ t('edit.maafwEmbeddedOffHint') }}
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
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  FileSearchOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig, ScriptType } from '@/types/script'
import { formatEmbeddedBytes, type MaaFWEmbeddedStatus } from '@/composables/useMaaFWEmbeddedApi'

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
  /** 内嵌副本状态：由父组件从后端拉取；导入几十到几百 MB 时 busy 为 true。 */
  embeddedStatus: MaaFWEmbeddedStatus
  embeddedBusy: boolean
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
  'select-path': []
  'preview-interface': []
  'toggle-embedded': [enabled: boolean]
  'reimport-embedded': []
}>()

const embeddedShellFamilies = computed(() =>
  (props.embeddedStatus.report?.shellFamilies ?? []).join(' / ')
)

// 后端给的是带时区的 ISO 文本；界面上只要到分钟。
const embeddedImportedAt = computed(() => {
  const raw = props.embeddedStatus.importedAt
  if (!raw) return ''
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  return parsed.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
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

.embedded-panel {
  margin: -8px 0 16px;
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.embedded-panel-on {
  border-color: var(--ant-color-primary-border);
  background: var(--ant-color-primary-bg);
}

.embedded-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.embedded-switch {
  display: flex;
  align-items: center;
  gap: 12px;
}

.embedded-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.embedded-meta-off {
  color: var(--ant-color-text-tertiary);
}

.embedded-tag {
  margin: 0;
}

.embedded-meta-item {
  white-space: nowrap;
}

.embedded-meta-warn {
  color: var(--ant-color-warning);
  white-space: normal;
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

.interface-loading {
  margin-top: 8px;
  padding: 16px;
}

.interface-loading :deep(.ant-spin-container) {
  opacity: 1;
}

@media (max-width: 768px) {
  .interface-stat-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
