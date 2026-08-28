<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
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
        <a-form-item>
          <template #label>
            <a-tooltip
              title="版本检查统一使用 Mirror酱；此选项只决定安装包下载位置。选择 GitHub 时按 Mirror酱目标版本精确查找同版本 Release，不使用 GitHub latest。"
            >
              <span class="form-label">
                安装包来源
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
            autocomplete="off"
            @blur="emit('change', 'Update', 'MirrorChyanCDK', maafwConfig.Update.MirrorChyanCDK)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-collapse v-if="maafwConfig.Update.Source === 'GitHub'" ghost class="update-advanced">
      <a-collapse-panel
        key="github"
        header="GitHub 高级选项（留空按 interface 与 Mirror酱目标版本解析）"
      >
        <a-row :gutter="24" class="update-config-row">
          <a-col :xs="24" :md="8">
            <a-form-item label="GitHub 仓库">
              <a-input
                v-model:value="maafwConfig.Update.GitHubRepo"
                placeholder="owner/repository（可留空，读取 interface）"
                size="large"
                class="modern-input"
                @blur="emit('change', 'Update', 'GitHubRepo', maafwConfig.Update.GitHubRepo)"
              />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-form-item label="GitHub 版本标签">
              <a-input
                v-model:value="maafwConfig.Update.GitHubTag"
                placeholder="按 Mirror酱目标版本精确匹配"
                size="large"
                class="modern-input"
                @blur="emit('change', 'Update', 'GitHubTag', maafwConfig.Update.GitHubTag)"
              />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-form-item label="资产匹配规则">
              <a-input
                v-model:value="maafwConfig.Update.GitHubAssetPattern"
                placeholder="例如 \.zip$"
                size="large"
                class="modern-input"
                @blur="
                  emit(
                    'change',
                    'Update',
                    'GitHubAssetPattern',
                    maafwConfig.Update.GitHubAssetPattern
                  )
                "
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-collapse-panel>
    </a-collapse>

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
            :checked="maafwConfig.Update.IfAutoUpdate"
            :disabled="isAutoUpdateDisabled"
            checked-children="开启"
            un-checked-children="关闭"
            @change="handleAutoUpdateChange"
          />
        </a-form-item>
      </a-col>
      <a-col :span="16">
        <a-form-item label="手动更新">
          <a-space wrap>
            <a-button :loading="updateChecking" @click="emit('check-update')">检查更新</a-button>
            <a-button
              v-if="updateResult && updateResult.installable"
              type="primary"
              :loading="updateApplying"
              @click="emit('apply-update')"
            >
              执行更新
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
import { computed } from 'vue'
import { Modal } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { MaaFWUpdateResult } from '@/composables/useMaaFWUpdateApi'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig } from '@/types/script'

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
    title: '开启运行前自动更新？',
    content: `每次运行前会检查并更新本地目录 ${props.maafwConfig.Info.Path || '（尚未选择）'}。更新失败时旧版本保持可用。`,
    okText: '开启',
    cancelText: '保持关闭',
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

.update-advanced {
  margin-bottom: 8px;
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
