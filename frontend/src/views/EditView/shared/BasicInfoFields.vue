<template>
  <div class="form-section basic-info-section">
    <div class="section-header">
      <h3>基本信息</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item name="name" :rules="nameRules">
          <template #label>
            <span class="form-label">
              {{ nameLabel }}
              <a-tooltip :title="nameTooltip">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input
            :value="modelValue.name"
            placeholder="请输入脚本名称"
            size="large"
            class="modern-input"
            @update:value="(v: string) => emit('update:name', v)"
            @blur="emit('blur-name')"
          />
        </a-form-item>
      </a-col>
      <a-col :span="16">
        <a-form-item name="path" :rules="pathRules">
          <template #label>
            <span class="form-label">
              {{ pathLabel }}
              <a-tooltip :title="pathTooltip">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input-group compact class="path-input-group">
            <a-input
              :value="modelValue.path"
              :placeholder="pathPlaceholder"
              size="large"
              class="path-input"
              readonly
            />
            <a-button size="large" class="path-button" @click="emit('select-path')">
              <template #icon>
                <FolderOpenOutlined />
              </template>
              {{ pathButtonText }}
            </a-button>
          </a-input-group>
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { FolderOpenOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { PropType } from 'vue'

interface BasicInfoModel {
  name: string
  path: string
}

defineProps({
  modelValue: {
    type: Object as PropType<BasicInfoModel>,
    required: true,
  },
  nameLabel: {
    type: String,
    default: '脚本名称',
  },
  nameTooltip: {
    type: String,
    default: '',
  },
  pathLabel: {
    type: String,
    default: '路径',
  },
  pathTooltip: {
    type: String,
    default: '',
  },
  pathPlaceholder: {
    type: String,
    default: '请选择路径',
  },
  pathButtonText: {
    type: String,
    default: '选择目录',
  },
  nameRules: {
    type: Array as PropType<unknown[]>,
    default: () => [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  },
  pathRules: {
    type: Array as PropType<unknown[]>,
    default: () => [{ required: true, message: '请选择路径', trigger: 'blur' }],
  },
})

const emit = defineEmits<{
  (event: 'update:name', value: string): void
  (event: 'blur-name'): void
  (event: 'select-path'): void
}>()
</script>

<style scoped>
.basic-info-section {
  margin-bottom: 12px;
}

.section-header {
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
}

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
  background: var(--ant-color-bg-container) !important;
}

.path-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  border-left: 1px solid var(--ant-color-border-secondary);
}
</style>
