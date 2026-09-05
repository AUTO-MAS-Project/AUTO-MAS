<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import QqBinding from './components/QqBinding.vue'
import WeixinBinding from './components/WeixinBinding.vue'
import WebhookManager from '@/components/WebhookManager.vue'
import { handleExternalLink } from '@/utils/openExternal'

const { t } = useI18n()

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
        <h3>{{ t('setting.notify.contentSection') }}</h3>
        <a-button
          type="primary"
          :loading="testingNotify"
          size="small"
          class="section-update-button primary-style"
          @click="testNotify"
          >{{ t('setting.notify.sendTest') }}</a-button
        >
      </div>
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.resultTime') }}</span>
              <a-tooltip :title="t('setting.notify.resultTimeTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Notify?.SendTaskResultTime"
              :options="sendTaskResultTimeOptions"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Notify', 'SendTaskResultTime', value)"
            />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.statistics') }}</span>
              <a-tooltip :title="t('setting.notify.statisticsTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Notify?.IfSendStatistic"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfSendStatistic', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.recruit') }}</span>
              <a-tooltip :title="t('setting.notify.recruitTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Notify?.IfSendSixStar"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfSendSixStar', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.notify.systemSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.systemEnable') }}</span>
              <a-tooltip :title="t('setting.notify.systemTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Notify?.IfPushPlyer"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfPushPlyer', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.notify.mailSection') }}</h3>
        <a
          href="https://doc.auto-mas.top/docs/advanced-features/notification.html#smtp-%E9%82%AE%E4%BB%B6%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
          class="section-doc-link"
          :title="t('setting.notify.mailDoc')"
          @click="handleExternalLink"
        >
          {{ t('common.doc') }}
        </a>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.mailEnable') }}</span>
              <a-tooltip :title="t('setting.notify.mailEnableTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Notify?.IfSendMail"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfSendMail', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.smtp') }}</span>
              <a-tooltip :title="t('setting.notify.smtpTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="settings.Notify?.SMTPServerAddress"
              :disabled="!settings.Notify?.IfSendMail"
              :placeholder="t('setting.notify.smtpPlaceholder')"
              size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'SMTPServerAddress', e.target.value)"
            />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.from') }}</span>
              <a-tooltip :title="t('setting.notify.fromTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="settings.Notify?.FromAddress"
              :disabled="!settings.Notify?.IfSendMail"
              :placeholder="t('setting.notify.fromPlaceholder')"
              size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'FromAddress', e.target.value)"
            />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.authCode') }}</span>
              <a-tooltip :title="t('setting.notify.authCodeTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input-password
              :value="settings.Notify?.AuthorizationCode"
              :disabled="!settings.Notify?.IfSendMail"
              :placeholder="t('setting.notify.authCodePlaceholder')"
              size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'AuthorizationCode', e.target.value)"
            />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.to') }}</span>
              <a-tooltip :title="t('setting.notify.toTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="settings.Notify?.ToAddress"
              :disabled="!settings.Notify?.IfSendMail"
              :placeholder="t('setting.notify.toPlaceholder')"
              size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'ToAddress', e.target.value)"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.notify.serverChanSection') }}</h3>
        <a
          href="https://doc.auto-mas.top/docs/advanced-features/notification.html#serverchan-%E9%80%9A%E7%9F%A5%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
          class="section-doc-link"
          :title="t('setting.notify.serverChanDoc')"
          @click="handleExternalLink"
        >
          {{ t('common.doc') }}
        </a>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.serverChanEnable') }}</span>
              <a-tooltip>
                <template #title>
                  <div>{{ t('setting.notify.serverChanTip') }}</div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Notify?.IfServerChan"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfServerChan', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.serverChanKey') }}</span>
              <a-tooltip>
                <template #title>
                  <div>{{ t('setting.notify.serverChanKeyTip') }}</div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="settings.Notify?.ServerChanKey"
              :disabled="!settings.Notify?.IfServerChan"
              :placeholder="t('setting.notify.serverChanPlaceholder')"
              size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'ServerChanKey', e.target.value)"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.notify.koishiSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.koishiEnable') }}</span>
              <a-tooltip :title="t('setting.notify.koishiTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Notify?.IfKoishiSupport"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Notify', 'IfKoishiSupport', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.notify.koishiWs') }}</span>
              <a-tooltip :title="t('setting.notify.koishiWsTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="settings.Notify?.KoishiServerAddress"
              :disabled="!settings.Notify?.IfKoishiSupport"
              placeholder="ws://localhost:5140/AUTO_MAS"
              size="large"
              @blur="
                (e: any) => handleSettingChange('Notify', 'KoishiServerAddress', e.target.value)
              "
            />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">Koishi Token</span>
              <a-tooltip :title="t('setting.notify.koishiTokenTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input-password
              :value="settings.Notify?.KoishiToken"
              :disabled="!settings.Notify?.IfKoishiSupport"
              :placeholder="t('setting.notify.koishiTokenPlaceholder')"
              size="large"
              @blur="(e: any) => handleSettingChange('Notify', 'KoishiToken', e.target.value)"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.notify.openclawWeixinSection') }}</h3>
        <a
          href="https://github.com/Tencent/openclaw-weixin"
          class="section-doc-link"
          :title="t('setting.notify.openclawWeixinDoc')"
          @click="handleExternalLink"
        >
          {{ t('common.doc') }}
        </a>
      </div>
      <WeixinBinding
        :enabled="!!settings.Notify?.IfOpenClawWeixin"
        :on-change="value => handleSettingChange('Notify', 'IfOpenClawWeixin', value)"
      />
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.notify.openclawQqSection') }}</h3>
        <a
          href="https://bot.q.qq.com/wiki/"
          class="section-doc-link"
          :title="t('setting.notify.openclawQqDoc')"
          @click="handleExternalLink"
        >
          {{ t('common.doc') }}
        </a>
      </div>
      <QqBinding
        :enabled="!!settings.Notify?.IfOpenClawQQ"
        :on-change="value => handleSettingChange('Notify', 'IfOpenClawQQ', value)"
      />
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.notify.webhookSection') }}</h3>
        <a
          href="https://doc.auto-mas.top/docs/advanced-features/notification.html"
          class="section-doc-link"
          :title="t('setting.notify.webhookDoc')"
          @click="handleExternalLink"
        >
          {{ t('common.doc') }}
        </a>
      </div>
      <WebhookManager mode="global" @change="handleWebhookChange" />
    </div>
  </div>
</template>

<style scoped>
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
  background: linear-gradient(
    135deg,
    var(--ant-color-primary),
    var(--ant-color-primary-hover)
  ) !important;
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
