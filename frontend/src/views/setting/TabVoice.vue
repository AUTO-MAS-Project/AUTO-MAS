<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { SettingsData } from '@/types/settings'

const { settings, voiceTypeOptions, handleSettingChange } = defineProps<{
  settings: SettingsData
  voiceTypeOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof SettingsData, key: string, value: any) => Promise<void>
}>()
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>语音配置</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用音效</span>
              <a-tooltip title="是否启用音效功能">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Voice.Enabled"
              @change="(checked: any) => handleSettingChange('Voice', 'Enabled', checked)"
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
              <span class="form-label">音效模式</span>
              <a-tooltip title="选择音效的播报模式">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Voice.Type"
              @change="(value: any) => handleSettingChange('Voice', 'Type', value)"
              :options="voiceTypeOptions"
              :disabled="!settings.Voice.Enabled"
              size="large"
              style="width:100%"
            />
          </div>
        </a-col>
      </a-row>
    </div>
  </div>
</template>
