<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { QrcodeOutlined } from '@ant-design/icons-vue'
import type { CancelablePromise, OutBase } from '@/api'
import { navigateTo } from '@/router'
import { openExternalUrl } from '@/utils/openExternal'
import { useGameSignApi } from '@/views/gamesign/useGameSignApi'
import QrLoginModal from './QrLoginModal.vue'
import { useQrLogin, type QrLoginProvider } from './useQrLogin'
import { useTokenApi } from './useTokenApi'

interface AccountOption {
  uid: string
  name: string
}

const { t } = useI18n()
const logger = window.electronAPI.getLogger('Token 获取')
const { listAccounts } = useGameSignApi()
const { loginTaygedo } = useTokenApi()
const accounts = ref<AccountOption[]>([])
const accountId = ref<string>()
const accountsLoading = ref(false)
const accountsError = ref(false)
const qrProvider = ref<QrLoginProvider>('miyoushe')
const taygedoVisible = ref(false)
const taygedoLoading = ref(false)
const taygedoForm = reactive({ phone: '', password: '' })
const saved = ref<{ name: string; platform: string }>()
let active = true
let loginRequest: CancelablePromise<OutBase> | undefined

const selectedAccount = computed(() => accounts.value.find(item => item.uid === accountId.value))
const accountOptions = computed(() =>
  accounts.value.map(item => ({ label: `${item.name} (${item.uid.slice(0, 8)})`, value: item.uid }))
)

const {
  visible: qrVisible,
  loading: qrLoading,
  status: qrStatus,
  statusText: qrStatusText,
  qrCodeDataUrl,
  start: startQr,
  cancel: cancelQr,
} = useQrLogin({
  getAccountId: () => accountId.value,
  provider: () => qrProvider.value,
  onSaved: (uid, _credential, isStillCurrent) => {
    if (!active || !isStillCurrent()) return
    const account = accounts.value.find(item => item.uid === uid)
    if (account) {
      saved.value = {
        name: account.name,
        platform: t(
          qrProvider.value === 'skland' ? 'gamesign.edit.skland' : 'gamesign.edit.miyoushe'
        ),
      }
    }
  },
  logger,
})

// 登录过程中冻结目标账号，确认扫码后不会将凭据存入另一账号。
const busy = computed(() => qrVisible.value || taygedoVisible.value)
const canLogin = computed(
  () => Boolean(selectedAccount.value) && !accountsLoading.value && !busy.value
)

const loadAccounts = async () => {
  accountsLoading.value = true
  accountsError.value = false
  try {
    const response = await listAccounts()
    if (!active) return
    if (response.code !== 200 || !response.data) throw new Error('Account list unavailable')
    const data = response.data as Record<string, unknown>
    if (!Array.isArray(data.instances)) throw new Error('Account list invalid')
    // 只保留选择器需要的名称和 UUID，不把账号列表中的明文凭据留在页面状态里。
    accounts.value = data.instances.flatMap((instance: { uid?: string; type?: string }) => {
      if (instance.type !== 'GameSignAccountGroup' || !instance.uid) return []
      const config = data[instance.uid] as { GameSignAccount?: { Name?: string } } | undefined
      return [
        { uid: instance.uid, name: config?.GameSignAccount?.Name || t('gamesign.defaultUserName') },
      ]
    })
    if (!selectedAccount.value) accountId.value = undefined
  } catch {
    if (!active) return
    accounts.value = []
    accountId.value = undefined
    accountsError.value = true
    logger.error('加载社区账号组失败')
  } finally {
    if (active) accountsLoading.value = false
  }
}

const openQr = (provider: QrLoginProvider) => {
  if (!canLogin.value) return
  saved.value = undefined
  qrProvider.value = provider
  void startQr()
}

const closeTaygedo = () => {
  // 关闭、重新锁定或离开页面时清理密码，并忽略已取消请求的晚到响应。
  loginRequest?.cancel()
  loginRequest = undefined
  taygedoVisible.value = false
  taygedoLoading.value = false
  taygedoForm.phone = ''
  taygedoForm.password = ''
}

const openTaygedo = () => {
  if (!canLogin.value) return
  saved.value = undefined
  closeTaygedo()
  taygedoVisible.value = true
}

const submitTaygedo = async () => {
  const account = selectedAccount.value
  if (!account || taygedoLoading.value) return
  taygedoLoading.value = true
  const request = loginTaygedo(account.uid, taygedoForm.phone.trim(), taygedoForm.password)
  loginRequest = request
  try {
    const response = await request
    if (!active || loginRequest !== request) return
    if (response.code !== 200 || response.status !== 'success') {
      message.error(response.message || t('mystery.tokens.taygedoFailed'))
      return
    }
    saved.value = { name: account.name, platform: t('gamesign.edit.taygedo') }
    loginRequest = undefined
    closeTaygedo()
  } catch {
    if (!active || loginRequest !== request) return
    logger.error('塔吉多登录失败')
    message.error(t('mystery.tokens.taygedoFailed'))
  } finally {
    if (loginRequest === request) {
      loginRequest = undefined
      taygedoLoading.value = false
      taygedoForm.phone = ''
      taygedoForm.password = ''
    }
  }
}

const openBmt = async () => {
  if (!(await openExternalUrl('https://github.com/Lance0174/Better-MAS-Tools')) && active) {
    message.error(t('mystery.tokens.openFailed'))
  }
}

onMounted(() => void loadAccounts())
onBeforeUnmount(() => {
  active = false
  cancelQr()
  closeTaygedo()
})
</script>

<template>
  <div class="token-tools">
    <a-card :title="t('mystery.tokens.title')">
      <p>{{ t('mystery.tokens.description') }}</p>
      <a-alert
        v-if="accountsError"
        type="error"
        show-icon
        :message="t('mystery.tokens.loadFailed')"
        class="token-notice"
      >
        <template #action>
          <a-button size="small" :loading="accountsLoading" @click="loadAccounts">
            {{ t('mystery.retry') }}
          </a-button>
        </template>
      </a-alert>
      <a-empty
        v-else-if="!accountsLoading && !accounts.length"
        :description="t('mystery.tokens.noAccounts')"
      >
        <a-button @click="navigateTo('/gamesign')">{{
          t('mystery.tokens.manageAccounts')
        }}</a-button>
      </a-empty>
      <a-form v-else layout="vertical">
        <a-form-item :label="t('mystery.tokens.account')" required>
          <a-select
            v-model:value="accountId"
            :options="accountOptions"
            :placeholder="t('mystery.tokens.accountPlaceholder')"
            :loading="accountsLoading"
            :disabled="accountsLoading || busy"
            :aria-label="t('mystery.tokens.account')"
            class="account-select"
          />
        </a-form-item>
      </a-form>
      <a-alert v-if="saved" type="success" show-icon :message="t('mystery.tokens.saved', saved)" />
    </a-card>

    <a-row :gutter="[16, 16]">
      <a-col :xs="24" :lg="12">
        <a-card :title="t('gamesign.edit.miyoushe')" class="token-card">
          <p>{{ t('mystery.tokens.miyousheDescription') }}</p>
          <a-button type="primary" :disabled="!canLogin" @click="openQr('miyoushe')">
            <template #icon><QrcodeOutlined /></template>
            {{ t('gamesign.edit.qrLogin') }}
          </a-button>
        </a-card>
      </a-col>
      <a-col :xs="24" :lg="12">
        <a-card :title="t('gamesign.edit.skland')" class="token-card">
          <p>{{ t('mystery.tokens.sklandDescription') }}</p>
          <a-button type="primary" :disabled="!canLogin" @click="openQr('skland')">
            <template #icon><QrcodeOutlined /></template>
            {{ t('gamesign.edit.qrLogin') }}
          </a-button>
        </a-card>
      </a-col>
      <a-col :xs="24" :lg="12">
        <a-card :title="t('gamesign.edit.taygedo')" class="token-card">
          <p>{{ t('mystery.tokens.taygedoDescription') }}</p>
          <a-button type="primary" :disabled="!canLogin" @click="openTaygedo">
            {{ t('gamesign.edit.passwordLogin') }}
          </a-button>
        </a-card>
      </a-col>
      <a-col :xs="24" :lg="12">
        <a-card :title="t('gamesign.edit.kuro')" class="token-card">
          <p>{{ t('mystery.tokens.kuroDescription') }}</p>
          <a-button @click="openBmt">{{ t('mystery.tokens.openBmt') }}</a-button>
        </a-card>
      </a-col>
    </a-row>

    <a-modal
      :open="taygedoVisible"
      :title="t('gamesign.login.taygedoTitle')"
      :footer="null"
      :width="420"
      :body-style="{ maxHeight: 'calc(100vh - 180px)', overflowY: 'auto' }"
      centered
      @cancel="closeTaygedo"
    >
      <a-alert
        type="info"
        show-icon
        :message="t('mystery.tokens.privacyNotice')"
        class="token-notice"
      />
      <a-form :model="taygedoForm" layout="vertical" @finish="submitTaygedo">
        <a-form-item :label="t('gamesign.login.currentAccount')">
          <a-input :value="selectedAccount?.name || ''" disabled />
        </a-form-item>
        <a-form-item
          name="phone"
          :label="t('gamesign.login.taygedoAccount')"
          :rules="[
            {
              required: true,
              whitespace: true,
              message: t('gamesign.login.taygedoAccountPlaceholder'),
            },
          ]"
        >
          <a-input
            v-model:value="taygedoForm.phone"
            autocomplete="off"
            :disabled="taygedoLoading"
            :placeholder="t('gamesign.login.taygedoAccountPlaceholder')"
          />
        </a-form-item>
        <a-form-item
          name="password"
          :label="t('gamesign.login.password')"
          :rules="[{ required: true, message: t('gamesign.login.taygedoPasswordPlaceholder') }]"
        >
          <a-input-password
            v-model:value="taygedoForm.password"
            autocomplete="new-password"
            :disabled="taygedoLoading"
            :placeholder="t('gamesign.login.taygedoPasswordPlaceholder')"
          />
        </a-form-item>
        <a-space class="login-actions">
          <a-button @click="closeTaygedo">{{ t('common.cancel') }}</a-button>
          <a-button type="primary" html-type="submit" :loading="taygedoLoading">
            {{ t('gamesign.login.submit') }}
          </a-button>
        </a-space>
      </a-form>
    </a-modal>

    <QrLoginModal
      :open="qrVisible"
      :status="qrStatus"
      :status-text="qrStatusText"
      :qr-code-data-url="qrCodeDataUrl"
      :loading="qrLoading"
      :provider="qrProvider"
      @cancel="cancelQr"
      @retry="startQr"
    />
  </div>
</template>

<style scoped>
.token-tools {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.token-card {
  height: 100%;
}

.account-select {
  max-width: 480px;
}

.token-notice {
  margin-bottom: 16px;
}

.login-actions {
  width: 100%;
  justify-content: flex-end;
}
</style>
