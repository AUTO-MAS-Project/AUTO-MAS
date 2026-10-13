<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import WebhookManager from '@/components/WebhookManager.vue'
import type { SettingsCategory, SettingsViewModel } from '@/types/settings'
import SettingGroupRenderer from './components/SettingGroupRenderer.vue'
import { settingFieldLabels, settingFieldTips, settingOptionLabels } from './components/settingUiText'

const props = defineProps<{
  settings: SettingsViewModel
  handleSettingChange: (category: SettingsCategory, key: string, value: unknown) => Promise<boolean>
}>()

const { t } = useI18n()
const hints = computed(() => props.settings.uiHints)
const notify = computed(() => props.settings.Notify ?? {})
const hiddenFields = computed(() => ({
  koishi_server_address: notify.value.IfKoishiSupport !== true,
  koishi_token: notify.value.IfKoishiSupport !== true,
  openclaw_qq_app_id: notify.value.IfOpenClawQQ !== true,
  openclaw_qq_client_secret: notify.value.IfOpenClawQQ !== true,
  openclaw_qq_target_open_id: notify.value.IfOpenClawQQ !== true,
  smtp_server_address: notify.value.IfSendMail !== true,
  authorization_code: notify.value.IfSendMail !== true,
  from_address: notify.value.IfSendMail !== true,
  to_address: notify.value.IfSendMail !== true,
  server_chan_key: notify.value.IfServerChan !== true,
}))
</script>

<template>
  <div class="tab-content notify-tab">
    <div class="notify-toolbar">
      <a
        href="https://doc.auto-mas.top/docs/advanced-features/notification.html"
        class="toolbar-link"
        target="_blank"
        rel="noreferrer"
      >
        {{ t('setting.notify.usageDoc') }}
      </a>
    </div>

    <div class="form-section">
      <div class="section-header"><h3>{{ t('setting.notify.contentSection') }}</h3></div>
      <SettingGroupRenderer
        group="notify"
        category="Notify"
        :settings="props.settings"
        :hints="hints"
        :include="['send_task_result_time', 'if_send_statistic', 'if_send_six_star', 'if_push_plyer']"
        :label-keys="settingFieldLabels.notify"
        :tip-keys="settingFieldTips.notify"
        :option-labels="settingOptionLabels.notify"
        :handle-setting-change="props.handleSettingChange"
      />
    </div>

    <div class="form-section">
      <div class="section-header"><h3>{{ t('setting.notify.systemSection') }}</h3></div>
      <SettingGroupRenderer
        group="notify"
        category="Notify"
        :settings="props.settings"
        :hints="hints"
        :include="['if_send_mail', 'if_koishi_support', 'if_openclaw_qq', 'if_server_chan']"
        :label-keys="settingFieldLabels.notify"
        :tip-keys="settingFieldTips.notify"
        :handle-setting-change="props.handleSettingChange"
      />
    </div>

    <div class="form-section">
      <div class="section-header"><h3>{{ t('setting.notify.testSection') }}</h3></div>
      <SettingGroupRenderer
        group="notify"
        category="Notify"
        :settings="props.settings"
        :hints="hints"
        :include="['test']"
        :label-keys="settingFieldLabels.notify"
        :tip-keys="settingFieldTips.notify"
        :handle-setting-change="props.handleSettingChange"
      />
    </div>

    <div class="form-section" v-if="notify.IfSendMail === true">
      <div class="section-header"><h3>{{ t('setting.notify.mailSection') }}</h3></div>
      <SettingGroupRenderer
        group="notify"
        category="Notify"
        :settings="props.settings"
        :hints="hints"
        :include="['smtp_server_address', 'from_address', 'to_address', 'authorization_code']"
        :label-keys="settingFieldLabels.notify"
        :tip-keys="settingFieldTips.notify"
        :hidden-fields="hiddenFields"
        :handle-setting-change="props.handleSettingChange"
      />
    </div>

    <div class="form-section" v-if="notify.IfKoishiSupport === true">
      <div class="section-header"><h3>{{ t('setting.notify.koishiSection') }}</h3></div>
      <SettingGroupRenderer
        group="notify"
        category="Notify"
        :settings="props.settings"
        :hints="hints"
        :include="['koishi_server_address', 'koishi_token']"
        :label-keys="settingFieldLabels.notify"
        :tip-keys="settingFieldTips.notify"
        :hidden-fields="hiddenFields"
        :handle-setting-change="props.handleSettingChange"
      />
    </div>

    <div class="form-section" v-if="notify.IfOpenClawQQ === true">
      <div class="section-header"><h3>{{ t('setting.notify.openclawQqSection') }}</h3></div>
      <SettingGroupRenderer
        group="notify"
        category="Notify"
        :settings="props.settings"
        :hints="hints"
        :include="['openclaw_qq_app_id', 'openclaw_qq_client_secret', 'openclaw_qq_target_open_id']"
        :label-keys="settingFieldLabels.notify"
        :tip-keys="settingFieldTips.notify"
        :hidden-fields="hiddenFields"
        :handle-setting-change="props.handleSettingChange"
      />
    </div>

    <div class="form-section" v-if="notify.IfServerChan === true">
      <div class="section-header"><h3>{{ t('setting.notify.serverChanSection') }}</h3></div>
      <SettingGroupRenderer
        group="notify"
        category="Notify"
        :settings="props.settings"
        :hints="hints"
        :include="['server_chan_key']"
        :label-keys="settingFieldLabels.notify"
        :tip-keys="settingFieldTips.notify"
        :hidden-fields="hiddenFields"
        :handle-setting-change="props.handleSettingChange"
      />
    </div>

    <div class="form-section">
      <div class="section-header"><h3>{{ t('setting.notify.customSection') }}</h3></div>
      <WebhookManager mode="global" />
    </div>
  </div>
</template>

<style scoped>
.notify-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.toolbar-link {
  color: var(--ant-color-primary);
  text-decoration: none;
}
</style>
