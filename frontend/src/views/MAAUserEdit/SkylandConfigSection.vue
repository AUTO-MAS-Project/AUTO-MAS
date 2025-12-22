<template>
  <div class="form-section">
    <div class="section-header">
      <h3>森空岛配置</h3>
      <a href="https://doc.auto-mas.top/docsV5/script-guide/maa.html#%E6%A3%AE%E7%A9%BA%E5%B2%9B%E8%87%AA%E5%8A%A8%E7%AD%BE%E5%88%B0"
        class="section-doc-link" title="查看森空岛签到配置文档" @click="handleExternalLink">
        文档
      </a>
    </div>
    <a-row :gutter="24" align="middle">
      <a-col :span="6">
        <span style="font-weight: 500">森空岛签到</span>
      </a-col>
      <a-col :span="18">
        <a-switch v-model:checked="formData.Info.IfSkland" :disabled="loading" @change="emitSave('Info.IfSkland', formData.Info.IfSkland)" />
        <span class="switch-description">开启后将启用森空岛签到功能</span>
      </a-col>
    </a-row>
    <a-row :gutter="24" style="margin-top: 16px">
      <a-col :span="24">
        <span style="font-weight: 500">森空岛Token</span>
        <a-input-password v-model:value="formData.Info.SklandToken" :disabled="loading || !formData.Info.IfSkland"
          placeholder="请输入森空岛Token" size="large" style="margin-top: 8px; width: 100%" allow-clear
          @blur="emitSave('Info.SklandToken', formData.Info.SklandToken)" />
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { handleExternalLink } from '@/utils/openExternal'

defineProps<{
  formData: any
  loading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const emitSave = (key: string, value: any) => {
  emit('save', key, value)
}
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.section-doc-link {
  color: var(--ant-color-primary) !important;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--ant-color-primary);
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 4px;
}

.section-doc-link:hover {
  color: var(--ant-color-primary-hover) !important;
  background-color: var(--ant-color-primary-bg);
  border-color: var(--ant-color-primary-hover);
  text-decoration: none;
}

.switch-description {
  margin-left: 12px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}
</style>
