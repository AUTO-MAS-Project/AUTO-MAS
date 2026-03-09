<script setup lang="ts">
import { QuestionCircleOutlined, SyncOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { GlobalConfig } from '@/api'
import WebhookManager from '@/components/WebhookManager.vue'
import { handleExternalLink } from '@/utils/openExternal'

// 生成随机订阅名
const generateRandomTopic = () => {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
  const prefix = 'auto-mas'
  return prefix + Array.from({ length: 8 }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
}

// 处理 Topic 自动生成
const handleGenerateTopic = async () => {
  const randomTopic = generateRandomTopic()
  await handleSettingChange('Notify', 'NtfyTopic', randomTopic)

  try {
    await navigator.clipboard.writeText(randomTopic)
    message.success('已复制随机 Topic')
  } catch {
    message.warning('随机 Topic 已生成，复制失败，请手动复制')
  }
}

const props = defineProps<{
  settings: GlobalConfig
  sendTaskResultTimeOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<void>
  testNotify: () => Promise<void>
  testingNotify: boolean
}>()

const { settings, sendTaskResultTimeOptions, handleSettingChange, testNotify, testingNotify } =
  props

// 处理 Webhook 变化
const handleWebhookChange = async () => {
  // Webhook 变化由 WebhookManager 组件内部处理，这里不需要额外处理
}
</script>

<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>通知内容</h3>
        <a-button type="primary" :loading="testingNotify" size="small" class="section-update-button primary-style"
          @click="testNotify">发送测试通知</a-button>
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
            <a-select :value="settings.Notify?.SendTaskResultTime" :options="sendTaskResultTimeOptions" size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Notify', 'SendTaskResultTime', value)" />
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
            <a-select :value="settings.Notify?.IfSendStatistic" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfSendStatistic', checked)">
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
            <a-select :value="settings.Notify?.IfSendSixStar" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfSendSixStar', checked)">
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
            <a-select :value="settings.Notify?.IfPushPlyer" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfPushPlyer', checked)">
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
        <a href="https://doc.auto-mas.top/docs/advanced-features/notification.html#smtp-%E9%82%AE%E4%BB%B6%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
          class="section-doc-link" title="查看电子邮箱配置文档" @click="handleExternalLink">
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
            <a-select :value="settings.Notify?.IfSendMail" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfSendMail', checked)">
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
            <a-input :value="settings.Notify?.SMTPServerAddress" :disabled="!settings.Notify?.IfSendMail"
              placeholder="请输入发信邮箱SMTP服务器地址" size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'SMTPServerAddress', e.target.value)" />
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
            <a-input :value="settings.Notify?.FromAddress" :disabled="!settings.Notify?.IfSendMail"
              placeholder="请输入发信邮箱地址" size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'FromAddress', e.target.value)" />
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
            <a-input-password :value="settings.Notify?.AuthorizationCode" :disabled="!settings.Notify?.IfSendMail"
              placeholder="请输入发信邮箱授权码" size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'AuthorizationCode', e.target.value)" />
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
            <a-input :value="settings.Notify?.ToAddress" :disabled="!settings.Notify?.IfSendMail"
              placeholder="请输入收信邮箱地址" size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'ToAddress', e.target.value)" />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>Server酱通知</h3>
        <a href="https://doc.auto-mas.top/docs/advanced-features/notification.html#serverchan-%E9%80%9A%E7%9F%A5%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
          class="section-doc-link" title="查看Server酱配置文档" @click="handleExternalLink">
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
            <a-select :value="settings.Notify?.IfServerChan" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfServerChan', checked)">
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
            <a-input :value="settings.Notify?.ServerChanKey" :disabled="!settings.Notify?.IfServerChan"
              placeholder="请输入Server酱SendKey" size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'ServerChanKey', e.target.value)" />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>ntfy通知</h3>
        <a href="https://doc.auto-mas.top/docs/advanced-features/notification.html#ntfy-邮件推送渠道" class="section-doc-link" title="查看ntfy配置文档" @click="handleExternalLink">
          文档
        </a>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用ntfy通知</span>
              <a-tooltip>
                <template #title>
                  <div>使用ntfy推送通知。ntfy是一个开源的自托管通知服务，可在网页或APP上订阅接收推送</div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Notify?.IfNtfy" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfNtfy', checked)">
              <a-select-option :value="true">是</a-select-option>
              <a-select-option :value="false">否</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">ntfy服务器地址</span>
              <a-tooltip>
                <template #title>
                  <div>ntfy服务器地址。使用官方服务请填写 ntfy.sh，自建服务器请填写您的服务器地址</div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input :value="settings.Notify?.NtfyServer" :disabled="!settings.Notify?.IfNtfy"
              placeholder="请输入ntfy服务器地址" size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'NtfyServer', e.target.value)" />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">ntfy Topic</span>
              <a-tooltip>
                <template #title>
                  <div>ntfy Topic名称，用于标识通知主题。请在ntfy客户端（APP/网页）中填写此名称以订阅接收通知</div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input-search
              :value="settings.Notify?.NtfyTopic"
              :disabled="!settings.Notify?.IfNtfy"
              placeholder="请输入ntfy Topic"
              size="large"
              @search="handleGenerateTopic"
              @blur="(e: any) => handleSettingChange('Notify', 'NtfyTopic', e.target.value)"
            >
              <template #enterButton>
                <SyncOutlined />
              </template>
            </a-input-search>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>Koishi通知</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用Koishi通知</span>
              <a-tooltip title="使用Koishi推送通知">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select :value="settings.Notify?.IfKoishiSupport" size="large" style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfKoishiSupport', checked)">
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
              <span class="form-label">Koishi WebSocket 地址</span>
              <a-tooltip title="Koishi WebSocket 服务器地址，支持 ws:// 或 wss:// 协议">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input :value="settings.Notify?.KoishiServerAddress" :disabled="!settings.Notify?.IfKoishiSupport"
              placeholder="ws://localhost:5140/AUTO_MAS" size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'KoishiServerAddress', e.target.value)" />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">Koishi Token</span>
              <a-tooltip title="Koishi的访问令牌">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input-password :value="settings.Notify?.KoishiToken" :disabled="!settings.Notify?.IfKoishiSupport"
              placeholder="请输入Koishi Token" size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'KoishiToken', e.target.value)" />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>自定义 Webhook 通知</h3>
        <a href="https://doc.auto-mas.top/docs/advanced-features/notification.html" class="section-doc-link"
          title="查看自定义Webhook配置文档" @click="handleExternalLink">
          文档
        </a>
      </div>
      <WebhookManager mode="global" @change="handleWebhookChange" />
    </div>

  </div>
</template>

<style scoped>
/* Header layout */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* Doc link and header action parity */
.section-header .section-update-button {
  /* Apply doc-link visual tokens to the local update button only.
     Do NOT touch global .section-doc-link so the real doc button remains unchanged. */
  color: var(--ant-color-primary) !important;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--ant-color-primary);
  transition: all 0.18s ease;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  line-height: 1;
}

.section-header .section-update-button:hover {
  color: var(--ant-color-primary-hover) !important;
  background-color: var(--ant-color-primary-bg);
  border-color: var(--ant-color-primary-hover);
}

/* Primary gradient style for the update button */

.section-header .section-update-button.primary-style {
  /* Keep gradient but match doc-link height/rounded corners for parity */
  height: 32px;
  padding: 4px 8px;
  /* same vertical padding as doc-link */
  font-size: 14px;
  /* same as doc-link for visual parity */
  font-weight: 500;
  border-radius: 4px;
  /* same radius as doc-link */
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.18);
  transition:
    transform 0.16s ease,
    box-shadow 0.16s ease;
  background: linear-gradient(135deg,
      var(--ant-color-primary),
      var(--ant-color-primary-hover)) !important;
  border: 1px solid var(--ant-color-primary) !important;
  /* subtle border to match doc-link rhythm */
  color: #fff !important;
}

.section-header .section-update-button.primary-style:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(22, 119, 255, 0.22);
}

@media (max-width: 640px) {
  .section-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .section-header .section-update-button {
    margin-top: 4px;
  }
}
</style>
