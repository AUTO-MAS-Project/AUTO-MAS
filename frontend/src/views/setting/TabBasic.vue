<script setup lang="ts">
import {
  DashboardOutlined,
  DeleteOutlined,
  FileTextOutlined,
  AimOutlined,
  SkinOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { navigateTo } from '@/router'
import { useLocale } from '@/composables/useLocale'
import type { ThemeColor, ThemeMode } from '@/composables/useTheme'
import { SUPPORTED_LOCALES, type AppLocale } from '@/i18n'
import type { CursorEffect } from '@/types/cursorEffect'
import type { HomeSatelliteStyle } from '@/types/homeSatellite'
import type { PressSoundPhase, PressSoundPreset } from '@/types/pressSound'
import type { GlobalConfig } from '@/api'
import type { SelectValue } from 'ant-design-vue/es/select'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
import LogHighlightSettings from '@/components/LogHighlightSettings.vue'
import MascotSettings from './components/MascotSettings.vue'
import CustomBackgroundSettings from './components/CustomBackgroundSettings.vue'
import PressSoundSettings from './components/PressSoundSettings.vue'
import StartupWindowSettings from './components/StartupWindowSettings.vue'

interface TabBasicProps {
  settings: GlobalConfig
  themeMode: ThemeMode | 'system'
  appearanceValue: string
  appearanceOptions: { label: string; value: string }[]
  themeColor: ThemeColor
  themeColorDisabled?: boolean
  appearanceBusy: boolean
  themeResetting: boolean
  themeModeOptions: { label: string; value: string }[]
  themeColorOptions: { label: string; value: string; color: string }[]
  cursorEffect: CursorEffect
  cursorEffectOptions: { label: string; value: CursorEffect }[]
  lowPerformanceMode: boolean
  lowPerformanceModeSaving: boolean
  pauseHomeEffectsWhenRunning: boolean
  pauseHomeEffectsWhenRunningSaving: boolean
  homeSatelliteStyle: HomeSatelliteStyle
  homeSatelliteStyleSaving: boolean
  pressSoundEnabled: boolean
  pressSoundPreset: PressSoundPreset
  pressSoundCustomPath: string
  pressSoundCustomName: string
  pressSoundCustomReleasePath: string
  pressSoundCustomReleaseName: string
  pressSoundVolume: number
  pressSoundSaving: boolean
  handlePressSoundEnabledChange(_enabled: boolean): Promise<void>
  handlePressSoundPresetChange(value: SelectValue): Promise<void>
  handlePressSoundVolumeChange(_volume: number): Promise<void>
  handlePressSoundImport(kind?: 'single' | 'press' | 'release'): Promise<void>
  handlePressSoundPreview(phase?: PressSoundPhase): void
  handleHomeSatelliteStyleChange(_style: HomeSatelliteStyle): Promise<void>
  handleThemeModeChange(value: SelectValue): Promise<void>
  handleAppearanceChange(value: SelectValue): Promise<void>
  handleAppearanceImport(): Promise<void>
  handleAppearanceRemove(): Promise<void>
  handleThemeColorChange(value: SelectValue): Promise<void>
  handleThemeReset(): Promise<void>
  handleCursorEffectChange(value: SelectValue): Promise<void>
  handleLowPerformanceModeChange(_enabled: boolean): Promise<void>
  handlePauseHomeEffectsWhenRunningChange(_enabled: boolean): Promise<void>
  handleSettingChange(category: keyof GlobalConfig, key: string, value: any): Promise<boolean>
}

const {
  settings,
  themeMode,
  appearanceValue,
  appearanceOptions,
  themeColor,
  themeColorDisabled = false,
  appearanceBusy,
  themeResetting,
  themeModeOptions,
  themeColorOptions,
  cursorEffect,
  cursorEffectOptions,
  lowPerformanceMode,
  lowPerformanceModeSaving,
  pauseHomeEffectsWhenRunning,
  pauseHomeEffectsWhenRunningSaving,
  homeSatelliteStyle,
  homeSatelliteStyleSaving,
  pressSoundEnabled,
  pressSoundPreset,
  pressSoundCustomPath,
  pressSoundCustomName,
  pressSoundCustomReleasePath,
  pressSoundCustomReleaseName,
  pressSoundVolume,
  pressSoundSaving,
  handlePressSoundEnabledChange,
  handlePressSoundPresetChange,
  handlePressSoundVolumeChange,
  handlePressSoundImport,
  handlePressSoundPreview,
  handleHomeSatelliteStyleChange,
  handleThemeModeChange,
  handleAppearanceChange,
  handleAppearanceImport,
  handleAppearanceRemove,
  handleThemeColorChange,
  handleThemeReset,
  handleCursorEffectChange,
  handleLowPerformanceModeChange,
  handlePauseHomeEffectsWhenRunningChange,
  handleSettingChange,
} = defineProps<TabBasicProps>()

const { t } = useI18n()
const { locale, setLocale } = useLocale()
const appearancePresets = computed(() => [
  { label: t('core.setting.basic.defaultAppearance'), value: 'default' },
  ...appearanceOptions.filter(option => option.value.startsWith('appearance:')),
])
const colorSwatches = computed(() =>
  themeColorOptions.filter(option =>
    ['blue', 'purple', 'cyan', 'green', 'orange', 'red'].includes(option.value)
  )
)

const handleLocaleChange = (value: unknown): void => {
  void setLocale(value as AppLocale)
}
</script>

<template>
  <div class="tab-content">
    <StartupWindowSettings :settings="settings" :handle-setting-change="handleSettingChange" />

    <SectionCard :title="t('core.setting.basic.appearance')" :icon="SkinOutlined">
      <template #actions>
        <a-button
          type="link"
          size="small"
          class="header-link"
          :loading="themeResetting"
          :disabled="appearanceBusy"
          @click="handleThemeReset"
        >
          {{ t('core.setting.basic.resetTheme') }}
        </a-button>
      </template>

      <SettingRow
        :label="t('core.setting.basic.themeMode')"
        :hint="t('core.setting.basic.themeModeTip')"
      >
        <a-segmented
          class="theme-mode-control"
          :value="themeMode"
          :options="themeModeOptions"
          :disabled="appearanceBusy || themeColorDisabled"
          :aria-label="t('core.setting.basic.themeMode')"
          @change="(value: string | number) => handleThemeModeChange(value as ThemeMode)"
        />
      </SettingRow>

      <SettingRow
        :label="t('core.setting.basic.themeColor')"
        :hint="t('core.setting.basic.themeColorTip')"
      >
        <div class="color-swatches" :aria-label="t('core.setting.basic.themeColor')">
          <a-button
            v-for="option in colorSwatches"
            :key="option.value"
            type="text"
            shape="circle"
            class="color-swatch"
            :class="{ 'color-swatch--selected': themeColor === option.value }"
            :style="{ '--swatch-color': option.color }"
            :disabled="themeColorDisabled || appearanceBusy"
            :aria-label="option.label"
            :aria-pressed="themeColor === option.value"
            :title="option.label"
            @click="handleThemeColorChange(option.value)"
          >
            <span class="color-dot" aria-hidden="true" />
          </a-button>
        </div>
        <a-select
          class="theme-color-select"
          :value="themeColor"
          :disabled="themeColorDisabled || appearanceBusy"
          :aria-label="t('core.setting.basic.themeColor')"
          @change="handleThemeColorChange"
        >
          <a-select-option
            v-for="option in themeColorOptions"
            :key="option.value"
            :value="option.value"
          >
            <span class="color-option">
              <span
                class="color-dot"
                :style="{ backgroundColor: option.color }"
                aria-hidden="true"
              />
              {{ option.label }}
            </span>
          </a-select-option>
        </a-select>
      </SettingRow>

      <SettingRow :label="t('core.common.language')" :hint="t('core.common.languageTip')">
        <a-select
          class="row-select language-select"
          :value="locale"
          :aria-label="t('core.common.language')"
          @change="handleLocaleChange"
        >
          <a-select-option v-for="item in SUPPORTED_LOCALES" :key="item" :value="item">
            {{ t(`bootstrap.locale.${item}`) }}
          </a-select-option>
        </a-select>
      </SettingRow>

      <SettingRow :label="t('core.setting.basic.appearancePreset')">
        <a-select
          class="row-select appearance-select"
          :value="appearanceValue.startsWith('appearance:') ? appearanceValue : 'default'"
          :options="appearancePresets"
          :disabled="appearanceBusy"
          :aria-label="t('core.setting.basic.appearancePreset')"
          @change="
            (value: SelectValue) => handleAppearanceChange(value === 'default' ? themeMode : value)
          "
        />
      </SettingRow>

      <template #footer>
        <span class="appearance-footer-hint">{{
          t('core.setting.basic.appearanceFooterHint')
        }}</span>
        <div class="appearance-actions">
          <a-button
            :loading="appearanceBusy"
            :disabled="appearanceBusy"
            @click="handleAppearanceImport"
          >
            <template #icon><UploadOutlined /></template>
            {{ t('core.setting.basic.importAppearance') }}
          </a-button>
          <a-button :disabled="appearanceBusy" @click="navigateTo('/theme-store')">
            <template #icon><SkinOutlined /></template>
            {{ t('core.setting.basic.themeStore') }}
          </a-button>
          <a-button
            v-if="appearanceValue.startsWith('appearance:')"
            danger
            :loading="appearanceBusy"
            :disabled="appearanceBusy"
            @click="handleAppearanceRemove"
          >
            <template #icon><DeleteOutlined /></template>
            {{ t('core.setting.basic.removeAppearance') }}
          </a-button>
        </div>
      </template>
    </SectionCard>

    <CustomBackgroundSettings />

    <MascotSettings />

    <PressSoundSettings
      :enabled="pressSoundEnabled"
      :preset="pressSoundPreset"
      :volume="pressSoundVolume"
      :saving="pressSoundSaving"
      :custom-path="pressSoundCustomPath"
      :custom-name="pressSoundCustomName"
      :custom-release-path="pressSoundCustomReleasePath"
      :custom-release-name="pressSoundCustomReleaseName"
      @enabled-change="handlePressSoundEnabledChange"
      @preset-change="handlePressSoundPresetChange"
      @volume-change="handlePressSoundVolumeChange"
      @import="handlePressSoundImport"
      @preview="handlePressSoundPreview"
    />

    <!-- 光标效果：只有一个开关式选项，一行即可 -->
    <SectionCard :title="t('core.setting.basic.cursorSection')" :icon="AimOutlined">
      <SettingRow
        :label="t('core.setting.basic.cursorAnim')"
        :hint="t('core.setting.basic.cursorTip')"
      >
        <a-segmented
          :value="cursorEffect"
          :options="cursorEffectOptions"
          :aria-label="t('core.setting.basic.cursorAnim')"
          @change="(value: any) => handleCursorEffectChange(value)"
        />
      </SettingRow>
    </SectionCard>

    <!-- 性能配置：三个开关/分段，全部单行 -->
    <SectionCard :title="t('core.setting.basic.perfSection')" :icon="DashboardOutlined">
      <SettingRow
        :label="t('core.setting.basic.lowPerf')"
        :hint="t('core.setting.basic.lowPerfTip')"
      >
        <a-switch
          :checked="lowPerformanceMode"
          :loading="lowPerformanceModeSaving"
          :disabled="lowPerformanceModeSaving"
          :aria-busy="lowPerformanceModeSaving"
          :aria-label="t('core.setting.basic.lowPerf')"
          @change="
            (checked: boolean | string | number) => handleLowPerformanceModeChange(!!checked)
          "
        />
      </SettingRow>

      <SettingRow
        :label="t('core.setting.basic.homeSatellite')"
        :hint="t('core.setting.basic.homeSatelliteTip')"
      >
        <a-segmented
          :value="homeSatelliteStyle"
          :options="[
            { label: t('core.setting.basic.homeSatelliteClassic'), value: 'classic' },
            { label: t('core.setting.basic.homeSatelliteGalaxy'), value: 'galaxy' },
          ]"
          :disabled="homeSatelliteStyleSaving"
          :aria-label="t('core.setting.basic.homeSatellite')"
          @change="(value: any) => handleHomeSatelliteStyleChange(value)"
        />
      </SettingRow>

      <SettingRow
        :label="t('core.setting.basic.pauseHomeEffects')"
        :hint="t('core.setting.basic.pauseHomeEffectsTip')"
      >
        <a-switch
          :checked="pauseHomeEffectsWhenRunning"
          :loading="pauseHomeEffectsWhenRunningSaving"
          :disabled="pauseHomeEffectsWhenRunningSaving"
          :aria-busy="pauseHomeEffectsWhenRunningSaving"
          :aria-label="t('core.setting.basic.pauseHomeEffects')"
          @change="
            (checked: boolean | string | number) =>
              handlePauseHomeEffectsWhenRunningChange(!!checked)
          "
        />
      </SettingRow>
    </SectionCard>

    <!-- 日志样式：内容由 LogHighlightSettings 自带行式布局，卡片只提供标题 -->
    <SectionCard :title="t('core.setting.basic.logStyle')" :icon="FileTextOutlined">
      <LogHighlightSettings />
    </SectionCard>
  </div>
</template>

<style scoped>
.header-link {
  height: auto;
  padding: 0;
}

.row-select {
  width: 204px;
  max-width: 100%;
}

.theme-color-select {
  width: 120px;
}

.color-swatches {
  display: flex;
  gap: 6px;
}

.color-swatch {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  padding: 3px;
}

.color-swatch--selected {
  outline: 2px solid var(--swatch-color);
  outline-offset: -2px;
}

.color-swatch .color-dot {
  background: var(--swatch-color);
}

.appearance-footer-hint {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.appearance-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.color-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.color-dot {
  width: 14px;
  height: 14px;
  flex: 0 0 14px;
  border-radius: 50%;
}
</style>
