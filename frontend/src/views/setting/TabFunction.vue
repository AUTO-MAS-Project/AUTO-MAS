<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import { handleExternalLink } from '@/utils/openExternal'
import SettingTabHeader from './SettingTabHeader.vue'
import type { SettingsCategory } from '@/composables/useSettingsFormGuard'

const {
  settings,
  historyRetentionOptions,
  voiceTypeOptions,
  handleSettingChange,
  getEffectiveValue,
  getAggregateState,
  clearErrorsForCategories,
  retryPendingForCategories,
  restoreDefaultsForCategories,
  isSaving,
} = defineProps<{
  settings: GlobalConfig
  historyRetentionOptions: { label: string; value: number }[]
  voiceTypeOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
  /** Lane 8：多 category 聚合 */
  getEffectiveValue: <T>(
    settings: GlobalConfig,
    category: SettingsCategory,
    key: string
  ) => T | undefined
  getAggregateState: (categories: SettingsCategory[]) => {
    error: string | null
    pendingCountForCategories: number
    hasPendingForCategories: boolean
  }
  clearErrorsForCategories: (categories: SettingsCategory[]) => void
  retryPendingForCategories: (categories: SettingsCategory[]) => Promise<void>
  revertField: (category: SettingsCategory, key: string) => void
  restoreDefaultsForCategories: (categories: SettingsCategory[]) => Promise<void>
  isSaving: (category: SettingsCategory, key: string) => boolean
}>()

// Lane 8：TabFunction 涉及 Start / Function / Voice 三个 category
const CATEGORIES: SettingsCategory[] = ['Start', 'Function', 'Voice']

const aggregateState = () => getAggregateState(CATEGORIES)
const errorMsg = (): string | null => aggregateState().error
const pendingCountForTab = (): number => aggregateState().pendingCountForCategories
const hasPendingForTab = (): boolean => aggregateState().hasPendingForCategories
const onClearError = (): void => clearErrorsForCategories(CATEGORIES)
const onRetryPending = (): Promise<void> => retryPendingForCategories(CATEGORIES)
const onRestoreDefaults = (): Promise<void> => restoreDefaultsForCategories(CATEGORIES)

// 各 category 辅助
const eff = <T,>(category: SettingsCategory, key: string): T | undefined =>
  getEffectiveValue<T>(settings, category, key)
const saving = (category: SettingsCategory, key: string): boolean => isSaving(category, key)
</script>

<template>
  <div class="tab-content">
    <!-- 统一 Tab 状态条：说明、错误、恢复默认和重试 -->
    <SettingTabHeader
      description="配置启动行为、运行时功能、Bilibili 隐私、广告屏蔽和语音提示。"
      :error="errorMsg()"
      :has-pending="hasPendingForTab()"
      :pending-count="pendingCountForTab()"
      :retrying="false"
      :restoring="false"
      :can-restore-defaults="true"
      @clear-error="onClearError"
      @retry-pending="onRetryPending"
      @restore-defaults="onRestoreDefaults"
    />

    <!-- ── 启动 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>启动</h3>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">开机自启</span>
          <span class="row-help">在系统启动时自动启动应用。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="在系统启动时自动启动应用">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('Start', 'IfSelfStart')"
            :loading="saving('Start', 'IfSelfStart')"
            aria-label="开机自启"
            @change="(checked: any) => handleSettingChange('Start', 'IfSelfStart', checked)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">启动后直接最小化</span>
          <span class="row-help">启动后自动最小化到托盘，不弹出主窗口。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="启动后直接最小化">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('Start', 'IfMinimizeDirectly')"
            :loading="saving('Start', 'IfMinimizeDirectly')"
            aria-label="启动后直接最小化"
            @change="(checked: any) => handleSettingChange('Start', 'IfMinimizeDirectly', checked)"
          />
        </div>
      </div>
    </section>

    <!-- ── 功能 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>功能</h3>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">历史记录保留时间</span>
          <span class="row-help">超过该时间的历史记录将被自动清理。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="超过该时间的历史记录将被自动清理">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-select
            :value="eff<number>('Function', 'HistoryRetentionTime')"
            :options="historyRetentionOptions"
            size="middle"
            style="min-width: 160px"
            :loading="saving('Function', 'HistoryRetentionTime')"
            @change="(value: any) => handleSettingChange('Function', 'HistoryRetentionTime', value)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">静默模式</span>
          <span class="row-help"> 启用后将各代理窗口置于后台运行。故障排查时请关闭此功能。 </span>
        </div>
        <div class="row-control">
          <a-tooltip
            title="启用后将各代理窗口置于后台运行，减少对前台的干扰。反馈问题、故障排查时，请关闭此功能以便检查相关窗口情况。"
          >
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('Function', 'IfSilence')"
            :loading="saving('Function', 'IfSilence')"
            aria-label="静默模式"
            @change="(checked: any) => handleSettingChange('Function', 'IfSilence', checked)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">运行时阻止系统休眠</span>
          <span class="row-help">程序运行时阻止系统进入休眠状态，不影响电脑熄屏。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="程序运行时阻止系统进入休眠状态，不影响电脑进入熄屏">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('Function', 'IfAllowSleep')"
            :loading="saving('Function', 'IfAllowSleep')"
            aria-label="运行时阻止系统休眠"
            @change="(checked: any) => handleSettingChange('Function', 'IfAllowSleep', checked)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">托管 Bilibili 游戏隐私政策</span>
          <span class="row-help">
            开启即代表您已阅读并同意以下协议，授权本程序替您处理相关弹窗。
          </span>
        </div>
        <div class="row-control">
          <a-tooltip>
            <template #title>
              <div style="max-width: 300px">
                <p>
                  开启本项即代表您已完整阅读并同意以下协议，并授权本程序在其认定需要时以其认定合适的方法替您处理相关弹窗：
                </p>
                <ul style="margin: 8px 0; padding-left: 16px">
                  <li>
                    <a
                      href="https://www.bilibili.com/protocal/licence.html"
                      class="tooltip-link"
                      @click="handleExternalLink"
                      >《哔哩哔哩弹幕网用户使用协议》</a
                    >
                  </li>
                  <li>
                    <a
                      href="https://www.bilibili.com/blackboard/privacy-pc.html"
                      class="tooltip-link"
                      @click="handleExternalLink"
                      >《哔哩哔哩隐私政策》</a
                    >
                  </li>
                  <li>
                    <a
                      href="https://game.bilibili.com/yhxy"
                      class="tooltip-link"
                      @click="handleExternalLink"
                      >《哔哩哔哩游戏中心用户协议》</a
                    >
                  </li>
                </ul>
              </div>
            </template>
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('Function', 'IfAgreeBilibili')"
            :loading="saving('Function', 'IfAgreeBilibili')"
            aria-label="托管 Bilibili 游戏隐私政策"
            @change="(checked: any) => handleSettingChange('Function', 'IfAgreeBilibili', checked)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">屏蔽模拟器广告</span>
          <span class="row-help"> 支持 MuMu 启动时广告、雷电启动时广告与桌面广告。 </span>
        </div>
        <div class="row-control">
          <a-tooltip>
            <template #title>
              <div style="max-width: 300px">
                <p>屏蔽部分模拟器广告，支持的广告类型如下：</p>
                <ul style="margin: 8px 0; padding-left: 16px">
                  <li><strong>MuMu模拟器</strong>：启动时广告</li>
                  <li><strong>雷电模拟器</strong>：启动时广告、桌面广告</li>
                </ul>
              </div>
            </template>
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('Function', 'IfBlockAd')"
            :loading="saving('Function', 'IfBlockAd')"
            aria-label="屏蔽模拟器广告"
            @change="(checked: any) => handleSettingChange('Function', 'IfBlockAd', checked)"
          />
        </div>
      </div>
    </section>

    <!-- ── 语音 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>语音</h3>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">启用语音提示</span>
          <span class="row-help">开启后将在特定时刻播放语音提示。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="开启后将在特定时刻播放语音提示">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('Voice', 'Enabled')"
            :loading="saving('Voice', 'Enabled')"
            aria-label="启用语音提示"
            @change="(checked: any) => handleSettingChange('Voice', 'Enabled', checked)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">语音类型</span>
          <span class="row-help">选择语音提示的详细程度。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="选择语音提示的详细程度">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-select
            :value="eff<string>('Voice', 'Type')"
            :options="voiceTypeOptions"
            :disabled="!eff<boolean>('Voice', 'Enabled')"
            size="middle"
            style="min-width: 160px"
            :loading="saving('Voice', 'Type')"
            @change="(value: any) => handleSettingChange('Voice', 'Type', value)"
          />
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
