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
            <a-tooltip :title="t('edit.versionChecksAlwaysGo')">
              <span class="form-label">
                {{ t('edit.packageSource') }}
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
        <a-form-item :label="t('edit.channel')">
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
            <a-tooltip :title="t('edit.whenSetScriptS')">
              <span class="form-label">
                {{ t('edit.mirrorchyanCdk') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input-password
            v-model:value="maafwConfig.Update.MirrorChyanCDK"
            :placeholder="t('edit.leaveEmptyUseGlobal')"
            size="large"
            class="modern-input"
            autocomplete="off"
            @blur="emit('change', 'Update', 'MirrorChyanCDK', maafwConfig.Update.MirrorChyanCDK)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-row :gutter="24" class="update-action-row">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.notWiredIntoRun')">
              <span class="form-label">
                {{ t('edit.updateAutomaticallyBeforeRun') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-switch
            :checked="maafwConfig.Update.IfAutoUpdate"
            :disabled="isAutoUpdateDisabled"
            :checked-children="t('edit.on2')"
            :un-checked-children="t('edit.off')"
            @change="handleAutoUpdateChange"
          />
        </a-form-item>
      </a-col>
      <a-col :span="16">
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
    <a-alert
      v-else-if="updateResult"
      class="update-alert"
      :type="updateResultType"
      show-icon
      :message="updateResult.message"
    />

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
import { Modal } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaFWUpdateResult } from '@/composables/useMaaFWUpdateApi'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'

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

const updateResultType = computed<'success' | 'warning' | 'info'>(() => {
  if (!props.updateResult) return 'info'
  if (props.updateResult.updated || !props.updateResult.updateAvailable) return 'success'
  return 'warning'
})

const handleAutoUpdateChange = (checked: boolean) => {
  if (!checked) {
    emit('change', 'Update', 'IfAutoUpdate', false)
    return
  }
  Modal.confirm({
    title: t('edit.updateAutomaticallyBeforeEvery'),
    content: `每次运行前会检查并更新本地目录 ${props.maafwConfig.Info.Path || '（尚未选择）'}。更新失败时旧版本保持可用。`,
    okText: t('edit.on'),
    cancelText: t('edit.keepClosed'),
    onOk: () => emit('change', 'Update', 'IfAutoUpdate', true),
  })
}
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
