<!--
  游戏社区：帐号编辑抽屉。
  名称与开关随保存一起提交；凭据按平台逐项绑定：森空岛与米游社扫码，
  塔吉多账密，库街区短信，其余平台只能手填。
  提交一律走 diffAccountForm 产出的补丁，避免把加载时的旧凭据整份回写。
  扫码 / 账密 / 短信登录都由后端直接落库：响应里给的是票据或中间值，
  真正的凭据是后端兑换后写进账号组的，所以成功后按账号 UID 回读，
  只更新该字段的表单值与基线，不改动其它还没提交的编辑。
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQrLogin, type QrLoginProvider } from '@/views/mystery/tokens/useQrLogin'
import QrLoginModal from '@/views/mystery/tokens/QrLoginModal.vue'
import AccountCredentialRow from './AccountCredentialRow.vue'
import AccountTokenStatus from './AccountTokenStatus.vue'
import KuroSmsLoginModal from './KuroSmsLoginModal.vue'
import TaygedoLoginModal from './TaygedoLoginModal.vue'
import {
  CREDENTIAL_ROWS,
  diffAccountForm,
  hasCredential,
  toAccountForm,
  type AccountForm,
  type AccountInstance,
  type CredentialField,
} from '../gameSignAccounts'
import type { CredentialAction } from './AccountCredentialRow.vue'

const props = defineProps<{
  open: boolean
  account: AccountInstance | null
  saving?: boolean
  /** 按帐号 UID 回读服务端最新快照；扫码、账密与短信登录都由后端直接写库，界面不能凭回调参数猜值 */
  onReload?: (uid: string) => Promise<AccountInstance | null>
}>()

const emit = defineEmits<{
  close: []
  save: [account: AccountInstance, patch: Record<string, unknown>]
}>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('游戏社区')

/**
 * 抽屉要让开 Electron 的 32px 无边框标题栏。
 *
 * `appOverlays.css` 只给 modal 补了这条偏移，drawer 没有全局兜底，
 * 不传就会从窗口最顶端开始画，标题栏压住抽屉标题。
 * root-style 作用在 `.ant-drawer` 根节点上，遮罩与面板一起下移，
 * 因此不需要为了避让而关掉遮罩。
 */
const drawerRootStyle: CSSProperties = {
  top: '32px',
  height: 'calc(100% - 32px)',
}

const form = ref<AccountForm>(toAccountForm(null))
const baseline = ref<AccountForm>(toAccountForm(null))

/** 本次抽屉会话编号：打开或切账号时递增，用来丢弃迟到的回读结果 */
const drawerSession = ref(0)
/** 本次会话里用户亲手改过的凭据字段：回读时只对齐基线，不覆盖输入 */
let editedFields = new Set<CredentialField>()

watch(
  () => [props.open, props.account?.uid] as const,
  () => {
    drawerSession.value += 1
    editedFields = new Set<CredentialField>()
    if (!props.open) return
    // 每次打开都从最新快照重新取基线，避免上次未保存的改动残留
    form.value = toAccountForm(props.account)
    baseline.value = toAccountForm(props.account)
  },
  { immediate: true }
)

const accountName = computed(() => props.account?.Name || t('core.signflow.defaultUserName'))
const boundCount = computed(
  () => CREDENTIAL_ROWS.filter(row => hasCredential(form.value, row.field)).length
)

const drawerOpen = computed({
  get: () => props.open,
  set: (value: boolean) => {
    if (!value) emit('close')
  },
})

/** 森空岛与米游社扫码，塔吉多账密，库街区短信，其余平台手动粘贴 */
const credentialAction = (field: CredentialField): CredentialAction | null => {
  if (field === 'SklandToken' || field === 'MiyousheToken') return 'qr'
  if (field === 'TaygedoToken') return 'password'
  if (field === 'KuroToken') return 'sms'
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
 * 标记之后，还在路上的扫码 / 账密 / 短信回读就不能再覆盖输入，
 * 否则用户刚清空或刚粘贴的值会被服务端旧值盖掉，点保存也看不出刚改过。
 */
const onFieldInput = (field: CredentialField, value: string) => {
  form.value = { ...form.value, [field]: value }
  editedFields.add(field)
}

/**
 * 按账号 UID 回读服务端已保存的字段。
 *
 * 扫码、账密与短信登录都不经过本抽屉的保存动作，后端写完库后表单必须重新对齐，
 * 否则保存时会把回调参数（票据）当成新凭据提交，或整份覆盖掉后台刚轮换的凭据。
 * 回读是异步的，落地前要过两道闸：这次抽屉会话是否还在，用户是否已经改过该字段。
 */
const reloadCredentialField = async (field: CredentialField) => {
  const account = props.account
  const reload = props.onReload
  if (!account || !reload) return
  const session = drawerSession.value
  const fresh = await reload(account.uid)
  // 抽屉已关闭或已切到别的账号，这次结果没有落点
  if (session !== drawerSession.value) return
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

const passwordVisible = ref(false)
const smsVisible = ref(false)

const openCredentialLogin = (field: CredentialField) => {
  if (!props.account) return
  // 登录成功后写入的就是这一项，先撤掉手填标记，让回读能落到表单
  editedFields.delete(field)
  if (field === 'TaygedoToken') passwordVisible.value = true
  else if (field === 'KuroToken') smsVisible.value = true
}

const handleCredentialSaved = (field: CredentialField) => {
  void reloadCredentialField(field)
}

/** 凭据体检里刷新成功的字段同样由后端写库，逐项回读 */
const handleTokenRefreshed = (tokenField: string) => {
  const matched = CREDENTIAL_ROWS.find(row => row.field === tokenField)
  if (matched) void reloadCredentialField(matched.field)
}

const handleRowAction = (field: CredentialField) => {
  const action = credentialAction(field)
  if (action === 'qr') startQrLogin(field)
  else openCredentialLogin(field)
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
})
</script>

<template>
  <a-drawer
    v-model:open="drawerOpen"
    :title="t('core.signflow.edit.title', { name: accountName })"
    :width="520"
    :root-style="drawerRootStyle"
    placement="right"
  >
    <div class="editor-body">
      <section class="editor-block">
        <span class="editor-title">{{ t('core.signflow.edit.userName') }}</span>
        <a-input v-model:value="form.Name" size="large" :maxlength="40" :disabled="saving" />
        <div class="editor-switch-row">
          <span class="editor-switch-label">{{ t('core.signflow.account.enabled') }}</span>
          <a-switch v-model:checked="form.Enabled" size="small" :disabled="saving" />
        </div>
      </section>

      <a-divider class="editor-divider" />

      <AccountCredentialRow
        v-for="row in CREDENTIAL_ROWS"
        :key="row.field"
        :field="row.field"
        :label="t(row.label)"
        :placeholder="t(row.placeholder)"
        :value="form[row.field]"
        :action="credentialAction(row.field)"
        :disabled="saving"
        @update:value="value => onFieldInput(row.field, value)"
        @clear="clearCredential(row.field)"
        @action="handleRowAction(row.field)"
      />

      <AccountTokenStatus
        v-if="props.account"
        :account-uid="props.account.uid"
        :session="drawerSession"
        @refreshed="handleTokenRefreshed"
      />

      <a-alert
        class="editor-notice"
        type="warning"
        show-icon
        :message="t('core.signflow.disclaimer.title')"
        :description="t('core.signflow.disclaimer.description')"
      />
    </div>

    <template #footer>
      <div class="editor-footer">
        <span class="editor-count">
          {{ t('core.signflow.account.credentialCount', { n: boundCount }) }}
        </span>
        <a-space :size="8">
          <a-button @click="emit('close')">{{ t('core.common.cancel') }}</a-button>
          <a-button type="primary" :loading="saving" @click="handleSave">
            {{ t('core.signflow.edit.save') }}
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

  <TaygedoLoginModal
    :open="passwordVisible"
    :account-uid="props.account?.uid ?? ''"
    @close="passwordVisible = false"
    @saved="handleCredentialSaved('TaygedoToken')"
  />

  <KuroSmsLoginModal
    :open="smsVisible"
    :account-uid="props.account?.uid ?? ''"
    @close="smsVisible = false"
    @saved="handleCredentialSaved('KuroToken')"
  />
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

.editor-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
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
</style>
