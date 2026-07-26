<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import WebhookManager from '@/components/WebhookManager.vue'
import { handleExternalLink } from '@/utils/openExternal'
import SettingTabHeader from './SettingTabHeader.vue'
import type { SettingsCategory } from '@/composables/useSettingsFormGuard'

const {
  settings,
  sendTaskResultTimeOptions,
  handleSettingChange,
  testNotify,
  testingNotify,
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
  sendTaskResultTimeOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
  testNotify: () => Promise<void>
  testingNotify: boolean
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

const CATEGORY: SettingsCategory = 'Notify'

// 处理 Webhook 变化
const handleWebhookChange = async () => {
  // Webhook 变化由 WebhookManager 组件内部处理，这里不需要额外处理
}

// Lane 8：辅助函数，读取 effective value
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
      description="配置任务结果推送、系统通知、邮件、Server酱、Koishi 和自定义 Webhook 通知渠道。"
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

    <!-- ── 通知内容 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>通知内容</h3>
        <a-button
          type="primary"
          :loading="testingNotify"
          size="small"
          class="section-update-button"
          @click="testNotify"
        >
          发送测试通知
        </a-button>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">推送任务结果时机</span>
          <span class="row-help">在选定的时机推送任务执行结果。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="在选定的时机推送任务执行结果">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-select
            :value="eff<string>('SendTaskResultTime')"
            :options="sendTaskResultTimeOptions"
            size="middle"
            style="min-width: 160px"
            :loading="saving('SendTaskResultTime')"
            @change="(value: any) => handleSettingChange('Notify', 'SendTaskResultTime', value)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">推送统计信息</span>
          <span class="row-help">推送自动代理统计信息的通知。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="推送自动代理统计信息的通知">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('IfSendStatistic')"
            :loading="saving('IfSendStatistic')"
            aria-label="推送统计信息"
            @change="(checked: any) => handleSettingChange('Notify', 'IfSendStatistic', checked)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">推送公招高资喜报</span>
          <span class="row-help">公招出现『高级资深干员』词条时推送喜报。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="公招出现『高级资深干员』词条时推送喜报">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('IfSendSixStar')"
            :loading="saving('IfSendSixStar')"
            aria-label="推送公招高资喜报"
            @change="(checked: any) => handleSettingChange('Notify', 'IfSendSixStar', checked)"
          />
        </div>
      </div>
    </section>

    <!-- ── 系统通知 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>系统通知</h3>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">启用系统通知</span>
          <span class="row-help">使用 plyer 推送系统级通知，不会在通知中心停留。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="使用plyer推送系统级通知，不会在通知中心停留">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('IfPushPlyer')"
            :loading="saving('IfPushPlyer')"
            aria-label="启用系统通知"
            @change="(checked: any) => handleSettingChange('Notify', 'IfPushPlyer', checked)"
          />
        </div>
      </div>
    </section>

    <!-- ── 邮件通知 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>邮件通知</h3>
        <a
          href="https://doc.auto-mas.top/docs/advanced-features/notification.html#smtp-%E9%82%AE%E4%BB%B6%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
          class="section-doc-link"
          title="查看电子邮箱配置文档"
          @click="handleExternalLink"
        >
          文档
        </a>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">启用邮件通知</span>
          <span class="row-help">使用电子邮件推送通知。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="使用电子邮件推送通知">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('IfSendMail')"
            :loading="saving('IfSendMail')"
            aria-label="启用邮件通知"
            @change="(checked: any) => handleSettingChange('Notify', 'IfSendMail', checked)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">SMTP 服务器地址</span>
          <span class="row-help">发信邮箱的 SMTP 服务器地址。</span>
        </div>
        <div class="row-control row-control-full">
          <a-input
            :value="eff<string>('SMTPServerAddress')"
            :disabled="!eff<boolean>('IfSendMail')"
            placeholder="请输入发信邮箱 SMTP 服务器地址"
            size="middle"
            @blur="(e: any) => handleSettingChange('Notify', 'SMTPServerAddress', e.target.value)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">发信邮箱地址</span>
          <span class="row-help">发送通知的邮箱地址。</span>
        </div>
        <div class="row-control row-control-full">
          <a-input
            :value="eff<string>('FromAddress')"
            :disabled="!eff<boolean>('IfSendMail')"
            placeholder="请输入发信邮箱地址"
            size="middle"
            @blur="(e: any) => handleSettingChange('Notify', 'FromAddress', e.target.value)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">发信邮箱授权码</span>
          <span class="row-help">用于替代您的邮箱密码进行第三方客户端登录的一种特殊密码。</span>
        </div>
        <div class="row-control row-control-full">
          <!-- Lane 8：敏感字段使用 a-input-password，明文不直接显示；保存失败时保留输入 -->
          <a-input-password
            :value="eff<string>('AuthorizationCode')"
            :disabled="!eff<boolean>('IfSendMail')"
            placeholder="请输入发信邮箱授权码"
            size="middle"
            @blur="(e: any) => handleSettingChange('Notify', 'AuthorizationCode', e.target.value)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">收信邮箱地址</span>
          <span class="row-help">接收邮件的邮箱地址。</span>
        </div>
        <div class="row-control row-control-full">
          <a-input
            :value="eff<string>('ToAddress')"
            :disabled="!eff<boolean>('IfSendMail')"
            placeholder="请输入收信邮箱地址"
            size="middle"
            @blur="(e: any) => handleSettingChange('Notify', 'ToAddress', e.target.value)"
          />
        </div>
      </div>
    </section>

    <!-- ── Server酱通知 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>Server酱通知</h3>
        <a
          href="https://doc.auto-mas.top/docs/advanced-features/notification.html#serverchan-%E9%80%9A%E7%9F%A5%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
          class="section-doc-link"
          title="查看Server酱配置文档"
          @click="handleExternalLink"
        >
          文档
        </a>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">启用 Server酱 通知</span>
          <span class="row-help">使用 Server酱 推送通知。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="使用Server酱推送通知">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('IfServerChan')"
            :loading="saving('IfServerChan')"
            aria-label="启用 Server酱 通知"
            @change="(checked: any) => handleSettingChange('Notify', 'IfServerChan', checked)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">Server酱 Key</span>
          <span class="row-help">Server酱的 SendKey，请自行查看文档以获取。</span>
        </div>
        <div class="row-control row-control-full">
          <!-- Lane 8：ServerChanKey 为敏感字段，使用 password 类型输入 -->
          <a-input-password
            :value="eff<string>('ServerChanKey')"
            :disabled="!eff<boolean>('IfServerChan')"
            placeholder="请输入Server酱 SendKey"
            size="middle"
            @blur="(e: any) => handleSettingChange('Notify', 'ServerChanKey', e.target.value)"
          />
        </div>
      </div>
    </section>

    <!-- ── Koishi通知 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>Koishi 通知</h3>
      </header>
      <div class="setting-row">
        <div class="row-label">
          <span class="row-title">启用 Koishi 通知</span>
          <span class="row-help">使用 Koishi 推送通知。</span>
        </div>
        <div class="row-control">
          <a-tooltip title="使用Koishi推送通知">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
          <a-switch
            :checked="eff<boolean>('IfKoishiSupport')"
            :loading="saving('IfKoishiSupport')"
            aria-label="启用 Koishi 通知"
            @change="(checked: any) => handleSettingChange('Notify', 'IfKoishiSupport', checked)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">Koishi WebSocket 地址</span>
          <span class="row-help">Koishi WebSocket 服务器地址，支持 ws:// 或 wss:// 协议。</span>
        </div>
        <div class="row-control row-control-full">
          <a-input
            :value="eff<string>('KoishiServerAddress')"
            :disabled="!eff<boolean>('IfKoishiSupport')"
            placeholder="ws://localhost:5140/AUTO_MAS"
            size="middle"
            @blur="(e: any) => handleSettingChange('Notify', 'KoishiServerAddress', e.target.value)"
          />
        </div>
      </div>
      <div class="row-separator" />
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">Koishi Token</span>
          <span class="row-help">Koishi 的访问令牌。</span>
        </div>
        <div class="row-control row-control-full">
          <!-- Lane 8：KoishiToken 为敏感字段，使用 password 类型输入 -->
          <a-input-password
            :value="eff<string>('KoishiToken')"
            :disabled="!eff<boolean>('IfKoishiSupport')"
            placeholder="请输入 Koishi Token"
            size="middle"
            @blur="(e: any) => handleSettingChange('Notify', 'KoishiToken', e.target.value)"
          />
        </div>
      </div>
    </section>

    <!-- ── 自定义 Webhook 通知 ── -->
    <section class="form-section">
      <header class="section-header">
        <h3>自定义 Webhook 通知</h3>
        <a
          href="https://doc.auto-mas.top/docs/advanced-features/notification.html"
          class="section-doc-link"
          title="查看自定义Webhook配置文档"
          @click="handleExternalLink"
        >
          文档
        </a>
      </header>
      <div class="setting-row setting-row-multiline">
        <div class="row-label">
          <span class="row-title">Webhook 列表</span>
          <span class="row-help">添加、编辑或移除自定义 Webhook，事件触发时按渠道推送。</span>
        </div>
        <div class="row-control row-control-full">
          <WebhookManager mode="global" @change="handleWebhookChange" />
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
