<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { MiyousheGenshinApiError } from '@/composables/useMiyousheGenshinApi'
import { navigateTo } from '@/router'
import { useBettergiMiyousheLogin, type MiyousheLoginProps } from './useBettergiMiyousheLogin'

const props = defineProps<MiyousheLoginProps>()
const emit = defineEmits<{ enabledChange: [enabled: boolean] }>()
const { t, te } = useI18n()
const errorText = (cause: unknown) => {
  const reason = cause instanceof MiyousheGenshinApiError ? cause.reason : ''
  const key = `edit.bettergiMiyousheErrors.${reason}`
  return reason && te(key) ? t(key) : t('edit.bettergiMiyousheRequestFailed')
}
const {
  accountsLoading,
  rolesLoading,
  draft,
  accounts,
  roles,
  accountsLoaded,
  rolesLoaded,
  accountError,
  roleError,
  saveFailed,
  saving,
  officialClient,
  selectedAccount,
  accountMissing,
  selectedRole,
  dirty,
  canSave,
  loadAccounts,
  loadRoles,
  saveSettings,
  changeEnabled,
  changeAccount,
  changeRole,
  initialize,
  dispose,
} = useBettergiMiyousheLogin(props, enabled => emit('enabledChange', enabled), errorText)
onMounted(initialize)
onUnmounted(dispose)
</script>

<template>
  <div class="miyoushe-login-section">
    <a-form-item :label="t('edit.bettergiMiyousheLogin')">
      <a-space align="start" wrap>
        <a-switch
          :checked="draft.MiyousheLogin"
          :loading="saving"
          :disabled="disabled || (!officialClient && !draft.MiyousheLogin)"
          :aria-label="t('edit.bettergiMiyousheLogin')"
          @change="changeEnabled"
        />
        <span>{{ t('edit.bettergiMiyousheLoginHint') }}</span>
      </a-space>
    </a-form-item>

    <a-alert
      v-if="!officialClient"
      class="login-alert"
      type="warning"
      show-icon
      :message="t('edit.bettergiMiyousheOfficialOnly')"
    />
    <template v-if="draft.MiyousheLogin">
      <a-alert
        class="login-alert"
        type="info"
        show-icon
        :message="t('edit.bettergiMiyousheLaunchHint')"
      />
      <a-row :gutter="24">
        <a-col :xs="24" :md="12">
          <a-form-item :label="t('edit.bettergiMiyousheAccount')" required>
            <a-select
              :value="draft.MiyousheAccountUid || undefined"
              :loading="accountsLoading"
              :disabled="disabled || saving || accountsLoading"
              :placeholder="t('edit.bettergiMiyousheSelectAccount')"
              size="large"
              class="login-select"
              @change="changeAccount"
            >
              <a-select-option
                v-for="account in accounts"
                :key="account.uid"
                :value="account.uid"
                :disabled="!account.has_credentials"
              >
                {{ account.name || t('gamesign.defaultUserName') }}
                {{ account.has_credentials ? '' : t('edit.bettergiMiyousheNeedsLogin') }}
              </a-select-option>
              <a-select-option v-if="accountMissing" :value="draft.MiyousheAccountUid" disabled>
                {{ t('edit.bettergiMiyousheAccountMissing') }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-form-item :label="t('edit.bettergiMiyousheRole')" required>
            <a-select
              :value="draft.MiyousheRoleUid || undefined"
              :loading="rolesLoading"
              :disabled="disabled || saving || rolesLoading || !selectedAccount?.has_credentials"
              :placeholder="t('edit.bettergiMiyousheSelectRole')"
              size="large"
              class="login-select"
              @change="changeRole"
            >
              <a-select-option v-for="role in roles" :key="role.uid" :value="role.uid">
                {{ role.nickname }} · {{ role.uid }} · {{ role.region_name }}
              </a-select-option>
              <a-select-option
                v-if="draft.MiyousheRoleUid && !selectedRole"
                :value="draft.MiyousheRoleUid"
                disabled
              >
                {{ draft.MiyousheRoleUid }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
      </a-row>
      <a-alert
        v-if="accountError || roleError"
        class="login-alert"
        type="error"
        show-icon
        :message="accountError || roleError"
      />
      <a-alert
        v-else-if="accountsLoaded && !accounts.some(account => account.has_credentials)"
        class="login-alert"
        type="info"
        show-icon
        :message="t('edit.bettergiMiyousheNoAccounts')"
      />
      <a-alert
        v-else-if="accountMissing"
        class="login-alert"
        type="warning"
        show-icon
        :message="t('edit.bettergiMiyousheAccountMissing')"
      />
      <a-alert
        v-else-if="selectedAccount && !selectedAccount.has_credentials"
        class="login-alert"
        type="warning"
        show-icon
        :message="t('edit.bettergiMiyousheErrors.credential_incomplete')"
      />
      <a-alert
        v-else-if="rolesLoaded && !roles.length"
        class="login-alert"
        type="warning"
        show-icon
        :message="t('edit.bettergiMiyousheNoRoles')"
      />
      <div class="login-actions">
        <a-space wrap>
          <a-button :disabled="disabled || saving" @click="navigateTo('/gamesign')">
            {{ t('edit.bettergiMiyousheManageAccounts') }}
          </a-button>
          <a-button :loading="accountsLoading" :disabled="disabled || saving" @click="loadAccounts">
            {{ t('edit.bettergiMiyousheRefreshAccounts') }}
          </a-button>
          <a-button
            :loading="rolesLoading"
            :disabled="disabled || saving || !selectedAccount?.has_credentials"
            @click="loadRoles(draft.MiyousheAccountUid)"
          >
            {{ t('edit.bettergiMiyousheRefreshRoles') }}
          </a-button>
        </a-space>
      </div>
      <a-alert
        v-if="dirty && !saving && !saveFailed"
        class="login-alert"
        type="info"
        show-icon
        :message="t('edit.bettergiMiyousheSelectionPending')"
      />
    </template>
    <a-alert
      v-if="saveFailed"
      class="login-alert"
      type="error"
      show-icon
      :message="t('edit.bettergiMiyousheSaveFailed')"
    >
      <template #action>
        <a-button
          size="small"
          :loading="saving"
          :disabled="disabled || (draft.MiyousheLogin && !canSave)"
          @click="saveSettings"
        >
          {{ t('edit.bettergiMiyousheRetrySave') }}
        </a-button>
      </template>
    </a-alert>
  </div>
</template>

<style scoped>
.login-select {
  width: 100%;
}

.login-alert {
  margin-bottom: 16px;
}

.login-actions {
  margin-bottom: 16px;
}
</style>
