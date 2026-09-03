<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.projectUpdate') }}</h3>
    </div>
    <a-alert
      v-if="isAutoUpdateDisabled"
      class="update-alert"
      type="warning"
      show-icon
      :message="t('edit.thisScriptDeclaresNo')"
    />
    <a-row :gutter="24" class="update-config-row">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.autoUpdateModeTip')">
              <span class="form-label">
                {{ t('edit.autoUpdateMode') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="maafwConfig.Update.AutoUpdateMode"
            size="large"
            :disabled="isAutoUpdateDisabled"
            :options="autoUpdateModeOptions"
            @change="(value: string | number) => emit('change', 'Update', 'AutoUpdateMode', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.updateSourceTip')">
              <span class="form-label">
                {{ t('edit.updateSource') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="maafwConfig.Update.Source"
            size="large"
            :options="updateSourceOptions"
            @change="(value: string | number) => emit('change', 'Update', 'Source', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item :label="t('edit.updateChannel')">
          <a-select
            v-model:value="maafwConfig.Update.Channel"
            size="large"
            :options="updateChannelOptions"
            @change="(value: string | number) => emit('change', 'Update', 'Channel', value)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-row :gutter="24" class="update-config-row">
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.cdkTip')">
              <span class="form-label">
                {{ t('edit.mirrorchyanCdk') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input-password
            v-model:value="maafwConfig.Update.MirrorChyanCDK"
            :placeholder="t('edit.cdkPlaceholder')"
            size="large"
            class="modern-input"
            autocomplete="off"
            @blur="emit('change', 'Update', 'MirrorChyanCDK', maafwConfig.Update.MirrorChyanCDK)"
          />
          <div class="form-hint" :class="{ 'form-hint--warning': isCdkMissingForMirror }">
            {{ t('edit.cdkHint') }}
            <a
              :href="MIRRORCHYAN_CDK_URL"
              class="form-hint-link"
              @click="handleExternalLink"
              >{{ t('edit.cdkGetLink') }}</a
            >
          </div>
        </a-form-item>
      </a-col>
    </a-row>
    <a-row :gutter="24" class="update-action-row">
      <a-col :span="24">
        <a-form-item :label="t('edit.updateNow')">
          <a-space wrap>
            <a-button :loading="updateChecking" @click="emit('check-update')">{{
              t('edit.checkUpdates2')
            }}</a-button>
            <a-button
              v-if="updateResult && updateResult.installable"
              type="primary"
              :loading="updateApplying"
              @click="emit('apply-update')"
            >
              {{ t('edit.update') }}
            </a-button>
          </a-space>
        </a-form-item>
      </a-col>
    </a-row>

    <a-alert
      v-if="updateError"
      class="update-alert"
      type="error"
      show-icon
      :message="updateError"
    />
    <template v-else-if="updateResult">
      <a-alert class="update-alert" :type="updateResultType" show-icon :message="updateResult.message">
        <template v-if="updateResultDetail" #description>
          <span class="update-result-detail">{{ updateResultDetail }}</span>
        </template>
      </a-alert>
      <a-alert
        v-if="cdkWarningMessage"
        class="update-alert"
        type="warning"
        show-icon
        :message="cdkWarningMessage"
      />
      <a-alert
        v-else-if="cdkExpiryMessage"
        class="update-alert"
        type="info"
        show-icon
        :message="cdkExpiryMessage"
      />
    </template>

    <div v-if="previewData" class="update-info-grid">
      <div class="update-info-item">
        <div class="update-info-label">{{ t('edit.currentVersion') }}</div>
        <div class="update-info-value">{{ previewData.project.version || '未声明' }}</div>
      </div>
      <div class="update-info-item">
        <div class="update-info-label">GitHub</div>
        <div class="update-info-value">{{ previewData.project.github || '未声明' }}</div>
      </div>
      <div class="update-info-item">
        <div class="update-info-label">MirrorChyan RID</div>
        <div class="update-info-value">
          {{ previewData.project.mirrorchyanRid || '未声明' }}
        </div>
      </div>
      <div class="update-info-item">
        <div class="update-info-label">{{ t('edit.multiPlatform') }}</div>
        <div class="update-info-value">
          {{ previewData.project.mirrorchyanMultiplatform ? '是' : '否' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaFWUpdateResult } from '@/composables/useMaaFWUpdateApi'
import {
  resolveCdkExpiry,
  resolveCdkWarning,
  type MaaFWAutoUpdateMode,
} from '@/composables/useMaaFWProjectUpdate'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'
import { handleExternalLink } from '@/utils/openExternal'

const MIRRORCHYAN_CDK_URL = 'https://mirrorchyan.com?source=automas_script_update'

const { t } = useI18n()

const props = defineProps<{
  maafwConfig: MaaFWScriptConfig
  previewData: MaaFWInterfacePreviewData | null
  isAutoUpdateDisabled: boolean
  updateChecking: boolean
  updateApplying: boolean
  updateError: string
  updateResult: MaaFWUpdateResult | null
  updateSourceOptions: Array<{ label: string; value: string }>
  updateChannelOptions: Array<{ label: string; value: string }>
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
  'check-update': []
  'apply-update': []
}>()

const autoUpdateModeOptions = computed<Array<{ label: string; value: MaaFWAutoUpdateMode }>>(
  () => [
    { label: t('edit.autoUpdateModeOff'), value: 'Off' },
    { label: t('edit.autoUpdateModeBeforeRun'), value: 'BeforeRun' },
    { label: t('edit.autoUpdateModeAfterRun'), value: 'AfterRun' },
  ]
)

const updateResultType = computed<'success' | 'warning' | 'info'>(() => {
  if (!props.updateResult) return 'info'
  if (props.updateResult.updated || !props.updateResult.updateAvailable) return 'success'
  return 'warning'
})

const sourceLabel = (source: string | null | undefined) => {
  const normalized = (source ?? '').trim().toLowerCase()
  if (!normalized) return ''
  if (normalized === 'mirrorchyan') return t('edit.sourceMirrorChyan')
  if (normalized === 'github') return t('edit.sourceGithub')
  return source ?? ''
}

// 检查结果的补充信息：版本名 + 实际下载来源。旧后端不返回这些字段时整行不显示。
const updateResultDetail = computed(() => {
  const result = props.updateResult
  if (!result) return ''
  const parts: string[] = []
  const versionName = result.versionName?.trim() || result.latestVersion?.trim() || ''
  if (versionName) parts.push(`${t('edit.updateResultVersion')}: ${versionName}`)
  const source = sourceLabel(result.source)
  if (source) parts.push(`${t('edit.updateResultSource')}: ${source}`)
  return parts.join('  ·  ')
})

// 选了 Mirror 酱却没填 CDK：下载注定失败，后端不会替用户改走 GitHub，输入框下方直接提醒。
const isCdkMissingForMirror = computed(
  () =>
    props.maafwConfig.Update.Source === 'MirrorChyan' &&
    !props.maafwConfig.Update.MirrorChyanCDK.trim()
)

const cdkWarningMessage = computed(() => {
  const warning = resolveCdkWarning(props.updateResult, props.maafwConfig.Update.Source)
  if (!warning) return ''
  if (warning.message) return warning.message
  if (warning.status === 'absent') return t('edit.cdkMissingForMirror')
  return t('edit.cdkStatusIssue', { status: warning.status })
})

const cdkExpiryMessage = computed(() => {
  const expiry = resolveCdkExpiry(props.updateResult)
  if (!expiry) return ''
  return t('edit.cdkExpiresSoon', { date: expiry.dateText })
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

.update-result-detail {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.form-hint {
  margin-top: 6px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.5;
}

.form-hint--warning {
  color: var(--ant-color-warning);
}

.form-hint-link {
  margin-left: 4px;
  color: var(--ant-color-primary);
  text-decoration: underline;
}

.form-hint-link:hover {
  color: var(--ant-color-primary-hover);
}

.update-config-row {
  margin-top: 4px;
}

.update-action-row {
  margin-top: 4px;
}

.update-info-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-top: 8px;
}

.update-info-item {
  min-width: 0;
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.update-info-label {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.update-info-value {
  margin-top: 4px;
  color: var(--ant-color-text);
  font-size: 14px;
  overflow-wrap: anywhere;
}

@media (max-width: 768px) {
  .update-info-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
