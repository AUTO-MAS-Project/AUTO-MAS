<!--
  游戏社区：帐号编辑抽屉。
  名称与开关随保存一起提交；凭据按平台逐项绑定，扫码走神秘入口已有的 useQrLogin，
  塔吉多走账密接口，库街区与云·原神只支持手动粘贴。
  提交一律走 diffAccountForm 产出的补丁，避免把加载时的旧凭据整份回写。
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { QrcodeOutlined } from '@ant-design/icons-vue'
import type { CancelablePromise, OutBase } from '@/api'
import { useQrLogin, type QrLoginProvider } from '@/views/mystery/tokens/useQrLogin'
import QrLoginModal from '@/views/mystery/tokens/QrLoginModal.vue'
import { useTokenApi } from '@/views/mystery/tokens/useTokenApi'
import {
  CREDENTIAL_ROWS,
  diffAccountForm,
  hasCredential,
  toAccountForm,
  type AccountForm,
  type AccountInstance,
  type CredentialField,
} from '../gameSignAccounts'

const props = defineProps<{
  open: boolean
  account: AccountInstance | null
  saving?: boolean
}>()

const emit = defineEmits<{
  close: []
  save: [account: AccountInstance, patch: Record<string, unknown>]
  reload: []
}>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('游戏社区')
const { loginTaygedo } = useTokenApi()

const form = ref<AccountForm>(toAccountForm(null))
const baseline = ref<AccountForm>(toAccountForm(null))

watch(
  () => [props.open, props.account?.uid] as const,
  () => {
    if (!props.open) return
    // 每次打开都从最新快照重新取基线，避免上次未保存的改动残留
    form.value = toAccountForm(props.account)
    baseline.value = toAccountForm(props.account)
  },
  { immediate: true }
)

const accountName = computed(() => props.account?.Name || t('core.gamesign.defaultUserName'))
const boundCount = computed(
  () => CREDENTIAL_ROWS.filter(row => hasCredential(form.value, row.field)).length
)

const drawerOpen = computed({
  get: () => props.open,
  set: (value: boolean) => {
    if (!value) emit('close')
  },
})

type CredentialAction = 'qr' | 'password'
/** 只有森空岛和米游社有扫码通道，塔吉多走账密，其余平台手动粘贴 */
const credentialAction = (field: CredentialField): CredentialAction | null => {
  if (field === 'SklandToken' || field === 'MiyousheToken') return 'qr'
  if (field === 'TaygedoToken') return 'password'
  return null
}

const qrProvider = ref<QrLoginProvider>('skland')
const qrAccountId = ref<string | undefined>(undefined)

const {
  visible: qrVisible,
  loading: qrLoading,
  status: qrStatus,
  statusText: qrStatusText,
  qrCodeDataUrl,
  start: startQr,
  cancel: cancelQr,
} = useQrLogin({
  getAccountId: () => qrAccountId.value,
  provider: () => qrProvider.value,
  onSaved: (_accountId, credential) => {
    // 扫码保存成功后后端已写库，本地同步进表单，保存时补丁里就是同一份值
    const field: CredentialField = qrProvider.value === 'skland' ? 'SklandToken' : 'MiyousheToken'
    form.value = { ...form.value, [field]: credential }
    baseline.value = { ...baseline.value, [field]: credential }
  },
  logger,
})

const startQrLogin = (field: CredentialField) => {
  if (!props.account) return
  qrProvider.value = field === 'SklandToken' ? 'skland' : 'miyoushe'
  qrAccountId.value = props.account.uid
  void startQr()
}

let loginRequest: CancelablePromise<OutBase> | undefined
const passwordVisible = ref(false)
const passwordForm = ref({ phone: '', password: '' })
const passwordLoading = ref(false)

const openPasswordLogin = () => {
  passwordForm.value = { phone: '', password: '' }
  passwordVisible.value = true
}

const closePasswordLogin = () => {
  loginRequest?.cancel()
  loginRequest = undefined
  passwordVisible.value = false
  passwordForm.value = { phone: '', password: '' }
}

const submitPasswordLogin = async () => {
  if (!props.account) return
  const phone = passwordForm.value.phone.trim()
  const password = passwordForm.value.password
  if (!phone || !password) return
  passwordLoading.value = true
  const request = loginTaygedo(props.account.uid, phone, password)
  loginRequest = request
  try {
    const response = await request
    if (loginRequest !== request) return
    if (response.code !== 200 || response.status !== 'success') {
      message.error(response.message || t('core.mystery.tokens.taygedoFailed'))
      return
    }
    message.success(t('core.gamesign.toast.tokenSaved'))
    closePasswordLogin()
    // 账密登录由后端直接写库，通知父级重拉，避免本地表单与后端值分叉
    emit('reload')
  } catch (error) {
    logger.error(`塔吉多账密登录失败: ${error instanceof Error ? error.message : String(error)}`)
    message.error(t('core.mystery.tokens.taygedoFailed'))
  } finally {
    if (loginRequest === request) {
      loginRequest = undefined
      passwordLoading.value = false
    }
  }
}

const clearCredential = (field: CredentialField) => {
  form.value = { ...form.value, [field]: '' }
}

const handleSave = () => {
  if (!props.account) return
  const patch = diffAccountForm(baseline.value, form.value)
  emit('save', props.account, patch as Record<string, unknown>)
}

onBeforeUnmount(() => {
  cancelQr()
  loginRequest?.cancel()
})
</script>

<template>
  <a-drawer
    v-model:open="drawerOpen"
    :title="t('core.gamesign.edit.title', { name: accountName })"
    :width="520"
    placement="right"
  >
    <div class="editor-body">
      <section class="editor-block">
        <div class="editor-head">
          <span class="editor-title">{{ t('core.gamesign.edit.userName') }}</span>
        </div>
        <a-input v-model:value="form.Name" size="large" :maxlength="40" />
        <div class="editor-switch-row">
          <span class="editor-switch-label">{{ t('core.gamesign.account.enabled') }}</span>
          <a-switch v-model:checked="form.Enabled" size="small" />
        </div>
      </section>

      <a-divider class="editor-divider" />

      <section v-for="row in CREDENTIAL_ROWS" :key="row.field" class="editor-block">
        <div class="editor-head">
          <span class="editor-title">{{ t(row.label) }}</span>
          <span class="editor-tools">
            <a-button
              v-if="hasCredential(form, row.field)"
              type="link"
              size="small"
              @click="clearCredential(row.field)"
            >
              {{ t('core.gamesign.cred.clear') }}
            </a-button>
            <a-button
              v-if="credentialAction(row.field) === 'qr'"
              type="link"
              size="small"
              @click="startQrLogin(row.field)"
            >
              <template #icon><QrcodeOutlined /></template>
              {{ t('core.gamesign.edit.qrLogin') }}
            </a-button>
            <a-button
              v-else-if="credentialAction(row.field) === 'password'"
              type="link"
              size="small"
              @click="openPasswordLogin"
            >
              {{ t('core.gamesign.edit.passwordLogin') }}
            </a-button>
            <span v-else class="editor-manual">{{ t('core.gamesign.account.manualHint') }}</span>
          </span>
        </div>
        <a-input-password
          v-model:value="form[row.field]"
          size="large"
          allow-clear
          :placeholder="t(row.placeholder)"
        />
      </section>

      <a-alert
        class="editor-notice"
        type="warning"
        show-icon
        :message="t('core.gamesign.disclaimer.title')"
        :description="t('core.gamesign.disclaimer.description')"
      />
    </div>

    <template #footer>
      <div class="editor-footer">
        <span class="editor-count">
          {{ t('core.gamesign.account.credentialCount', { n: boundCount }) }}
        </span>
        <a-space :size="8">
          <a-button @click="emit('close')">{{ t('core.common.cancel') }}</a-button>
          <a-button type="primary" :loading="saving" @click="handleSave">
            {{ t('core.gamesign.edit.save') }}
          </a-button>
        </a-space>
      </div>
    </template>
  </a-drawer>

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

  <a-modal
    v-model:open="passwordVisible"
    :title="t('core.gamesign.login.taygedoTitle')"
    :width="380"
    :footer="null"
    centered
    @cancel="closePasswordLogin"
  >
    <div class="password-form">
      <a-input
        v-model:value="passwordForm.phone"
        size="large"
        :placeholder="t('core.gamesign.login.taygedoAccountPlaceholder')"
      />
      <a-input-password
        v-model:value="passwordForm.password"
        size="large"
        :placeholder="t('core.gamesign.login.taygedoPasswordPlaceholder')"
      />
      <a-button
        type="primary"
        block
        :loading="passwordLoading"
        :disabled="!passwordForm.phone.trim() || !passwordForm.password"
        @click="submitPasswordLogin"
      >
        {{ t('core.gamesign.login.submit') }}
      </a-button>
    </div>
  </a-modal>
</template>

<style scoped>
.editor-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.editor-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.editor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.editor-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.editor-tools {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.editor-manual {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.editor-switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 4px;
}

.editor-switch-label {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.editor-divider {
  margin: 0;
}

.editor-notice {
  margin-top: 4px;
}

.editor-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.editor-count {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.password-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}
</style>
