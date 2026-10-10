<script setup lang="ts">
import { UserOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

import type { ShareAccount } from '../useShareAccount'

const props = defineProps<{
  account: ShareAccount
}>()

const { t } = useI18n()
const { state, starting, authorized, pending, accountName, login, cancel, openVerificationPage } =
  props.account
</script>

<template>
  <div class="store-account">
    <template v-if="authorized">
      <span class="store-account-name">
        <UserOutlined />
        {{ t('themeStore.account.signedInAs', { name: accountName }) }}
      </span>
      <a-button type="link" size="small" :loading="starting" @click="login">
        {{ t('themeStore.account.switch') }}
      </a-button>
    </template>
    <template v-else-if="pending">
      <span class="store-account-hint">{{ t('themeStore.account.pending') }}</span>
      <span class="store-account-code">{{ state.userCode }}</span>
      <a-button size="small" @click="openVerificationPage">
        {{ t('themeStore.account.reopen') }}
      </a-button>
      <a-button size="small" type="text" @click="cancel">
        {{ t('themeStore.account.cancel') }}
      </a-button>
    </template>
    <template v-else>
      <span v-if="state.message" class="store-account-hint">{{ state.message }}</span>
      <a-button :loading="starting" @click="login">
        {{ t('themeStore.account.login') }}
      </a-button>
    </template>
  </div>
</template>

<style scoped>
.store-account {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
}

.store-account-name {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  color: var(--ant-color-text-secondary);
}

.store-account-hint {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.store-account-code {
  padding: 0 8px;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  color: var(--ant-color-text);
  font-family: var(--font-monospace);
  font-size: 15px;
  letter-spacing: 2px;
}
</style>
