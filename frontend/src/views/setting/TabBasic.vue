<script setup lang="ts">
import { DeleteOutlined, QuestionCircleOutlined, UploadOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

import { useLocale } from '@/composables/useLocale'
import type { ThemeColor, ThemeMode } from '@/composables/useTheme'
import { SUPPORTED_LOCALES, type AppLocale } from '@/i18n'
import type { CursorEffect } from '@/types/cursorEffect'
import type { GlobalConfig } from '@/api'
import type { SelectValue } from 'ant-design-vue/es/select'
import LogHighlightSettings from '@/components/LogHighlightSettings.vue'
import TrayMenuEditor from './components/TrayMenuEditor.vue'

interface TabBasicProps {
  settings: GlobalConfig
  themeMode: ThemeMode | 'system'
  appearanceValue: string
  appearanceOptions: { label: string; value: string }[]
  themeColor: ThemeColor
  themeColorDisabled?: boolean
  appearanceBusy: boolean
  themeModeOptions: { label: string; value: string }[]
  themeColorOptions: { label: string; value: string; color: string }[]
  cursorEffect: CursorEffect
  cursorEffectOptions: { label: string; value: CursorEffect }[]
  lowPerformanceMode: boolean
  lowPerformanceModeSaving: boolean
  handleThemeModeChange(value: SelectValue): Promise<void>
  handleAppearanceChange(value: SelectValue): Promise<void>
  handleAppearanceImport(): Promise<void>
  handleAppearanceRemove(): Promise<void>
  handleThemeColorChange(value: SelectValue): Promise<void>
  handleCursorEffectChange(value: SelectValue): Promise<void>
  handleLowPerformanceModeChange(_enabled: boolean): Promise<void>
  handleSettingChange(category: keyof GlobalConfig, key: string, value: any): Promise<void>
}

const {
  settings,
  themeMode,
  appearanceValue,
  appearanceOptions,
  themeColor,
  themeColorDisabled = false,
  appearanceBusy,
  themeModeOptions,
  themeColorOptions,
  cursorEffect,
  cursorEffectOptions,
  lowPerformanceMode,
  lowPerformanceModeSaving,
  handleThemeModeChange,
  handleAppearanceChange,
  handleAppearanceImport,
  handleAppearanceRemove,
  handleThemeColorChange,
  handleCursorEffectChange,
  handleLowPerformanceModeChange,
  handleSettingChange,
} = defineProps<TabBasicProps>()

const { t } = useI18n()
const { locale, setLocale } = useLocale()

const handleLocaleChange = (value: unknown): void => {
  void setLocale(value as AppLocale)
}
</script>

<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.basic.appearance') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.basic.themeMode') }}</span>
              <a-tooltip :title="t('setting.basic.themeModeTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <div class="appearance-controls">
              <a-select
                class="appearance-select"
                :value="appearanceValue"
                size="large"
                @change="handleAppearanceChange"
              >
                <a-select-option
                  v-for="option in appearanceOptions"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </a-select-option>
              </a-select>
              <a-button
                :aria-label="t('setting.basic.importAppearance')"
                :loading="appearanceBusy"
                :disabled="appearanceBusy"
                @click="handleAppearanceImport"
              >
                <template #icon><UploadOutlined /></template>
                {{ t('setting.basic.importAppearance') }}
              </a-button>
              <a-button
                v-if="appearanceValue.startsWith('appearance:')"
                danger
                :loading="appearanceBusy"
                :disabled="appearanceBusy"
                :aria-label="t('setting.basic.removeAppearance')"
                @click="handleAppearanceRemove"
              >
                <template #icon><DeleteOutlined /></template>
                {{ t('setting.basic.removeAppearance') }}
              </a-button>
            </div>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.basic.themeColor') }}</span>
              <a-tooltip :title="t('setting.basic.themeColorTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="themeColor"
              :disabled="themeColorDisabled"
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
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('common.language') }}</span>
              <a-tooltip :title="t('common.languageTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="locale" size="large" style="width: 100%" @change="handleLocaleChange">
              <a-select-option v-for="item in SUPPORTED_LOCALES" :key="item" :value="item">
                {{ t(`locale.${item}`) }}
              </a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.basic.cursorSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.basic.cursorAnim') }}</span>
              <a-tooltip :title="t('setting.basic.cursorTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="cursorEffect"
              :options="cursorEffectOptions"
              size="large"
              style="width: 100%"
              @change="handleCursorEffectChange"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.basic.perfSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.basic.lowPerf') }}</span>
              <a-tooltip :title="t('setting.basic.lowPerfTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="lowPerformanceMode"
              :disabled="lowPerformanceModeSaving"
              :loading="lowPerformanceModeSaving"
              size="large"
              style="width: 100%"
              @change="(enabled: any) => handleLowPerformanceModeChange(enabled)"
            >
              <a-select-option :value="true">{{ t('common.on') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.off') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.basic.traySection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.basic.showTray') }}</span>
              <a-tooltip :title="t('setting.basic.showTrayTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.UI?.IfShowTray"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('UI', 'IfShowTray', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.basic.minToTray') }}</span>
              <a-tooltip :title="t('setting.basic.minToTrayTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.UI?.IfToTray"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('UI', 'IfToTray', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
      <TrayMenuEditor />
    </div>
    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.basic.windowSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.basic.hideClose') }}</span>
              <a-tooltip :title="t('setting.basic.hideCloseTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.UI?.IfHideCloseButton"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('UI', 'IfHideCloseButton', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>
    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.basic.logStyle') }}</h3>
      </div>
      <LogHighlightSettings />
    </div>
  </div>
</template>

<style scoped>
.appearance-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.appearance-select {
  flex: 1 1 144px;
  min-width: 144px;
}

@media (max-width: 1200px) {
  .appearance-controls {
    align-items: stretch;
    flex-wrap: wrap;
  }

  .appearance-controls :deep(.ant-select) {
    flex-basis: 100%;
  }
}
</style>
