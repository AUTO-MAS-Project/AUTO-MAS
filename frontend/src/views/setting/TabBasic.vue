<script setup lang="ts">
import { computed } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { ThemeColor, ThemeMode } from '@/composables/useTheme'
import type { V6PerfDetectionContext, V6PerfMode } from '@/theme/v6Theme'
import type { GlobalConfig } from '@/api'
import type { SelectValue } from 'ant-design-vue/es/select'
import LogHighlightSettings from '@/components/LogHighlightSettings.vue'
import SettingTabHeader from './SettingTabHeader.vue'
import type { SettingsCategory } from '@/composables/useSettingsFormGuard'

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
  getEffectiveValue,
  getError,
  clearError,
  hasPending,
  pendingCount,
  retryPending,
  restoreDefaults,
  isSaving,
} = defineProps<{
  settings: GlobalConfig
  themeMode: ThemeMode | 'system'
  themeColor: ThemeColor
  themeModeOptions: { label: string; value: string }[]
  themeColorOptions: { label: string; value: string; color: string }[]
  handleThemeModeChange: (value: SelectValue) => void
  handleThemeColorChange: (value: SelectValue) => void
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
  perfModeSelectValue: string
  detectedPerfMode: V6PerfMode
  detectionContext: V6PerfDetectionContext
  handlePerfModeChange: (value: SelectValue) => void
  /** Lane 8：表单保护 */
  getEffectiveValue: <T>(
    settings: GlobalConfig,
    category: SettingsCategory,
    key: string
  ) => T | undefined
  getError: (category: SettingsCategory) => string | null
  clearError: (category: SettingsCategory) => void
  hasPending: boolean
  pendingCount: number
  retryPending: (category: SettingsCategory) => Promise<void>
  revertField: (category: SettingsCategory, key: string) => void
  restoreDefaults: (category: SettingsCategory) => Promise<void>
  isSaving: (category: SettingsCategory, key: string) => boolean
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

// Lane 8：UI category 辅助
const CATEGORY: SettingsCategory = 'UI'
const eff = <T,>(key: string): T | undefined => getEffectiveValue<T>(settings, CATEGORY, key)
const saving = (key: string): boolean => isSaving(CATEGORY, key)
const errorMsg = (): string | null => getError(CATEGORY)
const onClearError = (): void => clearError(CATEGORY)
const onRetryPending = (): Promise<void> => retryPending(CATEGORY)
const onRestoreDefaults = (): Promise<void> => restoreDefaults(CATEGORY)
</script>

<template>
  <div class="tab-content">
    <!-- 统一 Tab 状态条：说明、错误、恢复默认和重试 -->
    <SettingTabHeader
      description="配置主题外观、性能模式、系统托盘、窗口控制和日志高亮。"
      :error="errorMsg()"
      :has-pending="hasPending"
      :pending-count="pendingCount"
      :retrying="false"
      :restoring="false"
      :can-restore-defaults="true"
      @clear-error="onClearError"
      @retry-pending="onRetryPending"
      @restore-defaults="onRestoreDefaults"
    />

    <!-- ── 外观 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>外观</h3>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">主题模式</span>
          <span class="row-help">跟随系统将按操作系统深浅色偏好自动切换。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="界面外观主题">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-select
            :value="themeMode"
            size="middle"
            style="min-width: 160px"
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
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">主题色</span>
          <span class="row-help">macOS accent 颜色，应用于按钮、链接与选中态。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="界面主色调">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-select
            :value="themeColor"
            size="middle"
            style="min-width: 160px"
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
                    width: '14px',
                    height: '14px',
                    borderRadius: '50%',
                    backgroundColor: option.color,
                  }"
                />
                {{ option.label }}
              </div>
            </a-select-option>
          </a-select>
        </div>
      </div>
    </section>

    <!-- ── 性能 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>性能</h3>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">动画与特效模式</span>
          <span class="row-help"> 低性能模式会关闭非必要动画、毛玻璃模糊和装饰特效。 </span>
        </div>
        <div class="row-control">
          <a-tooltip title="自动检测根据 CPU 核心数、内存和系统减少动画偏好决定。">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-select
            :value="perfModeSelectValue"
            size="middle"
            style="min-width: 160px"
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
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">硬件检测</span>
          <span class="row-help">{{ detectionSummary }}</span>
          <span v-if="perfModeSelectValue === 'auto'" class="row-help">
            自动检测结果：
            <strong>{{ detectedPerfMode === 'low' ? '低性能模式' : '标准模式' }}</strong>
          </span>
        </div>
      </div>
    </section>

    <!-- ── 系统托盘 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>系统托盘</h3>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">常态显示托盘图标</span>
          <span class="row-help">即使界面未最小化仍显示系统托盘图标。</span>
        </div>
        <div class="row-control">
          <a-switch
            :checked="eff<boolean>('IfShowTray')"
            :loading="saving('IfShowTray')"
            aria-label="常态显示托盘图标"
            @change="(checked: any) => handleSettingChange('UI', 'IfShowTray', checked)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">最小化到托盘</span>
          <span class="row-help">界面最小化时隐藏到系统托盘。</span>
        </div>
        <div class="row-control">
          <a-switch
            :checked="eff<boolean>('IfToTray')"
            :loading="saving('IfToTray')"
            aria-label="最小化到托盘"
            @change="(checked: any) => handleSettingChange('UI', 'IfToTray', checked)"
          />
        </div>
      </div>
    </section>

    <!-- ── 窗口控制 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>窗口控制</h3>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">隐藏关闭按钮</span>
          <span class="row-help">
            隐藏主窗口右上角的关闭按钮，仍可通过 Alt+F4 或托盘菜单退出。
          </span>
        </div>
        <div class="row-control">
          <a-switch
            :checked="eff<boolean>('IfHideCloseButton')"
            :loading="saving('IfHideCloseButton')"
            aria-label="隐藏关闭按钮"
            @change="(checked: any) => handleSettingChange('UI', 'IfHideCloseButton', checked)"
          />
        </div>
      </div>
    </section>

    <!-- ── 日志样式 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>日志样式</h3>
      </header>
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">日志高亮规则</span>
          <span class="row-help">配置日志面板的高亮关键词与配色。</span>
        </div>
        <div class="row-control row-control-full">
          <LogHighlightSettings />
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.help-icon {
  color: var(--v6-color-text-tertiary);
  font-size: var(--v6-font-size-sm);
}
</style>
