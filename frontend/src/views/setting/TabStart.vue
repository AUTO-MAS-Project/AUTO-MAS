<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { SettingsData } from '@/types/settings'

const { settings, handleSettingChange } = defineProps<{
  settings: SettingsData
  handleSettingChange: (category: keyof SettingsData, key: string, value: any) => Promise<void>
}>()
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>启动配置</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">开机自启</span>
              <a-tooltip title="在系统启动时自动启动应用">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Start.IfSelfStart"
              @change="(checked: any) => handleSettingChange('Start', 'IfSelfStart', checked)"
              size="large"
              style="width:100%"
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启动后直接最小化</span>
              <a-tooltip title="启动后直接最小化">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Start.IfMinimizeDirectly"
              @change="(checked: any) => handleSettingChange('Start', 'IfMinimizeDirectly', checked)"
              size="large"
              style="width:100%"
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>
  </div>
</template>
