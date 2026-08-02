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
    <a-row :gutter="24" class="update-config-row">
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
      v-if="maafwConfig.Update.Source === 'GitHub'"
      class="update-alert"
      type="info"
      show-icon
      message="GitHub 更新源会自动读取项目 interface.json 中声明的仓库，默认拉取最新 Release 的第一个 .zip 资产，无需额外填写。"
    />
    <a-row :gutter="24" class="update-action-row">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip
              title="运行 MaaFW 任务前先检查项目更新，更新完成后再读取 interface 与加载资源"
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
        <a-form-item label="手动更新">
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
            立即更新资源
          </a-button>
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
    <div v-if="previewData" class="update-info-grid">
      <div class="update-info-item">
        <div class="update-info-label">当前版本</div>
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
        <div class="update-info-label">多平台</div>
        <div class="update-info-value">
          {{ previewData.project.mirrorchyanMultiplatform ? '是' : '否' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { QuestionCircleOutlined, SyncOutlined } from '@ant-design/icons-vue'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'

defineProps<{
  maafwConfig: MaaFWScriptConfig
  previewData: MaaFWInterfacePreviewData | null
  isAutoUpdateDisabled: boolean
  projectUpdateLoading: boolean
  projectUpdateDisabled: boolean
  projectUpdateLogs: string[]
  updateSourceOptions: Array<{ label: string; value: string }>
  updateChannelOptions: Array<{ label: string; value: string }>
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
  'manual-update': []
}>()
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
