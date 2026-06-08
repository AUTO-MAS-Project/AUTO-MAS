<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import { handleExternalLink } from '@/utils/openExternal'

const {
  settings,
  historyRetentionOptions,
  voiceTypeOptions,
  handleSettingChange,
} = defineProps<{
  settings: GlobalConfig
  historyRetentionOptions: { label: string; value: number }[]
  voiceTypeOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<void>
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
            <a-select :value="settings.Start?.IfSelfStart" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Start', 'IfSelfStart', checked)">
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
            <a-select :value="settings.Start?.IfMinimizeDirectly" size="large" style="width: 100%" @change="
              (checked: any) => handleSettingChange('Start', 'IfMinimizeDirectly', checked)
            ">
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>功能设置</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">历史记录保留时间</span>
              <a-tooltip title="超过该时间的历史记录将被自动清理">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Function?.HistoryRetentionTime" :options="historyRetentionOptions" size="large"
              style="width: 100%" @change="
                (value: any) => handleSettingChange('Function', 'HistoryRetentionTime', value)
              " />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">静默模式</span>
              <a-tooltip title="启用后将各代理窗口置于后台运行，减少对前台的干扰。反馈问题、故障排查时，请关闭此功能以便检查相关窗口情况。">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Function?.IfSilence" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Function', 'IfSilence', checked)">
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">运行时阻止系统休眠</span>
              <a-tooltip title="程序运行时阻止系统进入休眠状态，不影响电脑进入熄屏">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Function?.IfAllowSleep" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Function', 'IfAllowSleep', checked)">
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
              <span class="form-label">托管Bilibili游戏隐私政策</span>
              <a-tooltip>
                <template #title>
                  <div style="max-width: 300px">
                    <p>
                      开启本项即代表您已完整阅读并同意以下协议，并授权本程序在其认定需要时以其认定合适的方法替您处理相关弹窗：
                    </p>
                    <ul style="margin: 8px 0; padding-left: 16px">
                      <li>
                        <a href="https://www.bilibili.com/protocal/licence.html" class="tooltip-link"
                          @click="handleExternalLink">《哔哩哔哩弹幕网用户使用协议》</a>
                      </li>
                      <li>
                        <a href="https://www.bilibili.com/blackboard/privacy-pc.html" class="tooltip-link"
                          @click="handleExternalLink">《哔哩哔哩隐私政策》</a>
                      </li>
                      <li>
                        <a href="https://game.bilibili.com/yhxy" class="tooltip-link"
                          @click="handleExternalLink">《哔哩哔哩游戏中心用户协议》</a>
                      </li>
                    </ul>
                  </div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Function?.IfAgreeBilibili" size="large" style="width: 100%" @change="
              (checked: any) => handleSettingChange('Function', 'IfAgreeBilibili', checked)
            ">
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">屏蔽模拟器广告</span>
              <a-tooltip>
                <template #title>
                  <div style="max-width: 300px">
                    <p>
                      屏蔽部分模拟器广告，支持的广告类型如下：
                    </p>
                    <ul style="margin: 8px 0; padding-left: 16px">
                      <li>
                        <strong>MuMu模拟器</strong>：启动时广告
                      </li>
                      <li>
                        <strong>雷电模拟器</strong>：启动时广告、桌面广告
                      </li>
                    </ul>
                  </div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Function?.IfBlockAd" size="large" style="width: 100%" @change="
              (checked: any) => handleSettingChange('Function', 'IfBlockAd', checked)
            ">
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>语音配置</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用语音提示</span>
              <a-tooltip title="开启后将在特定时刻播放语音提示">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Voice?.Enabled" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Voice', 'Enabled', checked)">
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">语音类型</span>
              <a-tooltip title="选择语音提示的详细程度">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Voice?.Type" :options="voiceTypeOptions" :disabled="!settings.Voice?.Enabled"
              size="large" style="width: 100%" @change="(value: any) => handleSettingChange('Voice', 'Type', value)" />
          </div>
        </a-col>
      </a-row>
    </div>
  </div>
</template>
