<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { SettingsData } from '@/types/settings'

const { settings, historyRetentionOptions, handleSettingChange } = defineProps<{
  settings: SettingsData
  historyRetentionOptions: { label: string; value: number }[]
  handleSettingChange: (category: keyof SettingsData, key: string, value: any) => Promise<void>
}>()
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>功能设置</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">历史记录保留时间</span>
              <a-tooltip title="超过该时间的历史记录将被自动清理">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Function.HistoryRetentionTime"
              @change="(value: any) => handleSettingChange('Function', 'HistoryRetentionTime', value)"
              :options="historyRetentionOptions"
              size="large"
              style="width: 100%"
            />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">运行时阻止系统休眠</span>
              <a-tooltip title="程序运行时阻止系统进入休眠状态，不影响电脑进入熄屏">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Function.IfAllowSleep"
              @change="(checked: any) => handleSettingChange('Function', 'IfAllowSleep', checked)"
              size="large"
              style="width: 100%"
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">静默模式</span>
              <a-tooltip title="将各代理窗口置于后台运行，减少对前台的干扰">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Function.IfSilence"
              @change="(checked: any) => handleSettingChange('Function', 'IfSilence', checked)"
              size="large"
              style="width: 100%"
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">模拟器老板键</span>
              <a-tooltip title="程序依靠模拟器老板键隐藏模拟器窗口，需要开启静默模式后才能填写，请直接输入文字，多个键位之间请用『+』隔开">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              v-model:value="settings.Function.BossKey"
              @blur="handleSettingChange('Function', 'BossKey', settings.Function.BossKey)"
              :disabled="!settings.Function.IfSilence"
              placeholder="请输入对应模拟器老板键，例如: Alt+Q"
              size="large"
            />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">托管Bilibili游戏隐私政策</span>
              <a-tooltip>
                <template #title>
                  <div style="max-width: 300px">
                    <p>开启本项即代表您已完整阅读并同意以下协议，并授权本程序在其认定需要时以其认定合适的方法替您处理相关弹窗：</p>
                    <ul style="margin: 8px 0; padding-left: 16px">
                      <li>
                        <a href="https://www.bilibili.com/protocal/licence.html" target="_blank" class="tooltip-link" @click.stop>《哔哩哔哩弹幕网用户使用协议》</a>
                      </li>
                      <li>
                        <a href="https://www.bilibili.com/blackboard/privacy-pc.html" target="_blank" class="tooltip-link" @click.stop>《哔哩哔哩隐私政策》</a>
                      </li>
                      <li>
                        <a href="https://game.bilibili.com/yhxy" target="_blank" class="tooltip-link" @click.stop>《哔哩哔哩游戏中心用户协议》</a>
                      </li>
                    </ul>
                  </div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Function.IfAgreeBilibili"
              @change="(checked: any) => handleSettingChange('Function', 'IfAgreeBilibili', checked)"
              size="large"
              style="width: 100%"
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">屏蔽MuMu启动广告</span>
              <a-tooltip title="MuMu模拟器启动时屏蔽启动广告">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Function.IfSkipMumuSplashAds"
              @change="(checked: any) => handleSettingChange('Function', 'IfSkipMumuSplashAds', checked)"
              size="large"
              style="width: 100%"
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
