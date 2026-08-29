<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
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
              title="选择包含 interface.json 的 MFW 项目目录；目前仅支持 MFAAvalonia 与 MXU 两类外壳"
            >
              <span class="form-label">
                本地项目目录
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input-group compact class="path-input-group">
            <a-input
              v-model:value="formData.path"
              placeholder="请选择 MFW 项目实际目录"
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
              选择本地目录
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
              读取 interface
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
          message="正在加载 MFW 接口"
          description="请稍候，正在解析 interface.json 中的控制器、资源、任务和选项定义"
        />
      </a-spin>
    </div>
    <div v-else class="interface-guide-card">
      <InboxOutlined class="interface-guide-icon" aria-hidden="true" />
      <h3>选择 MFW 项目</h3>
      <p>选择包含 interface.json 的项目目录，读取控制器、资源和任务。</p>
      <p class="interface-guide-note">
        目前仅支持 MFAAvalonia（如 M9A、MaaKes）与 MXU（如 MaaEnd、MaaYYs）两类外壳，
        其余外壳尚未接入。
      </p>
      <a-button
        type="primary"
        size="large"
        :disabled="interfaceLoading || updateApplying"
        @click="emit('select-path')"
      >
        <template #icon>
          <FolderOpenOutlined />
        </template>
        选择项目目录
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  FileSearchOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import type { MaaFWInterfacePreviewData, MaaFWScriptConfig, ScriptType } from '@/types/script'

defineProps<{
  maafwConfig: MaaFWScriptConfig
  formData: { type: ScriptType; name: string; path: string }
  rules: { name: unknown[]; path: unknown[] }
  previewData: MaaFWInterfacePreviewData | null
  interfaceLoading: boolean
  previewProjectTitle: string
  interfaceStats: Array<{ label: string; value: number }>
  /** 项目更新正在落盘：此时读 interface 会读到半成品，按钮一律禁用。 */
  updateApplying: boolean
}>()

const emit = defineEmits<{
  change: [category: keyof MaaFWScriptConfig, key: string, value: unknown]
  'select-path': []
  'preview-interface': []
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

.interface-guide-note {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
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
