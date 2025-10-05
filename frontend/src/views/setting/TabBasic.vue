<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { ThemeColor, ThemeMode } from '@/composables/useTheme'
import type { SettingsData } from '@/types/settings'
import type { SelectValue } from 'ant-design-vue/es/select'

const {
  settings,
  themeMode,
  themeColor,
  themeModeOptions,
  themeColorOptions,
  handleThemeModeChange,
  handleThemeColorChange,
  handleSettingChange,
} = defineProps<{
  settings: SettingsData
  themeMode: ThemeMode | 'system'
  themeColor: ThemeColor
  themeModeOptions: { label: string; value: string }[]
  themeColorOptions: { label: string; value: string; color: string }[]
  handleThemeModeChange: (e: any) => void
  handleThemeColorChange: (value: SelectValue) => void
  handleSettingChange: (category: keyof SettingsData, key: string, value: any) => Promise<void>
}>()
</script>

<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>外观配置</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">主题模式</span>
              <a-tooltip title="界面外观主题">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-radio-group
              :value="themeMode"
              :options="themeModeOptions"
              size="large"
              @change="handleThemeModeChange"
            />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">主题色</span>
              <a-tooltip title="界面主色调">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="themeColor"
              size="large"
              style="width: 100%"
              @change="handleThemeColorChange"
            >
              <a-select-option
                v-for="option in themeColorOptions"
                :key="option.value"
                :value="option.value"
              >
                <div style="display: flex; align-items: center; gap: 8px">
                  <div
                    :style="{
                      width: '16px',
                      height: '16px',
                      borderRadius: '50%',
                      backgroundColor: option.color,
                    }"
                  />
                  {{ option.label }}
                </div>
              </a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>系统托盘</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">常态显示托盘图标</span>
              <a-tooltip title="即使界面未最小化仍显示系统托盘图标">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.UI.IfShowTray"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('UI', 'IfShowTray', checked)"
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">最小化到托盘</span>
              <a-tooltip title="界面最小化时隐藏到系统托盘">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.UI.IfToTray"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('UI', 'IfToTray', checked)"
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
