<!--
  游戏社区：帐号编辑抽屉。
  名称与开关随保存一起提交；凭据按平台逐项绑定，扫码走神秘入口已有的 useQrLogin，
  塔吉多走账密接口，库街区与云·原神只支持手动粘贴。
  提交一律走 diffAccountForm 产出的补丁，避免把加载时的旧凭据整份回写。
  扫码与账密登录都由后端直接落库：森空岛扫码确认只能拿到短时扫码码，
  真正的凭据是后端拿它兑换后再写进账号组的，所以成功后按账号 UID 回读，
  只更新该字段的表单值与基线，不改动其它还没提交的编辑。
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
  /** 按帐号 UID 回读服务端最新快照；扫码与账密登录都由后端直接写库，界面不能凭回调参数猜值 */
  onReload?: (uid: string) => Promise<AccountInstance | null>
}>()

const emit = defineEmits<{
  close: []
  save: [account: AccountInstance, patch: Record<string, unknown>]
}>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('游戏社区')
const { loginTaygedo } = useTokenApi()

const form = ref<AccountForm>(toAccountForm(null))
const baseline = ref<AccountForm>(toAccountForm(null))

/** 本次抽屉会话编号：打开或切账号时递增，用来丢弃迟到的回读结果 */
let drawerSession = 0
/** 本次会话里用户亲手改过的凭据字段：回读时只对齐基线，不覆盖输入 */
let editedFields = new Set<CredentialField>()

watch(
  () => [props.open, props.account?.uid] as const,
  () => {
    drawerSession += 1
    editedFields = new Set<CredentialField>()
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
  onSaved: async () => {
    // 回调里的 credential 只是扫码票据（森空岛是短时 scan_code），不是账号组里的凭据，
    // 直接写进表单会把票据存成 Token，所以回读后端已保存的字段。
    // 这里必须等回读落地再返回：否则抽屉会先进入「已完成」态，用户接着手改同一项时
    // 回读还在路上，落地就会覆盖刚输入的值。
    await reloadCredentialField(qrProvider.value === 'skland' ? 'SklandToken' : 'MiyousheToken')
  },
  logger,
})

/**
 * 手填与清除都算「用户编辑过这个字段」。
 *
 * 标记之后，还在路上的扫码 / 账密回读就不能再覆盖输入，
 * 否则用户刚清空或刚粘贴的值会被服务端旧值盖掉，点保存也看不出刚改过。
 */
const onFieldInput = (field: CredentialField, value: string) => {
  form.value = { ...form.value, [field]: value }
  editedFields.add(field)
}

/** 模板里按行绑定输入事件：柯里化后参数类型由 TS 推导，不用在模板写类型标注 */
const onCredentialInput = (field: CredentialField) => (value: string) => onFieldInput(field, value)

/**
 * 按账号 UID 回读服务端已保存的字段。
 *
 * 扫码和账密登录都不经过本抽屉的保存动作，后端写完库后表单必须重新对齐，
 * 否则保存时会把回调参数（票据）当成新凭据提交，或整份覆盖掉后台刚轮换的凭据。
 * 回读是异步的，落地前要过两道闸：这次抽屉会话是否还在，用户是否已经改过该字段。
 */
const reloadCredentialField = async (field: CredentialField) => {
  const account = props.account
  const reload = props.onReload
  if (!account || !reload) return
  const session = drawerSession
  const fresh = await reload(account.uid)
  // 抽屉已关闭或已切到别的账号，这次结果没有落点
  if (session !== drawerSession) return
  if (!props.account || props.account.uid !== account.uid) return
  if (!fresh) return
  const value = toAccountForm(fresh)[field]
  // 基线始终对齐服务端，保证「没改过就不提交」的判断成立
  baseline.value = { ...baseline.value, [field]: value }
  // 用户在这段时间里动过该字段：保留输入，只更新基线
  if (editedFields.has(field)) return
  form.value = { ...form.value, [field]: value }
}

const startQrLogin = (field: CredentialField) => {
  if (!props.account) return
  qrProvider.value = field === 'SklandToken' ? 'skland' : 'miyoushe'
  qrAccountId.value = props.account.uid
  // 用户主动发起扫码，等于要用服务端写入的凭据替换这一项，先撤掉手填标记
  editedFields.delete(field)
  void startQr()
}

let loginRequest: CancelablePromise<OutBase> | undefined
const passwordVisible = ref(false)
const passwordForm = ref({ phone: '', password: '' })
const passwordLoading = ref(false)

const openPasswordLogin = () => {
  passwordForm.value = { phone: '', password: '' }
  passwordVisible.value = true
  // 同扫码：这次账密登录的结果就是要替换 TaygedoToken，先撤掉手填标记
  editedFields.delete('TaygedoToken')
}

/**
 * 关闭账密弹窗：取消在途请求时一并复位加载态。
 *
 * 取消后 Promise 会 reject，但那时 loginRequest 已被清空，finally 里的身份比对不再成立，
 * 只复位 loading 的分支不会执行；这里不显式复位，下次打开弹窗提交按钮会一直转圈。
 */
const closePasswordLogin = () => {
  loginRequest?.cancel()
  loginRequest = undefined
  passwordLoading.value = false
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
    // 账密登录由后端直接写库，密码换来的 Token 只在响应之外落盘，必须回读
    await reloadCredentialField('TaygedoToken')
  } catch (error) {
    // 用户关闭弹窗会取消请求，这不是登录失败，迟到的 reject 直接丢弃
    if (loginRequest !== request) return
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
  onFieldInput(field, '')
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
          :value="form[row.field]"
          size="large"
          allow-clear
          :placeholder="t(row.placeholder)"
          @update:value="onCredentialInput(row.field)"
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
