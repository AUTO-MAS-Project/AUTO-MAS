<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { SettingsData } from '@/types/settings'
import WebhookManager from '@/components/WebhookManager.vue'

const props = defineProps<{
  settings: SettingsData
  sendTaskResultTimeOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof SettingsData, key: string, value: any) => Promise<void>
  testNotify: () => Promise<void>
  testingNotify: boolean
}>()

const { settings, sendTaskResultTimeOptions, handleSettingChange, testNotify, testingNotify } = props

// 处理 Webhook 变化
const handleWebhookChange = async () => {
  await handleSettingChange('Notify', 'CustomWebhooks', settings.Notify.CustomWebhooks)
}
</script>

<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>通知内容</h3>
        <a-button type="primary" :loading="testingNotify" @click="testNotify" size="small" class="section-update-button primary-style">发送测试通知</a-button>
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
        <h3>自定义 Webhook 通知</h3>
        <a
          href="https://doc.auto-mas.top/docs/advanced-features.html#%E8%87%AA%E5%AE%9A%E4%B9%89webhook%E9%80%9A%E7%9F%A5"
          target="_blank"
          class="section-doc-link"
          title="查看自定义Webhook配置文档"
        >
          文档
        </a>
      </div>
      <WebhookManager 
        mode="global"
        @change="handleWebhookChange"
      />
    </div>

    <!-- 测试按钮已移至“通知内容”标题右侧 -->
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
  padding: 4px 8px; /* same vertical padding as doc-link */
  font-size: 14px; /* same as doc-link for visual parity */
  font-weight: 500;
  border-radius: 4px; /* same radius as doc-link */
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.18);
  transition: transform 0.16s ease, box-shadow 0.16s ease;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover)) !important;
  border: 1px solid var(--ant-color-primary) !important; /* subtle border to match doc-link rhythm */
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

