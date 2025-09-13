<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { SettingsData } from '@/types/settings'

const { settings, updateTypeOptions, updateSourceOptions, handleSettingChange, checkUpdate } = defineProps<{
  settings: SettingsData
  updateTypeOptions: { label: string; value: string }[]
  updateSourceOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof SettingsData, key: string, value: any) => Promise<void>
  checkUpdate: () => Promise<void>
}>()
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>更新配置</h3>
        <a-button type="primary" @click="checkUpdate" size="medium" class="section-update-button">
          <template #icon>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z" />
            </svg>
          </template>
          检查更新
        </a-button>
      </div>
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">自动检查更新</span>
              <a-tooltip title="启动时自动检测软件更新">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Update.IfAutoUpdate"
              @change="(checked: any) => handleSettingChange('Update', 'IfAutoUpdate', checked)"
              size="large"
              style="width:100%"
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">更新类型</span>
              <a-tooltip title="选择版本更新类型">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Update.UpdateType"
              @change="(value: any) => handleSettingChange('Update', 'UpdateType', value)"
              :options="updateTypeOptions"
              size="large"
              style="width:100%"
            />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">更新源</span>
              <a-tooltip title="选择下载软件更新的来源">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Update.Source"
              @change="(value: any) => handleSettingChange('Update', 'Source', value)"
              :options="updateSourceOptions"
              size="large"
              style="width:100%"
            />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">网络代理地址</span>
              <a-tooltip title="使用网络代理软件时，若出现网络连接问题，请尝试设置代理地址，此设置全局生效">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              v-model:value="settings.Update.ProxyAddress"
              @blur="handleSettingChange('Update', 'ProxyAddress', settings.Update.ProxyAddress)"
              placeholder="请输入网络代理地址"
              size="large"
            />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">Mirror酱 CDK</span>
              <a-tooltip>
                <template #title>
                  <div>
                    Mirror酱CDK是使用Mirror源进行高速下载的凭证，可前往
                    <a href="https://mirrorchyan.com/zh/get-start?source=auto-mas-setting" target="_blank" class="tooltip-link" @click.stop>Mirror酱官网</a>
                    获取
                  </div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              v-model:value="settings.Update.MirrorChyanCDK"
              @blur="handleSettingChange('Update','MirrorChyanCDK', settings.Update.MirrorChyanCDK)"
              :disabled="settings.Update.Source !== 'MirrorChyan'"
              placeholder="使用Mirror源时请输入Mirror酱CDK"
              size="large"
            />
          </div>
        </a-col>
      </a-row>
    </div>
  </div>
</template>
