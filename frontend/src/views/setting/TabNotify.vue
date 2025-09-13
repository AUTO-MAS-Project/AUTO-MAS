<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { SettingsData } from '@/types/settings'

const { settings, sendTaskResultTimeOptions, handleSettingChange, testNotify, testingNotify } = defineProps<{
  settings: SettingsData
  sendTaskResultTimeOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof SettingsData, key: string, value: any) => Promise<void>
  testNotify: () => Promise<void>
  testingNotify: boolean
}>()
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>通知内容</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">推送任务结果时机</span>
              <a-tooltip title="在选定的时机推送任务执行结果">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Notify.SendTaskResultTime"
              @change="(value: any) => handleSettingChange('Notify', 'SendTaskResultTime', value)"
              :options="sendTaskResultTimeOptions"
              size="large"
              style="width: 100%"
            />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">推送统计信息</span>
              <a-tooltip title="推送自动代理统计信息的通知">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Notify.IfSendStatistic"
              @change="(checked: any) => handleSettingChange('Notify', 'IfSendStatistic', checked)"
              size="large"
              style="width: 100%"
            >
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">推送公招高资喜报</span>
              <a-tooltip title="公招出现『高级资深干员』词条时推送喜报">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Notify.IfSendSixStar"
              @change="(checked: any) => handleSettingChange('Notify', 'IfSendSixStar', checked)"
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

    <div class="form-section">
      <div class="section-header">
        <h3>系统通知</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用系统通知</span>
              <a-tooltip title="使用plyer推送系统级通知，不会在通知中心停留">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Notify.IfPushPlyer"
              @change="(checked: any) => handleSettingChange('Notify', 'IfPushPlyer', checked)"
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

    <div class="form-section">
      <div class="section-header">
        <h3>邮件通知</h3>
        <a
          href="https://doc.auto-mas.top/docs/advanced-features.html#smtp-%E9%82%AE%E4%BB%B6%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
          target="_blank"
          class="section-doc-link"
          title="查看电子邮箱配置文档"
        >
          文档
        </a>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用邮件通知</span>
              <a-tooltip title="使用电子邮件推送通知">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Notify.IfSendMail"
              @change="(checked: any) => handleSettingChange('Notify', 'IfSendMail', checked)"
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
              <span class="form-label">SMTP服务器地址</span>
              <a-tooltip title="发信邮箱的SMTP服务器地址">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              v-model:value="settings.Notify.SMTPServerAddress"
              @blur="handleSettingChange('Notify', 'SMTPServerAddress', settings.Notify.SMTPServerAddress)"
              :disabled="!settings.Notify.IfSendMail"
              placeholder="请输入发信邮箱SMTP服务器地址"
              size="large"
            />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">发信邮箱地址</span>
              <a-tooltip title="发送通知的邮箱地址">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              v-model:value="settings.Notify.FromAddress"
              @blur="handleSettingChange('Notify', 'FromAddress', settings.Notify.FromAddress)"
              :disabled="!settings.Notify.IfSendMail"
              placeholder="请输入发信邮箱地址"
              size="large"
            />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">发信邮箱授权码</span>
              <a-tooltip title="用于替代您的邮箱密码进行第三方客户端登录的一种特殊密码">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input-password
              v-model:value="settings.Notify.AuthorizationCode"
              @blur="handleSettingChange('Notify', 'AuthorizationCode', settings.Notify.AuthorizationCode)"
              :disabled="!settings.Notify.IfSendMail"
              placeholder="请输入发信邮箱授权码"
              size="large"
            />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">收信邮箱地址</span>
              <a-tooltip title="接收邮件的邮箱地址">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              v-model:value="settings.Notify.ToAddress"
              @blur="handleSettingChange('Notify', 'ToAddress', settings.Notify.ToAddress)"
              :disabled="!settings.Notify.IfSendMail"
              placeholder="请输入收信邮箱地址"
              size="large"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>Server酱通知</h3>
        <a
          href="https://doc.auto-mas.top/docs/advanced-features.html#serverchan-%E9%80%9A%E7%9F%A5%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
          target="_blank"
          class="section-doc-link"
          title="查看Server酱配置文档"
        >
          文档
        </a>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用Server酱通知</span>
              <a-tooltip>
                <template #title>
                  <div>使用Server酱推送通知</div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Notify.IfServerChan"
              @change="(checked: any) => handleSettingChange('Notify', 'IfServerChan', checked)"
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
              <span class="form-label">Server酱Key</span>
              <a-tooltip>
                <template #title>
                  <div>Server酱的SendKey，请自行查看文档以获取</div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              v-model:value="settings.Notify.ServerChanKey"
              @blur="handleSettingChange('Notify', 'ServerChanKey', settings.Notify.ServerChanKey)"
              :disabled="!settings.Notify.IfServerChan"
              placeholder="请输入Server酱SendKey"
              size="large"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>企业微信机器人通知</h3>
        <a
          href="https://doc.auto-mas.top/docs/advanced-features.html#%E4%BC%81%E4%B8%9A%E5%BE%AE%E4%BF%A1%E7%BE%A4%E6%9C%BA%E5%99%A8%E4%BA%BA%E9%80%9A%E7%9F%A5%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
          target="_blank"
          class="section-doc-link"
          title="查看企业微信机器人配置文档"
        >
          文档
        </a>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用企业微信机器人通知</span>
              <a-tooltip title="使用企业微信机器人推送通知">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              v-model:value="settings.Notify.IfCompanyWebHookBot"
              @change="(checked: any) => handleSettingChange('Notify', 'IfCompanyWebHookBot', checked)"
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
              <span class="form-label">Webhook URL</span>
              <a-tooltip title="企业微信机器人的Webhook地址">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              v-model:value="settings.Notify.CompanyWebHookBotUrl"
              @blur="handleSettingChange('Notify', 'CompanyWebHookBotUrl', settings.Notify.CompanyWebHookBotUrl)"
              :disabled="!settings.Notify.IfCompanyWebHookBot"
              placeholder="请输入Webhook URL"
              size="large"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>通知测试</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="24">
          <a-space>
            <a-button type="primary" :loading="testingNotify" @click="testNotify">发送测试通知</a-button>
          </a-space>
        </a-col>
      </a-row>
    </div>
  </div>
</template>
