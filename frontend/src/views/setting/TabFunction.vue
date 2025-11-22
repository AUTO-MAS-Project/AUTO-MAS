<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { SettingsData } from '@/types/settings'

const {
  settings,
  historyRetentionOptions,
  updateSourceOptions,
  updateChannelOptions,
  voiceTypeOptions,
  handleSettingChange,
  checkUpdate,
} = defineProps<{
  settings: SettingsData
  historyRetentionOptions: { label: string; value: number }[]
  updateSourceOptions: { label: string; value: string }[]
  updateChannelOptions: { label: string; value: string }[]
  voiceTypeOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof SettingsData, key: string, value: any) => Promise<void>
  checkUpdate: () => Promise<void>
}>()
</script>
<template>
  <div class="tab-content">
    <!-- 启动设置 - 移到最上方 -->
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
            <a-select
              v-model:value="settings.Start.IfSelfStart"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Start', 'IfSelfStart', checked)"
            >
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
            <a-select
              v-model:value="settings.Start.IfMinimizeDirectly"
              size="large"
              style="width: 100%"
              @change="
                (checked: any) => handleSettingChange('Start', 'IfMinimizeDirectly', checked)
              "
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <!-- 原有的功能设置 -->
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
            <a-select
              v-model:value="settings.Function.HistoryRetentionTime"
              :options="historyRetentionOptions"
              size="large"
              style="width: 100%"
              @change="
                (value: any) => handleSettingChange('Function', 'HistoryRetentionTime', value)
              "
            />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">静默模式</span>
              <a-tooltip title="将各代理窗口置于后台运行，减少对前台的干扰">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Function.IfSilence"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Function', 'IfSilence', checked)"
            >
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
            <a-select
              v-model:value="settings.Function.IfAllowSleep"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Function', 'IfAllowSleep', checked)"
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
              <span class="form-label">托管Bilibili游戏隐私政策</span>
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
                          target="_blank"
                          class="tooltip-link"
                          @click.stop
                          >《哔哩哔哩弹幕网用户使用协议》</a
                        >
                      </li>
                      <li>
                        <a
                          href="https://www.bilibili.com/blackboard/privacy-pc.html"
                          target="_blank"
                          class="tooltip-link"
                          @click.stop
                          >《哔哩哔哩隐私政策》</a
                        >
                      </li>
                      <li>
                        <a
                          href="https://game.bilibili.com/yhxy"
                          target="_blank"
                          class="tooltip-link"
                          @click.stop
                          >《哔哩哔哩游戏中心用户协议》</a
                        >
                      </li>
                    </ul>
                  </div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Function.IfAgreeBilibili"
              size="large"
              style="width: 100%"
              @change="
                (checked: any) => handleSettingChange('Function', 'IfAgreeBilibili', checked)
              "
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
              size="large"
              style="width: 100%"
              @change="
                (checked: any) => handleSettingChange('Function', 'IfSkipMumuSplashAds', checked)
              "
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <!-- 更新设置 - 移到最下方 -->
    <div class="form-section">
      <div class="section-header">
        <h3>更新配置</h3>
        <a-button type="primary" size="small" class="section-update-button" @click="checkUpdate">
          <template #icon>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path
                d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"
              />
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
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Update', 'IfAutoUpdate', checked)"
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
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
              :options="updateSourceOptions"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Update', 'Source', value)"
            />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">更新渠道</span>
              <a-tooltip title="稳定版：BUG 较少，无法第一时间体验新功能；公测版：包含最新功能，但可能存在较多 BUG">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Update.Channel"
              :options="updateChannelOptions"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Update', 'Channel', value)"
            />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">网络代理地址</span>
              <a-tooltip
                title="使用网络代理软件时，若出现网络连接问题，请尝试设置代理地址，此设置全局生效"
              >
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              v-model:value="settings.Update.ProxyAddress"
              placeholder="请输入网络代理地址"
              size="large"
              @blur="handleSettingChange('Update', 'ProxyAddress', settings.Update.ProxyAddress)"
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
                    <a
                      href="https://mirrorchyan.com/zh/get-start?source=auto-mas-setting"
                      target="_blank"
                      class="tooltip-link"
                      @click.stop
                      >Mirror酱官网</a
                    >
                    获取
                  </div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input-password
              v-model:value="settings.Update.MirrorChyanCDK"
              :disabled="settings.Update.Source !== 'MirrorChyan'"
              placeholder="使用Mirror源时请输入Mirror酱CDK"
              :visibility-toggle="true"
              size="large"
              @blur="
                handleSettingChange('Update', 'MirrorChyanCDK', settings.Update.MirrorChyanCDK)
              "
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <!-- 语音设置 - 移到最下方 -->
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
            <a-select
              v-model:value="settings.Voice.Enabled"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Voice', 'Enabled', checked)"
            >
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
            <a-select
              v-model:value="settings.Voice.Type"
              :options="voiceTypeOptions"
              :disabled="!settings.Voice.Enabled"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Voice', 'Type', value)"
            />
          </div>
        </a-col>
      </a-row>
    </div>
  </div>
</template>
