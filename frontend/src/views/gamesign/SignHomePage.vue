<!--
  游戏社区首页（签到页）。
  只负责把四块内容按固定顺序摆好：免责声明 → 设置 → 帐号总览 → 签到结果。
  数据与提交都在页面容器里，这里不直接读写配置。
-->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ToolsConfig_SignFlow } from '@/api'
import type { AccountInstance } from './gameSignAccounts'
import type { PlatformResult } from './gameSignDisplay'
import AccountSummarySection from './components/AccountSummarySection.vue'
import SignResultSection from './components/SignResultSection.vue'
import SignSettingsPanel from './components/SignSettingsPanel.vue'

defineProps<{
  config: ToolsConfig_SignFlow
  result: PlatformResult
  accounts: readonly AccountInstance[]
  disabled?: boolean
  accountsLoading?: boolean
  signLoading?: boolean
  onFieldChange?: <K extends keyof ToolsConfig_SignFlow>(
    key: K,
    value: ToolsConfig_SignFlow[K]
  ) => void | Promise<void>
}>()

const emit = defineEmits<{
  manage: []
  sign: []
  refresh: []
}>()

const { t } = useI18n()
</script>

<template>
  <div class="sign-home">
    <!-- 免责声明固定置顶：凭据迁移前必须让用户先看到这条 -->
    <a-alert
      class="sign-disclaimer"
      type="warning"
      show-icon
      :message="t('core.gamesign.disclaimer.title')"
      :description="t('core.gamesign.disclaimer.description')"
    />

    <section class="home-block">
      <SignSettingsPanel :config="config" :disabled="disabled" :on-field-change="onFieldChange" />
    </section>

    <section class="home-block">
      <AccountSummarySection
        :accounts="accounts"
        :loading="accountsLoading"
        @manage="emit('manage')"
      />
    </section>

    <section class="home-block">
      <SignResultSection
        :result="result"
        :loading="signLoading"
        @sign="emit('sign')"
        @refresh="emit('refresh')"
      />
    </section>
  </div>
</template>

<style scoped>
.sign-home {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 20px 24px 24px;
}

.sign-disclaimer {
  border-radius: var(--ant-border-radius-lg);
}

.home-block {
  display: flex;
  flex-direction: column;
}

@media (max-width: 860px) {
  .sign-home {
    padding: 12px 16px 16px;
  }
}
</style>
