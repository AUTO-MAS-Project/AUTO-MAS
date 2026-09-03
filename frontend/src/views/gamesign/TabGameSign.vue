<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  EditOutlined,
  DeleteOutlined,
  PlusOutlined,
  SwapOutlined,
  QrcodeOutlined,
  MessageOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import draggable from 'vuedraggable'
import type { GameSignAccountGroupConfig, ToolsConfig_GameSign } from '@/api'
import { useGameSignAccountApi } from '@/composables/useGameSignAccountApi'
import DocLink from '@/components/DocLink.vue'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import QrLoginModal from './QrLoginModal.vue'
import { useGameSignApi } from './useGameSignApi'
import { useQrLogin } from './useQrLogin'
import {
  buildUserTagsMap,
  getSignDetailAlias,
  getSignDetailClass,
  getSignStatusKey,
  getTagClass,
  getTagText,
  parseSignResult,
  type AccountGroup,
  type PlatformTag,
} from './gameSignDisplay'

const { t } = useI18n()

const {
  config,
  disabled = false,
  onFieldChange = undefined,
  onRefreshConfig = undefined,
} = defineProps<{
  config: ToolsConfig_GameSign
  disabled?: boolean
  onFieldChange?: <K extends keyof ToolsConfig_GameSign>(
    key: K,
    value: ToolsConfig_GameSign[K]
  ) => void | Promise<void>
  onRefreshConfig?: () => Promise<void>
}>()

const logger = window.electronAPI.getLogger('游戏社区')
const signLoading = ref(false)
const notifySaving = ref(false)
const credentialToolDescription = computed(() => t('gamesign.section.toolDesc'))
const credentialPrivacyNotice = computed(() => t('gamesign.section.privacyNotice'))

// ==================== 账号管理 ====================

interface AccountInstance {
  uid: string
  type: string
  Name: string
  Enabled: boolean
  MiyousheToken: string
  MiyousheDeviceId: string
  MiyousheDeviceFp: string
  CloudGenshinToken: string
  KuroToken: string
  SklandToken: string
  TaygedoToken: string
}

interface AccountListInstance {
  uid?: unknown
  type?: unknown
}

interface AccountListData {
  instances?: AccountListInstance[]
  [key: string]: unknown
}

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}

const asString = (value: unknown) => (typeof value === 'string' ? value : '')

const {
  addAccount,
  updateAccount,
  sendKuroSmsCode,
  loginKuroSms,
  loginTaygedo,
  loginSkland,
  deleteAccount,
} = useGameSignAccountApi()
const { listAccounts, reorderAccounts, manualSign } = useGameSignApi()
const accounts = ref<AccountInstance[]>([])
const addLoading = ref(false)
const isDragging = ref(false)
const credentialAction = ref<
  'kuro-sms-send' | 'kuro-sms-login' | 'taygedo-login' | 'skland-login' | null
>(null)

const loadAccounts = async () => {
  try {
    const response = await listAccounts()
    if (response.code !== 200) return
    const data = response.data as unknown as AccountListData | undefined
    const instances: AccountInstance[] = []
    const instanceList = Array.isArray(data?.instances) ? data.instances : []
    for (const inst of instanceList) {
      const uid = asString(inst.uid)
      if (!uid) continue
      const accountData = asRecord(asRecord(data?.[uid]).GameSignAccount)
      instances.push({
        uid,
        type: asString(inst.type) || 'GameSignAccountGroup',
        Name: asString(accountData.Name) || t('gamesign.defaultUserName'),
        Enabled: typeof accountData.Enabled === 'boolean' ? accountData.Enabled : true,
        MiyousheToken: asString(accountData.MiyousheToken),
        MiyousheDeviceId: asString(accountData.MiyousheDeviceId),
        MiyousheDeviceFp: asString(accountData.MiyousheDeviceFp),
        CloudGenshinToken: asString(accountData.CloudGenshinToken),
        KuroToken: asString(accountData.KuroToken),
        SklandToken: asString(accountData.SklandToken),
        TaygedoToken: asString(accountData.TaygedoToken),
      })
    }
    accounts.value = instances
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载用户列表失败: ${errorMsg}`)
  }
}

const getAccountAllData = (account: AccountInstance): GameSignAccountGroupConfig => ({
  Name: account.Name,
  Enabled: account.Enabled,
  MiyousheToken: account.MiyousheToken,
  MiyousheDeviceId: account.MiyousheDeviceId,
  MiyousheDeviceFp: account.MiyousheDeviceFp,
  CloudGenshinToken: account.CloudGenshinToken,
  KuroToken: account.KuroToken,
  SklandToken: account.SklandToken,
  TaygedoToken: account.TaygedoToken,
})

const handleAddAccount = async () => {
  addLoading.value = true
  try {
    const result = await addAccount()
    if (result) {
      const defaultName = t('gamesign.newUserName', { n: accounts.value.length + 1 })
      const data = result.data || {}
      const newAccount: AccountInstance = {
        uid: result.accountId,
        type: 'GameSignAccountGroup',
        Name: data.Name || defaultName,
        Enabled: data.Enabled ?? true,
        MiyousheToken: data.MiyousheToken || '',
        MiyousheDeviceId: data.MiyousheDeviceId || '',
        MiyousheDeviceFp: data.MiyousheDeviceFp || '',
        CloudGenshinToken: data.CloudGenshinToken || '',
        KuroToken: data.KuroToken || '',
        SklandToken: data.SklandToken || '',
        TaygedoToken: data.TaygedoToken || '',
      }
      accounts.value.push(newAccount)
      message.success(t('gamesign.toast.userAdded'))
      openEditModal(newAccount)
    }
  } finally {
    addLoading.value = false
  }
}

const handleDeleteAccount = (account: AccountInstance) => {
  Modal.confirm({
    title: t('gamesign.toast.deleteTitle'),
    content: t('gamesign.toast.deleteContent', { name: account.Name }),
    okText: t('gamesign.list.del'),
    okType: 'danger',
    cancelText: t('common.cancel'),
    onOk: async () => {
      await deleteAccount(account.uid)
      accounts.value = accounts.value.filter(a => a.uid !== account.uid)
    },
  })
}

const handleAccountEnabledChange = async (account: AccountInstance, enabled: boolean) => {
  const previousEnabled = account.Enabled
  account.Enabled = enabled
  try {
    await updateAccount(account.uid, { Enabled: enabled })
  } catch {
    account.Enabled = previousEnabled
    message.error(t('gamesign.toast.saveFailed'))
  }
}

// ==================== 拖拽排序 ====================

interface DragEndEvent {
  oldIndex?: number | null
  newIndex?: number | null
}

const onDragEnd = async (evt: DragEndEvent) => {
  if (evt.oldIndex === evt.newIndex) return
  isDragging.value = true
  try {
    const order = accounts.value.map(a => a.uid)
    const response = await reorderAccounts(order)
    if (response.code !== 200) {
      throw new Error(response.message || t('gamesign.toast.reorderFailed'))
    }
    logger.info('用户排序已保存')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`排序保存失败: ${errorMsg}`)
    message.error(t('gamesign.toast.reorderError', { error: errorMsg }))
    await loadAccounts()
  } finally {
    isDragging.value = false
  }
}

// ==================== 编辑 Token 模态框 ====================

const editModalVisible = ref(false)
const editingAccount = ref<AccountInstance | null>(null)
const kuroSmsModalVisible = ref(false)
const kuroSmsAccountId = ref('')
const kuroSmsPhone = ref('')
const kuroSmsCode = ref('')
const kuroSmsSessionId = ref('')
const kuroSmsExpiresIn = ref(0)
const kuroSmsResendIn = ref(0)
const kuroSmsRequiresVerification = ref(false)
const taygedoLoginModalVisible = ref(false)
const taygedoLoginAccountId = ref('')
const taygedoLoginPhone = ref('')
const taygedoLoginPassword = ref('')
const sklandLoginModalVisible = ref(false)
const sklandLoginAccountId = ref('')
const sklandLoginPhone = ref('')
const sklandLoginPassword = ref('')
let kuroSmsCountdownTimer: ReturnType<typeof setInterval> | undefined
let kuroSmsRequestGeneration = 0

const stopKuroSmsCountdown = () => {
  if (kuroSmsCountdownTimer !== undefined) {
    clearInterval(kuroSmsCountdownTimer)
    kuroSmsCountdownTimer = undefined
  }
}

const startKuroSmsCountdown = (expiresIn: number) => {
  stopKuroSmsCountdown()
  kuroSmsExpiresIn.value = expiresIn
  kuroSmsResendIn.value = 60
  kuroSmsCountdownTimer = setInterval(() => {
    kuroSmsExpiresIn.value = Math.max(0, kuroSmsExpiresIn.value - 1)
    kuroSmsResendIn.value = Math.max(0, kuroSmsResendIn.value - 1)
    if (kuroSmsExpiresIn.value === 0) {
      kuroSmsSessionId.value = ''
      kuroSmsCode.value = ''
      kuroSmsRequiresVerification.value = false
      stopKuroSmsCountdown()
    }
  }, 1000)
}

const closeKuroSmsModal = () => {
  kuroSmsRequestGeneration += 1
  stopKuroSmsCountdown()
  kuroSmsModalVisible.value = false
  kuroSmsAccountId.value = ''
  kuroSmsPhone.value = ''
  kuroSmsCode.value = ''
  kuroSmsSessionId.value = ''
  kuroSmsExpiresIn.value = 0
  kuroSmsResendIn.value = 0
  kuroSmsRequiresVerification.value = false
  credentialAction.value = null
}

const closeTaygedoLoginModal = () => {
  taygedoLoginModalVisible.value = false
  taygedoLoginAccountId.value = ''
  taygedoLoginPhone.value = ''
  taygedoLoginPassword.value = ''
  credentialAction.value = null
}

const closeSklandLoginModal = () => {
  sklandLoginModalVisible.value = false
  sklandLoginAccountId.value = ''
  sklandLoginPhone.value = ''
  sklandLoginPassword.value = ''
  credentialAction.value = null
}

const openTaygedoLoginModal = () => {
  if (!editingAccount.value) return
  taygedoLoginAccountId.value = editingAccount.value.uid
  taygedoLoginPhone.value = ''
  taygedoLoginPassword.value = ''
  taygedoLoginModalVisible.value = true
}

const openKuroSmsModal = () => {
  if (!editingAccount.value) return
  kuroSmsRequestGeneration += 1
  kuroSmsAccountId.value = editingAccount.value.uid
  kuroSmsPhone.value = ''
  kuroSmsCode.value = ''
  kuroSmsSessionId.value = ''
  kuroSmsExpiresIn.value = 0
  kuroSmsResendIn.value = 0
  kuroSmsRequiresVerification.value = false
  kuroSmsModalVisible.value = true
}

const openSklandLoginModal = () => {
  if (!editingAccount.value) return
  sklandLoginAccountId.value = editingAccount.value.uid
  sklandLoginPhone.value = ''
  sklandLoginPassword.value = ''
  sklandLoginModalVisible.value = true
}

const openEditModal = (account: AccountInstance) => {
  closeKuroSmsModal()
  closeTaygedoLoginModal()
  closeSklandLoginModal()
  editingAccount.value = { ...account }
  editModalVisible.value = true
}

const handleEditModalCancel = () => {
  closeQrModal()
  closeKuroSmsModal()
  closeTaygedoLoginModal()
  closeSklandLoginModal()
  editModalVisible.value = false
  editingAccount.value = null
}

const handleEditModalOk = async () => {
  if (!editingAccount.value) return
  try {
    const uid = editingAccount.value.uid
    const idx = accounts.value.findIndex(a => a.uid === uid)
    const accountData = getAccountAllData(editingAccount.value)
    await updateAccount(uid, accountData)
    if (idx >= 0) {
      accounts.value[idx] = { ...editingAccount.value }
    }
    message.success(t('gamesign.toast.tokenSaved'))
    closeQrModal()
    closeKuroSmsModal()
    editModalVisible.value = false
    editingAccount.value = null
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 Token 失败: ${errorMsg}`)
    message.error(t('gamesign.toast.saveFailed'))
  }
}

const openKuroVerification = async () => {
  const sessionId = kuroSmsSessionId.value
  if (!sessionId) {
    message.warning(t('gamesign.toast.needKuroSession'))
    return
  }
  try {
    const result = await window.electronAPI.openKuroLogin(sessionId)
    if (result.success) return
    logger.error('打开库街区验证页失败')
    message.error(t('gamesign.login.kuroVerificationOpenFailed'))
  } catch {
    logger.error('调用库街区验证窗口失败')
    message.error(t('gamesign.login.kuroVerificationOpenFailed'))
  }
}

const handleSendKuroSmsCode = async () => {
  const accountId = kuroSmsAccountId.value
  const phone = kuroSmsPhone.value.trim()
  if (!accountId) return
  if (!/^1\d{10}$/.test(phone)) {
    message.warning(t('gamesign.toast.needKuroPhone'))
    return
  }
  const requestGeneration = ++kuroSmsRequestGeneration
  credentialAction.value = 'kuro-sms-send'
  try {
    const result = await sendKuroSmsCode(accountId, phone)
    if (
      requestGeneration !== kuroSmsRequestGeneration ||
      !kuroSmsModalVisible.value ||
      kuroSmsAccountId.value !== accountId
    ) {
      return
    }
    kuroSmsPhone.value = phone
    kuroSmsSessionId.value = result.sessionId
    kuroSmsRequiresVerification.value = result.requiresVerification
    kuroSmsCode.value = ''
    startKuroSmsCountdown(result.expiresIn)
    if (result.requiresVerification) {
      await openKuroVerification()
    }
  } catch {
    // sendKuroSmsCode 已展示脱敏错误，保留弹窗供用户重试。
  } finally {
    if (requestGeneration === kuroSmsRequestGeneration) {
      credentialAction.value = null
    }
  }
}

const handleKuroSmsLogin = async () => {
  const accountId = kuroSmsAccountId.value
  const sessionId = kuroSmsSessionId.value
  const phone = kuroSmsPhone.value.trim()
  const code = kuroSmsCode.value.trim()
  if (!accountId) return
  if (!sessionId) {
    message.warning(t('gamesign.toast.needKuroSession'))
    return
  }
  if (!/^\d{4,8}$/.test(code)) {
    message.warning(t('gamesign.toast.needKuroCode'))
    return
  }
  const requestGeneration = ++kuroSmsRequestGeneration
  credentialAction.value = 'kuro-sms-login'
  try {
    await loginKuroSms(accountId, sessionId, phone, code)
    if (
      requestGeneration !== kuroSmsRequestGeneration ||
      !kuroSmsModalVisible.value ||
      kuroSmsAccountId.value !== accountId
    ) {
      return
    }
    await loadAccounts()
    if (
      requestGeneration !== kuroSmsRequestGeneration ||
      !kuroSmsModalVisible.value ||
      kuroSmsAccountId.value !== accountId
    ) {
      return
    }
    const updated = accounts.value.find(item => item.uid === accountId)
    if (updated && editingAccount.value?.uid === accountId) {
      editingAccount.value = { ...updated }
    }
    closeKuroSmsModal()
  } catch {
    // loginKuroSms 已展示脱敏错误，保留短期会话供用户修正验证码。
  } finally {
    if (requestGeneration === kuroSmsRequestGeneration) {
      kuroSmsCode.value = ''
      credentialAction.value = null
    }
  }
}

const handleTaygedoLogin = async () => {
  const accountId = taygedoLoginAccountId.value
  const phone = taygedoLoginPhone.value.trim()
  const password = taygedoLoginPassword.value
  if (!accountId) return
  if (!phone || !password) {
    message.warning(t('gamesign.toast.needTaygedoCredential'))
    return
  }
  credentialAction.value = 'taygedo-login'
  try {
    await loginTaygedo(accountId, phone, password)
    await loadAccounts()
    const updated = accounts.value.find(item => item.uid === accountId)
    if (updated && editingAccount.value?.uid === accountId) {
      editingAccount.value = { ...updated }
    }
    closeTaygedoLoginModal()
  } catch {
    // loginTaygedo 已展示错误提示，保留二级弹窗供用户重新输入。
  } finally {
    taygedoLoginPhone.value = ''
    taygedoLoginPassword.value = ''
    credentialAction.value = null
  }
}

const handleSklandLogin = async () => {
  const accountId = sklandLoginAccountId.value
  const phone = sklandLoginPhone.value.trim()
  const password = sklandLoginPassword.value
  if (!accountId) return
  if (!phone || !password) {
    message.warning(t('gamesign.toast.needSklandCredential'))
    return
  }
  credentialAction.value = 'skland-login'
  try {
    await loginSkland(accountId, phone, password)
    await loadAccounts()
    const updated = accounts.value.find(item => item.uid === accountId)
    if (updated && editingAccount.value?.uid === accountId) {
      editingAccount.value = { ...updated }
    }
    closeSklandLoginModal()
  } catch {
    // loginSkland 已展示错误提示，保留二级弹窗供用户重新输入。
  } finally {
    sklandLoginPhone.value = ''
    sklandLoginPassword.value = ''
    credentialAction.value = null
  }
}

// ==================== 米游社扫码登录 ====================
// 会话状态机在 useQrLogin，弹窗在 QrLoginModal，这里只提供「存到哪个账号」
// 和存完之后的本地同步。沿用原来的变量名，模板不用改。

const {
  visible: qrModalVisible,
  loading: qrLoading,
  status: qrStatus,
  statusText: qrStatusText,
  qrCodeDataUrl,
  start: startQrLogin,
  cancel: closeQrModal,
} = useQrLogin({
  getAccountId: () => editingAccount.value?.uid,
  onSaved: async (accountId, cookiesStr, isStillCurrent) => {
    if (editingAccount.value?.uid === accountId) {
      editingAccount.value.MiyousheToken = cookiesStr
    }
    await loadAccounts()
    if (!isStillCurrent()) return
    const savedAccount = accounts.value.find(account => account.uid === accountId)
    if (savedAccount && editingAccount.value?.uid === accountId) {
      editingAccount.value = { ...savedAccount }
    }
    if (onRefreshConfig) {
      await onRefreshConfig()
    }
  },
  logger,
})

// ==================== 签到结果解析（按用户绑定） ====================
// 解析与聚合逻辑都在 gameSignDisplay.ts，这里只负责接上响应式

const signResult = computed(() => parseSignResult(config.Result))

// 预计算每个用户的社区标签，signResult 或 accounts 变化时自动重算
const userTagsMap = computed(() => buildUserTagsMap(accounts.value, signResult.value))

// 获取某用户的所有社区标签（响应式版本）
const getUserPlatformTagsReactive = (account: AccountInstance): PlatformTag[] => {
  return userTagsMap.value.get(account.uid) || []
}

// 获取某用户在某社区的账号组（响应式版本，用于 Tooltip）
const getAccountGroupsForPlatformReactive = (
  account: AccountInstance,
  platform: string
): AccountGroup[] => {
  const tags = userTagsMap.value.get(account.uid) || []
  const tag = tags.find(t => t.platform === platform)
  return tag?.groups || []
}

// ==================== 通用变更处理 ====================

const handleChange = async <K extends keyof ToolsConfig_GameSign>(
  key: K,
  value: ToolsConfig_GameSign[K]
) => {
  if (!onFieldChange) return

  try {
    await onFieldChange(key, value)
  } catch {
    // updateTools 已显示错误，父组件负责回滚配置
  }
}

const handleNotifyEnabledChange = async (value: boolean) => {
  if (!onFieldChange) return

  notifySaving.value = true
  try {
    await handleChange('NotifyEnabled', value)
  } finally {
    notifySaving.value = false
  }
}

// ==================== 手动签到 ====================

const handleManualSign = async () => {
  signLoading.value = true
  try {
    const response = await manualSign()
    if (response.code === 409) {
      const warning = response.message || t('gamesign.toast.autoSignRunning')
      logger.warn(`手动签到被拒绝: ${warning}`)
      message.warning(warning)
      return
    }
    if (response.code !== 200 && response.code !== 0) {
      throw new Error(response.message || t('gamesign.toast.signFailed'))
    }
    logger.info('游戏社区签到完成')
    if (response.status === 'warning') {
      message.warning(response.message || t('gamesign.toast.signPartialNotify'))
    } else {
      message.success(response.message || t('gamesign.toast.signDone'))
    }
    // 立即刷新签到结果（不等父组件轮询）
    if (onRefreshConfig) await onRefreshConfig()
    await loadAccounts()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`签到失败: ${errorMsg}`)
    message.error(t('gamesign.toast.signError', { error: errorMsg }))
  } finally {
    signLoading.value = false
  }
}

// ==================== 生命周期 ====================

onMounted(() => {
  loadAccounts()
})

onBeforeUnmount(() => {
  stopKuroSmsCountdown()
})
</script>

<template>
  <div class="tab-content">
    <!-- 全局设置区 -->
    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('gamesign.section.settings') }}</h3>
        <div class="section-header-actions">
          <DocLink :url="MAS_DOC_URLS.gameSign" />
          <a-button
            type="primary"
            size="small"
            class="section-update-button primary-style"
            :loading="signLoading"
            :disabled="disabled || !config.Enabled"
            @click="handleManualSign"
          >
            <template #icon><SwapOutlined /></template>
            {{ t('gamesign.section.signAll') }}
          </a-button>
        </div>
      </div>
      <a-alert class="game-sign-notice" type="info" show-icon>
        <template #message>{{ t('gamesign.section.noticeTitle') }}</template>
        <template #description>
          <div>{{ credentialToolDescription }}</div>
          <div>{{ credentialPrivacyNotice }}</div>
        </template>
      </a-alert>
      <div class="settings-list">
        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-title">{{ t('gamesign.section.enable') }}</span>
            <span class="setting-desc">{{ t('gamesign.section.enableDesc') }}</span>
          </div>
          <a-switch
            :checked="config.Enabled"
            :disabled="disabled"
            @change="handleChange('Enabled', $event)"
          />
        </div>
        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-title">{{ t('gamesign.section.notify') }}</span>
            <span class="setting-desc">{{ t('gamesign.section.notifyDesc') }}</span>
          </div>
          <a-switch
            :checked="config.NotifyEnabled"
            :disabled="disabled"
            :loading="notifySaving"
            @change="handleNotifyEnabledChange"
          />
        </div>
        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-title">{{ t('gamesign.section.runOnStartup') }}</span>
            <span class="setting-desc">{{ t('gamesign.section.runOnStartupDesc') }}</span>
          </div>
          <a-switch
            :checked="config.RunOnStartup"
            :disabled="disabled"
            @change="handleChange('RunOnStartup', $event)"
          />
        </div>
        <div class="setting-row setting-row-static">
          <div class="setting-info">
            <span class="setting-title">{{ t('gamesign.section.lastSign') }}</span>
            <span class="setting-desc">{{ t('gamesign.section.lastSignDesc') }}</span>
          </div>
          <span class="setting-value">{{
            config.LastSignDate && config.LastSignDate !== '2000-01-01'
              ? config.LastSignDate
              : t('gamesign.section.neverSigned')
          }}</span>
        </div>
      </div>
    </div>

    <!-- 用户列表 -->
    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('gamesign.list.title') }}</h3>
        <a-button
          type="primary"
          ghost
          size="middle"
          :loading="addLoading"
          :disabled="disabled"
          @click="handleAddAccount"
        >
          <template #icon><PlusOutlined /></template>
          {{ t('gamesign.list.add') }}
        </a-button>
      </div>

      <div class="user-table-container">
        <!-- 表头 -->
        <div class="user-table-header">
          <div class="header-cell drag-cell"></div>
          <div class="header-cell name-cell">{{ t('gamesign.list.colName') }}</div>
          <div class="header-cell status-cell">{{ t('gamesign.list.colEnabled') }}</div>
          <div class="header-cell tags-cell">{{ t('gamesign.list.colTags') }}</div>
          <div class="header-cell actions-cell">{{ t('gamesign.list.colActions') }}</div>
        </div>

        <!-- 拖拽内容 -->
        <draggable
          v-model="accounts"
          item-key="uid"
          :animation="200"
          :disabled="disabled || isDragging"
          ghost-class="user-ghost"
          chosen-class="user-chosen"
          drag-class="user-drag"
          handle=".drag-handle"
          class="user-draggable"
          @end="onDragEnd"
        >
          <template #item="{ element: account }">
            <div class="user-row">
              <!-- 拖拽手柄 -->
              <div class="row-cell drag-cell">
                <span class="drag-handle" :title="t('gamesign.list.drag')">
                  <span class="drag-dots"></span>
                </span>
              </div>
              <!-- 用户名 -->
              <div class="row-cell name-cell">
                <span class="user-name-text">{{ account.Name }}</span>
              </div>
              <!-- 启用开关 -->
              <div class="row-cell status-cell">
                <a-switch
                  :checked="account.Enabled"
                  :disabled="disabled"
                  @change="handleAccountEnabledChange(account, $event)"
                />
              </div>
              <!-- 社区签到情况（标签云） -->
              <div class="row-cell tags-cell">
                <a-space :size="6" wrap>
                  <a-tooltip
                    v-for="tag in getUserPlatformTagsReactive(account)"
                    :key="tag.platform"
                    overlay-class-name="game-sign-tooltip-overlay"
                  >
                    <template #title>
                      <div class="sign-tooltip">
                        <div class="sign-tooltip-title">
                          {{ t('gamesign.list.tooltipTitle', { platform: tag.platform }) }}
                        </div>
                        <template
                          v-for="(group, gIdx) in getAccountGroupsForPlatformReactive(
                            account,
                            tag.platform
                          )"
                          :key="gIdx"
                        >
                          <template
                            v-for="game in group.games"
                            :key="`${game.account || group.account_alias}-${game.game}`"
                          >
                            <div class="sign-tooltip-alias">
                              {{ getSignDetailAlias(group, game, t('gamesign.unknownUser')) }}
                            </div>
                            <div class="sign-tooltip-row">
                              <span>{{ game.game }}</span>
                              <span :class="getSignDetailClass(game.status)">
                                ● {{ t(getSignStatusKey(game.status)) }}
                              </span>
                              <span v-if="game.reward" class="tt-reward">{{ game.reward }}</span>
                            </div>
                          </template>
                        </template>
                        <div v-if="tag.games.length === 0" class="sign-tooltip-empty">
                          {{ t('gamesign.list.noSignData') }}
                        </div>
                      </div>
                    </template>
                    <span :class="['platform-tag', getTagClass(tag.status)]">
                      {{ getTagText(tag) }}
                    </span>
                  </a-tooltip>
                </a-space>
              </div>
              <!-- 操作 -->
              <div class="row-cell actions-cell">
                <a-space :size="8">
                  <a-button
                    size="middle"
                    class="action-btn edit-btn"
                    @click="openEditModal(account)"
                  >
                    <template #icon><EditOutlined /></template>
                    {{ t('gamesign.list.edit') }}
                  </a-button>
                  <a-button
                    size="middle"
                    class="action-btn delete-btn"
                    @click="handleDeleteAccount(account)"
                  >
                    <template #icon><DeleteOutlined /></template>
                    {{ t('gamesign.list.del') }}
                  </a-button>
                </a-space>
              </div>
            </div>
          </template>
        </draggable>

        <!-- 空状态 -->
        <div v-if="accounts.length === 0" class="empty-state">
          <div class="empty-hint">{{ t('gamesign.list.empty') }}</div>
          <div class="empty-guide">{{ t('gamesign.list.emptyGuide') }}</div>
        </div>
      </div>
    </div>

    <!-- 编辑 Token 模态框 -->
    <a-modal
      v-model:open="editModalVisible"
      :title="t('gamesign.edit.title', { name: editingAccount?.Name || '' })"
      :ok-text="t('gamesign.edit.save')"
      :cancel-text="t('common.cancel')"
      :width="560"
      :body-style="{ maxHeight: 'calc(100vh - 180px)', overflowY: 'auto' }"
      centered
      @ok="handleEditModalOk"
      @cancel="handleEditModalCancel"
    >
      <div v-if="editingAccount" class="modal-form">
        <div class="form-item-vertical">
          <span class="form-label">{{ t('gamesign.edit.userName') }}</span>
          <a-input v-model:value="editingAccount.Name" size="large" />
        </div>
        <a-divider orientation="left" class="community-divider">{{
          t('gamesign.edit.miyoushe')
        }}</a-divider>
        <div class="form-item-vertical">
          <a-input-password
            v-model:value="editingAccount.MiyousheToken"
            size="large"
            :placeholder="t('gamesign.edit.miyoushePlaceholder')"
            allow-clear
          />
          <a-button
            size="small"
            danger
            class="credential-helper-btn"
            style="margin-top: 6px"
            :loading="qrLoading"
            @click="startQrLogin"
          >
            <template #icon><QrcodeOutlined /></template>
            {{ t('gamesign.edit.qrLogin') }}
          </a-button>
        </div>
        <a-divider orientation="left" class="community-divider">{{
          t('gamesign.edit.kuro')
        }}</a-divider>
        <div class="form-item-vertical">
          <a-input-password
            v-model:value="editingAccount.KuroToken"
            size="large"
            :placeholder="t('gamesign.edit.kuroPlaceholder')"
            allow-clear
          />
          <a-button
            size="small"
            danger
            class="credential-helper-btn"
            style="margin-top: 6px"
            :loading="credentialAction === 'kuro-sms-send'"
            :disabled="credentialAction !== null"
            @click="openKuroSmsModal"
          >
            <template #icon><MessageOutlined /></template>
            {{ t('gamesign.edit.smsLogin') }}
          </a-button>
        </div>
        <a-divider orientation="left" class="community-divider">{{
          t('gamesign.edit.skland')
        }}</a-divider>
        <div class="form-item-vertical">
          <a-input-password
            v-model:value="editingAccount.SklandToken"
            size="large"
            :placeholder="t('gamesign.edit.sklandPlaceholder')"
            allow-clear
          />
          <a-button
            size="small"
            danger
            class="credential-helper-btn"
            style="margin-top: 6px"
            :loading="credentialAction === 'skland-login'"
            :disabled="credentialAction !== null"
            @click="openSklandLoginModal"
          >
            {{ t('gamesign.edit.passwordLogin') }}
          </a-button>
        </div>
        <a-divider orientation="left" class="community-divider">{{
          t('gamesign.edit.taygedo')
        }}</a-divider>
        <div class="form-item-vertical">
          <a-input-password
            v-model:value="editingAccount.TaygedoToken"
            size="large"
            :placeholder="t('gamesign.edit.taygedoPlaceholder')"
            allow-clear
          />
          <a-button
            size="small"
            danger
            class="credential-helper-btn"
            style="margin-top: 6px"
            :loading="credentialAction === 'taygedo-login'"
            :disabled="credentialAction !== null"
            @click="openTaygedoLoginModal"
          >
            {{ t('gamesign.edit.passwordLogin') }}
          </a-button>
        </div>
      </div>
    </a-modal>

    <!-- 库街区短信验证码获取 Token 弹窗 -->
    <a-modal
      v-model:open="kuroSmsModalVisible"
      :title="t('gamesign.login.kuroTitle')"
      :footer="null"
      :width="440"
      @cancel="closeKuroSmsModal"
    >
      <div class="modal-form">
        <a-alert class="credential-disclaimer" type="warning" show-icon>
          <template #message>{{ t('gamesign.login.smsDisclaimerTitle') }}</template>
          <template #description>{{ credentialPrivacyNotice }}</template>
        </a-alert>
        <a-alert type="warning" show-icon :message="t('gamesign.login.kuroConflictNotice')" />
        <div class="form-item-vertical">
          <span class="form-label">{{ t('gamesign.login.currentAccount') }}</span>
          <a-input :value="editingAccount?.Name || ''" disabled />
        </div>
        <div class="form-item-vertical">
          <span class="form-label">{{ t('gamesign.login.kuroPhone') }}</span>
          <div class="sms-send-row">
            <a-input
              v-model:value="kuroSmsPhone"
              autocomplete="tel"
              inputmode="numeric"
              :maxlength="11"
              :disabled="Boolean(kuroSmsSessionId)"
              :placeholder="t('gamesign.login.kuroPhonePlaceholder')"
              allow-clear
            />
            <a-button
              danger
              class="sms-send-button credential-helper-btn"
              :loading="credentialAction === 'kuro-sms-send'"
              :disabled="credentialAction !== null || kuroSmsResendIn > 0"
              @click="handleSendKuroSmsCode"
            >
              {{
                kuroSmsResendIn > 0
                  ? t('gamesign.login.resendAfter', { seconds: kuroSmsResendIn })
                  : kuroSmsSessionId
                    ? t('gamesign.login.resendCode')
                    : t('gamesign.login.sendCode')
              }}
            </a-button>
          </div>
        </div>
        <a-alert
          v-if="kuroSmsSessionId"
          type="info"
          show-icon
          :message="t('gamesign.login.kuroSessionHint', { seconds: kuroSmsExpiresIn })"
        />
        <a-alert
          v-if="kuroSmsRequiresVerification"
          type="warning"
          show-icon
          :message="t('gamesign.login.kuroVerificationHint')"
        >
          <template #action>
            <a-button danger size="small" @click="openKuroVerification">
              {{ t('gamesign.login.openKuroVerification') }}
            </a-button>
          </template>
        </a-alert>
        <div class="form-item-vertical">
          <span class="form-label">{{ t('gamesign.login.smsCode') }}</span>
          <a-input
            v-model:value="kuroSmsCode"
            autocomplete="one-time-code"
            inputmode="numeric"
            :maxlength="8"
            :disabled="!kuroSmsSessionId"
            :placeholder="t('gamesign.login.smsCodePlaceholder')"
            allow-clear
            @press-enter="handleKuroSmsLogin"
          />
        </div>
        <a-space style="width: 100%; justify-content: flex-end">
          <a-button @click="closeKuroSmsModal">{{ t('common.cancel') }}</a-button>
          <a-button
            type="primary"
            danger
            class="credential-helper-btn"
            :loading="credentialAction === 'kuro-sms-login'"
            :disabled="credentialAction !== null || !kuroSmsSessionId"
            @click="handleKuroSmsLogin"
          >
            {{ t('gamesign.login.smsSubmit') }}
          </a-button>
        </a-space>
      </div>
    </a-modal>

    <!-- 塔吉多账号密码登录弹窗 -->
    <a-modal
      v-model:open="taygedoLoginModalVisible"
      :title="t('gamesign.login.taygedoTitle')"
      :footer="null"
      :width="420"
      @cancel="closeTaygedoLoginModal"
    >
      <div class="modal-form">
        <a-alert class="credential-disclaimer" type="warning" show-icon>
          <template #message>{{ t('gamesign.login.disclaimerTitle') }}</template>
          <template #description>{{ credentialPrivacyNotice }}</template>
        </a-alert>
        <div class="form-item-vertical">
          <span class="form-label">{{ t('gamesign.login.currentAccount') }}</span>
          <a-input :value="editingAccount?.Name || ''" disabled />
        </div>
        <div class="form-item-vertical">
          <span class="form-label">{{ t('gamesign.login.taygedoAccount') }}</span>
          <a-input
            v-model:value="taygedoLoginPhone"
            autocomplete="off"
            :placeholder="t('gamesign.login.taygedoAccountPlaceholder')"
            allow-clear
          />
        </div>
        <div class="form-item-vertical">
          <span class="form-label">{{ t('gamesign.login.password') }}</span>
          <a-input-password
            v-model:value="taygedoLoginPassword"
            autocomplete="new-password"
            :placeholder="t('gamesign.login.taygedoPasswordPlaceholder')"
            allow-clear
          />
        </div>
        <a-space style="width: 100%; justify-content: flex-end">
          <a-button @click="closeTaygedoLoginModal">{{ t('common.cancel') }}</a-button>
          <a-button
            type="primary"
            danger
            class="credential-helper-btn"
            :loading="credentialAction === 'taygedo-login'"
            :disabled="credentialAction !== null"
            @click="handleTaygedoLogin"
          >
            {{ t('gamesign.login.submit') }}
          </a-button>
        </a-space>
      </div>
    </a-modal>

    <!-- 森空岛账密获取 Token 弹窗 -->
    <a-modal
      v-model:open="sklandLoginModalVisible"
      :title="t('gamesign.login.sklandTitle')"
      :footer="null"
      :width="420"
      @cancel="closeSklandLoginModal"
    >
      <div class="modal-form">
        <a-alert class="credential-disclaimer" type="warning" show-icon>
          <template #message>{{ t('gamesign.login.disclaimerTitle') }}</template>
          <template #description>{{ credentialPrivacyNotice }}</template>
        </a-alert>
        <div class="form-item-vertical">
          <span class="form-label">{{ t('gamesign.login.currentAccount') }}</span>
          <a-input :value="editingAccount?.Name || ''" disabled />
        </div>
        <div class="form-item-vertical">
          <span class="form-label">{{ t('gamesign.login.sklandPhone') }}</span>
          <a-input
            v-model:value="sklandLoginPhone"
            autocomplete="off"
            :placeholder="t('gamesign.login.sklandPhonePlaceholder')"
            allow-clear
          />
        </div>
        <div class="form-item-vertical">
          <span class="form-label">{{ t('gamesign.login.password') }}</span>
          <a-input-password
            v-model:value="sklandLoginPassword"
            autocomplete="new-password"
            :placeholder="t('gamesign.login.sklandPasswordPlaceholder')"
            allow-clear
          />
        </div>
        <a-space style="width: 100%; justify-content: flex-end">
          <a-button @click="closeSklandLoginModal">{{ t('common.cancel') }}</a-button>
          <a-button
            type="primary"
            danger
            class="credential-helper-btn"
            :loading="credentialAction === 'skland-login'"
            :disabled="credentialAction !== null"
            @click="handleSklandLogin"
          >
            {{ t('gamesign.login.submit') }}
          </a-button>
        </a-space>
      </div>
    </a-modal>

    <!-- 扫码登录弹窗 -->
    <QrLoginModal
      :open="qrModalVisible"
      :status="qrStatus"
      :status-text="qrStatusText"
      :qr-code-data-url="qrCodeDataUrl"
      :loading="qrLoading"
      @cancel="closeQrModal"
      @retry="startQrLogin"
    />
  </div>
</template>

<style scoped>
/* 布尔设置统一使用 Ant Design 开关，避免同类值出现不同交互。 */

.section-header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

/* 复用新版通知页的页眉操作按钮规格，保持文档入口和主操作高度一致。 */
.section-header-actions .section-update-button {
  height: 32px;
  padding: 4px 8px;
  font-size: 14px;
  font-weight: 500;
  line-height: 1;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.section-header-actions .section-update-button.primary-style {
  background: var(--ant-color-primary);
  border: 1px solid var(--ant-color-primary);
  color: #fff;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.18);
  transition:
    transform 0.16s ease,
    box-shadow 0.16s ease;
}

.section-header-actions .section-update-button.primary-style:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(22, 119, 255, 0.22);
}

.section-header-actions .section-update-button.primary-style:disabled {
  transform: none;
  box-shadow: none;
}

/* ==================== 签到设置（开关列表） ==================== */
.settings-list {
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--ant-color-bg-container);
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.setting-row:last-child {
  border-bottom: none;
}

.setting-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.setting-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.setting-desc {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.setting-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
}

/* ==================== 用户列表表格 ==================== */
.user-table-container {
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  overflow: hidden;
  background: var(--ant-color-bg-container);
}

.user-table-header {
  display: flex;
  align-items: center;
  background-color: var(--ant-color-fill-quaternary);
  border-bottom: 1px solid var(--ant-color-border);
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
  min-height: 48px;
}

.user-table-header .header-cell {
  padding: 12px 16px;
  border-right: 1px solid var(--ant-color-border);
}

.user-table-header .header-cell:last-child {
  border-right: none;
}

.drag-cell {
  width: 36px;
  min-width: 36px;
  max-width: 36px;
  text-align: center;
}
.name-cell {
  width: 140px;
  min-width: 140px;
  text-align: center;
}
.status-cell {
  width: 80px;
  min-width: 80px;
  text-align: center;
  justify-content: center;
}
.tags-cell {
  flex: 1;
  min-width: 0;
}
.actions-cell {
  width: 200px;
  min-width: 200px;
  text-align: center;
}

.user-draggable {
  min-height: 60px;
}

.user-row {
  display: flex;
  align-items: center;
  min-height: 64px;
  border-bottom: 1px solid var(--ant-color-border);
  padding: 0;
  transition: background 0.2s ease;
  cursor: default;
  background: var(--ant-color-bg-container);
}

.user-row:last-child {
  border-bottom: none;
}
.user-row:hover {
  background-color: var(--ant-color-fill-quaternary);
}

.row-cell {
  padding: 14px 16px;
  text-align: center;
  border-right: 1px solid var(--ant-color-border);
  display: flex;
  align-items: center;
  justify-content: center;
}

.row-cell:last-child {
  border-right: none;
}

.row-cell.name-cell {
  justify-content: center;
}
.row-cell.tags-cell {
  justify-content: flex-start;
  padding-right: 20px;
}
.row-cell.actions-cell {
  justify-content: center;
  padding: 14px 24px;
}

/* 拖拽手柄 - 对齐 TimeSetManager */
.drag-handle {
  width: 16px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-tertiary);
  background: transparent;
  border: none;
  cursor: grab;
  user-select: none;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-dots {
  width: 10px;
  height: 16px;
  display: block;
  background-image: radial-gradient(currentColor 1.2px, transparent 1.2px);
  background-size: 5px 5px;
  opacity: 0.65;
}

.drag-handle:hover .drag-dots {
  opacity: 0.85;
}

/* 拖拽视觉反馈 */
.user-ghost {
  opacity: 0 !important;
  background: transparent !important;
  border-color: transparent !important;
}
.user-chosen {
  cursor: grabbing !important;
}
.user-drag {
  transform: rotate(3deg);
  opacity: 1 !important;
}

/* 用户名 */
.user-name-text {
  font-weight: 600;
  font-size: 14px;
  color: var(--ant-color-text);
}

/* ==================== 社区标签云（小标签 + 红绿黄） ==================== */
.platform-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  min-width: 76px;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  line-height: 1.5;
  border: 1px solid transparent;
  cursor: default;
  white-space: nowrap;
  text-align: center;
  box-sizing: border-box;
}

/* 绿色：签到成功 */
.tag-signed {
  background: #f6ffed;
  border-color: #b7eb8f;
  color: var(--ant-color-success);
}

/* 灰色：有 Token 但暂无签到数据 */
.tag-unsigned {
  background: #f5f5f5;
  border-color: #e8e8e8;
  color: #999;
}

/* 红色：签到失败 */
.tag-failed {
  background: #fff1f0;
  border-color: #ffa39e;
  color: #f5222d;
}

/* 橙色：账号风控 */
.tag-risk {
  background: #fff2e8;
  border-color: #ffbb96;
  color: #e8590c;
}

/* 橙色：部分签到 */
.tag-partial {
  background: #fff7e6;
  border-color: #ffd591;
  color: #fa8c16;
}

/* ==================== Tooltip 签到详情 ==================== */
:global(.game-sign-tooltip-overlay.ant-tooltip) {
  max-width: min(480px, calc(100vw - 32px));
}

:global(.game-sign-tooltip-overlay .ant-tooltip-inner) {
  box-sizing: border-box;
  min-width: min(320px, calc(100vw - 32px));
  max-width: 100%;
}

.sign-tooltip {
  width: 100%;
  min-width: 0;
  color: rgba(255, 255, 255, 0.85);
}
.sign-tooltip-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
  padding-bottom: 8px;
  margin-bottom: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.18);
}
.sign-tooltip-alias {
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
  padding: 4px 0 2px;
  margin-top: 4px;
  overflow-wrap: anywhere;
}
.sign-tooltip-alias:first-of-type {
  margin-top: 0;
}
.sign-tooltip-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) max-content;
  align-items: center;
  width: 100%;
  min-width: 0;
  padding: 2px 0;
  font-size: 13px;
  gap: 12px;
  overflow-wrap: anywhere;
}
.sign-tooltip-row > span:first-child {
  min-width: 0;
}
.sign-tooltip-row > span:nth-child(2) {
  white-space: nowrap;
}
.tt-signed {
  color: var(--ant-color-success);
}
.tt-unsigned {
  color: #d4b106;
}
.tt-risk {
  color: #e8590c;
}
.tt-failed {
  color: #f5222d;
}
.tt-reward {
  grid-column: 1 / -1;
  color: rgba(255, 255, 255, 0.55);
  font-size: 12px;
}
.sign-tooltip-empty {
  color: rgba(255, 255, 255, 0.55);
  font-size: 13px;
  text-align: center;
  padding: 8px 0;
}

/* ==================== 操作按钮 ==================== */
.action-btn {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 13px;
  border: 1px solid;
  background: transparent;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.edit-btn {
  border-color: var(--ant-color-border);
  color: var(--ant-color-text-secondary);
}

.edit-btn:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

.delete-btn {
  border-color: var(--ant-color-error);
  color: var(--ant-color-error);
}

.delete-btn:hover {
  border-color: #ff7875;
  color: #ff7875;
}

/* ==================== 空状态 ==================== */
.empty-state {
  text-align: center;
  padding: 48px 0;
}
.empty-hint {
  color: var(--ant-color-text-tertiary);
  font-size: 15px;
  margin-bottom: 6px;
}
.empty-guide {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

/* ==================== 模态框 ==================== */
.modal-form .form-item-vertical {
  margin-bottom: 16px;
}

.game-sign-notice,
.credential-disclaimer {
  margin-bottom: 16px;
}

.game-sign-notice {
  background: var(--ant-color-bg-container);
  border-color: var(--ant-color-border);
}

.game-sign-notice :deep(.ant-alert-icon),
.game-sign-notice :deep(.ant-alert-message) {
  color: var(--ant-color-text);
}

.game-sign-notice :deep(.ant-alert-description) {
  color: var(--ant-color-text-secondary);
}

.game-sign-notice :deep(.ant-alert-description),
.credential-disclaimer :deep(.ant-alert-description) {
  line-height: 1.6;
}

.credential-helper-btn {
  font-weight: 700;
}

.sms-send-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 136px;
  gap: 8px;
}

.sms-send-button {
  width: 136px;
}

.community-divider {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

@media (max-width: 860px) {
  .section-header-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .setting-row {
    align-items: flex-start;
    padding: 12px 16px;
  }

  .setting-row-static {
    flex-wrap: wrap;
  }

  .user-table-container {
    overflow: visible;
    border: none;
    background: transparent;
  }

  .user-table-header {
    display: none;
  }

  .user-draggable {
    min-height: 0;
  }

  .user-row {
    display: grid;
    grid-template-columns: 32px minmax(0, 1fr) auto;
    align-items: center;
    margin-bottom: 8px;
    border: 1px solid var(--ant-color-border);
    border-radius: 8px;
  }

  .user-row:last-child {
    margin-bottom: 0;
    border-bottom: 1px solid var(--ant-color-border);
  }

  .row-cell {
    width: auto;
    min-width: 0;
    padding: 12px;
    border-right: none;
  }

  .row-cell.drag-cell {
    grid-column: 1;
    grid-row: 1;
    padding: 12px 4px;
  }

  .row-cell.name-cell {
    grid-column: 2;
    grid-row: 1;
    justify-content: flex-start;
    text-align: left;
  }

  .row-cell.status-cell {
    grid-column: 3;
    grid-row: 1;
    padding-left: 4px;
  }

  .row-cell.tags-cell {
    grid-column: 2 / 4;
    grid-row: 2;
    min-width: 0;
    padding: 0 12px 12px;
  }

  .row-cell.tags-cell :deep(.ant-space) {
    display: flex;
    width: 100%;
    justify-content: flex-start;
  }

  .row-cell.actions-cell {
    grid-column: 2 / 4;
    grid-row: 3;
    width: auto;
    min-width: 0;
    justify-content: flex-start;
    padding: 0 12px 12px;
  }

  .empty-state {
    padding: 32px 16px;
    border: 1px solid var(--ant-color-border);
    border-radius: 8px;
    background: var(--ant-color-bg-container);
  }
}

@media (max-width: 480px) {
  .sms-send-row {
    grid-template-columns: minmax(0, 1fr);
  }

  .sms-send-button {
    width: 100%;
  }
}

/* 深色模式下使用低亮度状态底色，避免浅色标签在暗背景中刺眼。 */
:global(:root.dark .tag-signed) {
  background: rgba(82, 196, 26, 0.16);
  border-color: rgba(82, 196, 26, 0.45);
  color: #95de64;
}

:global(:root.dark .tag-unsigned) {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  color: var(--ant-color-text-secondary);
}

:global(:root.dark .tag-failed) {
  background: rgba(255, 77, 79, 0.16);
  border-color: rgba(255, 77, 79, 0.48);
  color: #ff7875;
}

:global(:root.dark .tag-risk),
:global(:root.dark .tag-partial) {
  background: rgba(250, 173, 20, 0.16);
  border-color: rgba(250, 173, 20, 0.48);
  color: #ffc53d;
}
</style>
