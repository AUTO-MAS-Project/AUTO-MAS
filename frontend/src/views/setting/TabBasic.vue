<script setup lang="ts">
import { computed } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { ThemeColor, ThemeMode } from '@/composables/useTheme'
import type { V6PerfDetectionContext, V6PerfMode } from '@/theme/v6Theme'
import type { GlobalConfig } from '@/api'
import type { SelectValue } from 'ant-design-vue/es/select'
import LogHighlightSettings from '@/components/LogHighlightSettings.vue'

const {
  settings,
  themeMode,
  themeColor,
  themeModeOptions,
  themeColorOptions,
  handleThemeModeChange,
  handleThemeColorChange,
  handleSettingChange,
  perfModeSelectValue,
  detectedPerfMode,
  detectionContext,
  handlePerfModeChange,
} = defineProps<{
  settings: GlobalConfig
  themeMode: ThemeMode | 'system'
  themeColor: ThemeColor
  themeModeOptions: { label: string; value: string }[]
  themeColorOptions: { label: string; value: string; color: string }[]
  handleThemeModeChange: (value: SelectValue) => void
  handleThemeColorChange: (value: SelectValue) => void
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<void>
  perfModeSelectValue: string
  detectedPerfMode: V6PerfMode
  detectionContext: V6PerfDetectionContext
  handlePerfModeChange: (value: SelectValue) => void
}>()

const perfModeOptions = [
  { label: '自动检测', value: 'auto' },
  { label: '标准模式', value: 'normal' },
  { label: '低性能模式', value: 'low' },
]

const detectionSummary = computed(() => {
  const parts: string[] = []
  if (typeof detectionContext.hardwareConcurrency === 'number') {
    parts.push(`CPU ${detectionContext.hardwareConcurrency} 核`)
  }
  if (typeof detectionContext.deviceMemory === 'number') {
    parts.push(`${detectionContext.deviceMemory} GB 内存`)
  }
  if (detectionContext.prefersReducedMotion) {
    parts.push('已请求减少动画')
  }
  return parts.length > 0 ? parts.join(' · ') : '未检测到硬件信息'
})
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
            <a-select
              :value="themeMode"
              size="large"
              style="width: 100%"
              @change="handleThemeModeChange"
            >
              <a-select-option
                v-for="option in themeModeOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </a-select-option>
            </a-select>
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
        <h3>性能模式</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">动画与特效模式</span>
              <a-tooltip
                title="低性能模式会关闭非必要动画、毛玻璃模糊和装饰特效，适合低端设备或偏好简洁界面的用户。自动检测根据 CPU 核心数、内存和系统减少动画偏好决定。"
              >
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="perfModeSelectValue"
              size="large"
              style="width: 100%"
              @change="handlePerfModeChange"
            >
              <a-select-option
                v-for="option in perfModeOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">硬件检测</span>
              <a-tooltip title="基于浏览器 navigator API 检测的硬件信息，用于自动判定性能模式">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <div class="detection-info">
              <span class="detection-summary">{{ detectionSummary }}</span>
              <span v-if="perfModeSelectValue === 'auto'" class="detection-result">
                自动检测结果：
                <strong>{{ detectedPerfMode === 'low' ? '低性能模式' : '标准模式' }}</strong>
              </span>
            </div>
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
              :value="settings.UI?.IfShowTray"
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
              :value="settings.UI?.IfToTray"
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
    <div class="form-section">
      <div class="section-header">
        <h3>窗口控制</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">隐藏关闭按钮</span>
              <a-tooltip
                title="隐藏主窗口右上角的关闭按钮，避免误操作；仍可通过 Alt+F4、任务栏窗口菜单或托盘菜单退出"
              >
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.UI?.IfHideCloseButton"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('UI', 'IfHideCloseButton', checked)"
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>
    <div class="form-section">
      <div class="section-header">
        <h3>日志样式</h3>
      </div>
      <LogHighlightSettings />
    </div>
  </div>
</template>

<style scoped>
.detection-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: var(--v6-color-fill-quaternary, rgba(0, 0, 0, 0.02));
  border-radius: 8px;
  border: 1px solid var(--v6-color-border, rgba(0, 0, 0, 0.06));
}

.detection-summary {
  font-size: 13px;
  color: var(--v6-color-text-secondary, #8e8e93);
  line-height: 1.5;
}

.detection-result {
  font-size: 12px;
  color: var(--v6-color-text-tertiary, #aeaeb2);
}

.detection-result strong {
  color: var(--v6-color-text, inherit);
  font-weight: 600;
}
</style>
