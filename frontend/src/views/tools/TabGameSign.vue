<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  QuestionCircleOutlined,
  EditOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SwapOutlined,
  QrcodeOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import QRCode from 'qrcode'
import draggable from 'vuedraggable'
import type { ToolsConfig_GameSign, GameSignAccountGroupConfig } from '@/api'
import { Service } from '@/api'
import { OpenAPI } from '@/api/core/OpenAPI'
import { useGameSignAccountApi } from '@/composables/useGameSignAccountApi'
import { handleExternalLink } from '@/utils/openExternal'

const {
  config,
  disabled = false,
  onFieldChange = undefined,
  onSelectVisibleChange = undefined,
  onRefreshConfig = undefined,
} = defineProps<{
  config: ToolsConfig_GameSign
  disabled?: boolean
  /* eslint-disable no-unused-vars -- Callback parameter names document the prop contract. */
  onFieldChange?: (key: string, value: any) => void | Promise<void>
  onSelectVisibleChange?: (visible: boolean) => void
  /* eslint-enable no-unused-vars */
  onRefreshConfig?: () => Promise<void>
}>()

const logger = window.electronAPI.getLogger('游戏签到')
const signLoading = ref(false)
const notifySaving = ref(false)

// ==================== 账号管理 ====================

interface AccountInstance {
  uid: string
  type: string
  Name: string
  Enabled: boolean
  MiyousheToken: string
  KuroToken: string
  SklandToken: string
}

const { addAccount, updateAccount, deleteAccount } = useGameSignAccountApi()
const accounts = ref<AccountInstance[]>([])
const addLoading = ref(false)
const isDragging = ref(false)

const loadAccounts = async () => {
  try {
    const response = await Service.listGameSignAccountsApiToolsSignAccountListPost()
    if (response.code !== 200) return
    const data = response.data as any
    const instances: AccountInstance[] = []
    const instanceList = data?.instances || []
    for (const inst of instanceList) {
      const uid = inst.uid as string
      const accountData = data?.[uid]?.GameSignAccount || {}
      instances.push({
        uid,
        type: inst.type || 'GameSignAccountGroup',
        Name: accountData.Name || '用户',
        Enabled: accountData.Enabled ?? true,
        MiyousheToken: accountData.MiyousheToken || '',
        KuroToken: accountData.KuroToken || '',
        SklandToken: accountData.SklandToken || '',
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
  KuroToken: account.KuroToken,
  SklandToken: account.SklandToken,
})

const handleAddAccount = async () => {
  addLoading.value = true
  try {
    const result = await addAccount()
    if (result) {
      const defaultName = `用户 ${accounts.value.length + 1}`
      const newAccount: AccountInstance = {
        uid: result.accountId,
        type: 'GameSignAccountGroup',
        Name: defaultName,
        Enabled: true,
        MiyousheToken: '',
        KuroToken: '',
        SklandToken: '',
      }
      accounts.value.push(newAccount)
      await updateAccount(result.accountId, getAccountAllData(newAccount))
      message.success('用户已添加')
      openEditModal(newAccount)
    }
  } finally {
    addLoading.value = false
  }
}

const handleDeleteAccount = (account: AccountInstance) => {
  Modal.confirm({
    title: '删除用户',
    content: `确定要删除「${account.Name}」吗？该操作不可撤销。`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      await deleteAccount(account.uid)
      accounts.value = accounts.value.filter(a => a.uid !== account.uid)
    },
  })
}

const handleAccountFieldSave = async (account: AccountInstance) => {
  try {
    await updateAccount(account.uid, getAccountAllData(account))
  } catch {
    message.error('保存失败，请重试')
  }
}

// ==================== 拖拽排序 ====================

const onDragEnd = async (evt: any) => {
  if (evt.oldIndex === evt.newIndex) return
  isDragging.value = true
  try {
    const order = accounts.value.map(a => a.uid)
    const response = await Service.reorderGameSignAccountsApiToolsSignAccountReorderPost({ order })
    if (response.code !== 200) {
      throw new Error(response.message || '排序保存失败')
    }
    logger.info('用户排序已保存')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`排序保存失败: ${errorMsg}`)
    message.error(`排序保存失败：${errorMsg}`)
    await loadAccounts()
  } finally {
    isDragging.value = false
  }
}

// ==================== 编辑 Token 模态框 ====================

const editModalVisible = ref(false)
const editingAccount = ref<AccountInstance | null>(null)

const openEditModal = (account: AccountInstance) => {
  editingAccount.value = { ...account }
  editModalVisible.value = true
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
    message.success('Token 已保存')
    editModalVisible.value = false
    editingAccount.value = null
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 Token 失败: ${errorMsg}`)
    message.error('保存失败，请重试')
  }
}

// ==================== 米游社扫码登录 ====================

const qrModalVisible = ref(false)
const qrLoading = ref(false)
const qrStatus = ref<
  'idle' | 'loading' | 'waiting' | 'scanned' | 'exchanging' | 'done' | 'expired' | 'error'
>('idle')
const qrCodeDataUrl = ref('')
const qrStatusText = ref('')
const qrTicket = ref('')
const qrDevice = ref('')
const qrPollTimer = ref<ReturnType<typeof setInterval> | null>(null)
const qrPollInFlight = ref(false)
let qrSessionId = 0
let qrAbortController: AbortController | null = null
let qrCloseTimer: ReturnType<typeof setTimeout> | null = null

interface QrApiResponse {
  code?: number
  status?: string
  message?: string
  ticket?: string
  qr_url?: string
  device?: string
  cookies_str?: string
}

const QR_RESPONSE_INVALID_MESSAGE = '二维码状态响应无效，请刷新后重试'
const isQrExpiredMessage = (messageText: string) =>
  /二维码|qr|expired|invalid|nonetype.*get|object has no attribute.*get/i.test(messageText)

const stopQrPoll = () => {
  if (qrPollTimer.value) {
    clearInterval(qrPollTimer.value)
    qrPollTimer.value = null
  }
}

const clearQrCloseTimer = () => {
  if (qrCloseTimer) {
    clearTimeout(qrCloseTimer)
    qrCloseTimer = null
  }
}

const isCurrentQrSession = (sessionId: number) => sessionId === qrSessionId && qrModalVisible.value

const invalidateQrSession = () => {
  qrSessionId += 1
  stopQrPoll()
  clearQrCloseTimer()
  qrAbortController?.abort()
  qrAbortController = null
  qrPollInFlight.value = false
  return qrSessionId
}

const isQrAbortError = (error: unknown) => error instanceof Error && error.name === 'AbortError'

const qrFetch = async (
  path: string,
  body?: Record<string, string>,
  signal?: AbortSignal
): Promise<QrApiResponse> => {
  const resp = await fetch(`${OpenAPI.BASE}/api/tools/sign/miyoushe/qr${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
    signal,
  })
  const text = await resp.text()
  if (!text) throw new Error('服务器无响应')
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    throw new Error(QR_RESPONSE_INVALID_MESSAGE)
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error(QR_RESPONSE_INVALID_MESSAGE)
  }
  const response = data as QrApiResponse
  // Cookie 是登录凭据，禁止写入前端日志；其余字段仍保留便于排查状态流转。
  const logData = { ...response, cookies_str: undefined }
  logger.debug(`[QR ${path}] ${JSON.stringify(logData)}`)
  // 不在此处抛出 API 错误，由调用方根据 data.status / data.code 处理
  return response
}

const markQrExpired = (messageText = '二维码已过期，请刷新后重新扫码') => {
  stopQrPoll()
  qrStatus.value = 'expired'
  qrStatusText.value = messageText
  qrCodeDataUrl.value = ''
}

const startQrLogin = async () => {
  const sessionId = invalidateQrSession()
  qrAbortController = new AbortController()
  const { signal } = qrAbortController
  qrLoading.value = true
  qrStatus.value = 'loading'
  qrStatusText.value = '正在生成二维码...'
  qrCodeDataUrl.value = ''
  qrTicket.value = ''
  qrDevice.value = ''
  qrModalVisible.value = true

  try {
    const data = await qrFetch('/create', undefined, signal)
    if (!isCurrentQrSession(sessionId)) return
    if (data.code === 500 || data.status === 'error') {
      qrStatus.value = 'error'
      qrStatusText.value = data.message || '创建二维码失败'
      return
    }
    if (!data.qr_url || !data.ticket || !data.device) {
      throw new Error('创建二维码失败：服务端响应缺少登录信息')
    }
    qrCodeDataUrl.value = await QRCode.toDataURL(data.qr_url, {
      width: 240,
      margin: 2,
      errorCorrectionLevel: 'M',
    })
    if (!isCurrentQrSession(sessionId)) return
    qrTicket.value = data.ticket
    qrDevice.value = data.device
    qrStatus.value = 'waiting'
    qrStatusText.value = '请使用米游社 APP 扫描二维码'
    qrPollTimer.value = setInterval(() => {
      void pollQrStatus(sessionId)
    }, 2000)
  } catch (e) {
    if (!isCurrentQrSession(sessionId) || isQrAbortError(e)) return
    qrStatus.value = 'error'
    qrStatusText.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (isCurrentQrSession(sessionId)) {
      qrLoading.value = false
    }
  }
}

const pollQrStatus = async (sessionId: number) => {
  if (
    !isCurrentQrSession(sessionId) ||
    qrPollInFlight.value ||
    !qrTicket.value ||
    !qrDevice.value
  ) {
    return
  }
  const ticket = qrTicket.value
  const device = qrDevice.value
  const signal = qrAbortController?.signal
  if (!signal) return
  qrPollInFlight.value = true
  try {
    const data = await qrFetch('/check', { ticket, device }, signal)
    if (!isCurrentQrSession(sessionId)) return

    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      markQrExpired('二维码已失效或服务端返回空响应，请刷新后重试')
      return
    }

    const responseMessage = typeof data.message === 'string' ? data.message : ''

    // 后端错误响应（code=500 或 status=error）
    if (data.code === 500 || data.status === 'error') {
      if (isQrExpiredMessage(responseMessage)) {
        markQrExpired(responseMessage)
      } else {
        stopQrPoll()
        qrStatus.value = 'error'
        qrStatusText.value = responseMessage || '查询状态失败'
      }
      return
    }

    if (data.status === 'Scanned') {
      qrStatus.value = 'scanned'
      qrStatusText.value = '已扫码，等待确认...'
    } else if (data.status === 'Confirmed') {
      stopQrPoll()
      await handleQrConfirmed(data.cookies_str || '', sessionId, signal)
    } else if (data.status === 'Canceled') {
      stopQrPoll()
      qrStatus.value = 'error'
      qrStatusText.value = responseMessage || '登录已取消'
    } else if (data.status === 'Expired') {
      markQrExpired(responseMessage || '二维码已过期，请刷新后重新扫码')
    } else if (data.status === 'Error') {
      if (isQrExpiredMessage(responseMessage)) {
        markQrExpired(responseMessage)
      } else {
        stopQrPoll()
        qrStatus.value = 'error'
        qrStatusText.value = responseMessage || '查询状态失败'
      }
    }
    // status === 'Init' 时不更新 UI，继续轮询
  } catch (e) {
    if (!isCurrentQrSession(sessionId) || isQrAbortError(e)) return
    const errorMessage = e instanceof Error ? e.message : String(e)
    if (isQrExpiredMessage(errorMessage) || errorMessage === QR_RESPONSE_INVALID_MESSAGE) {
      markQrExpired('二维码已失效或服务端返回无效状态，请刷新后重试')
    } else {
      // 短暂网络错误不停止轮询，但记录日志便于调试。
      logger.warn(`[QR poll] 轮询异常: ${errorMessage}`)
    }
  } finally {
    if (isCurrentQrSession(sessionId)) {
      qrPollInFlight.value = false
    }
  }
}

const handleQrConfirmed = async (cookiesStr: string, sessionId: number, signal: AbortSignal) => {
  if (!isCurrentQrSession(sessionId)) return
  if (!cookiesStr) {
    qrStatus.value = 'error'
    qrStatusText.value = '扫码确认成功但未获取到有效认证 Cookie，请重新生成二维码'
    return
  }

  // Passport 模式：cookies 直接从响应头获取，无需 exchange
  const accountId = editingAccount.value?.uid
  if (accountId) {
    qrStatus.value = 'exchanging'
    qrStatusText.value = '正在保存登录凭据...'
    try {
      const saveResponse = await qrFetch(
        '/save',
        {
          account_uid: accountId,
          cookie: cookiesStr,
        },
        signal
      )
      if (!isCurrentQrSession(sessionId)) return
      if (saveResponse.code !== 200 || saveResponse.status === 'error') {
        throw new Error(saveResponse.message || '保存 Token 失败')
      }
      if (editingAccount.value?.uid === accountId) {
        editingAccount.value.MiyousheToken = cookiesStr
      }
      await loadAccounts()
      if (!isCurrentQrSession(sessionId)) return
      if (onRefreshConfig) {
        await onRefreshConfig()
      }
      if (!isCurrentQrSession(sessionId)) return
    } catch (error) {
      if (!isCurrentQrSession(sessionId) || isQrAbortError(error)) return
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`扫码保存 Token 失败: ${errorMsg}`)
      message.error('扫码成功，但保存 Token 失败')
      qrStatus.value = 'error'
      qrStatusText.value = '扫码成功，但保存 Token 失败'
      return
    }
  }
  qrStatus.value = 'done'
  qrStatusText.value = '登录成功！Token 已自动填入'
  message.success('米游社扫码登录成功')
  // 延迟关闭弹窗，让用户看到成功提示
  clearQrCloseTimer()
  qrCloseTimer = setTimeout(() => {
    qrCloseTimer = null
    if (isCurrentQrSession(sessionId)) closeQrModal()
  }, 1200)
}

const closeQrModal = () => {
  invalidateQrSession()
  qrModalVisible.value = false
  qrLoading.value = false
  qrStatus.value = 'idle'
  qrCodeDataUrl.value = ''
  qrStatusText.value = ''
  qrTicket.value = ''
  qrDevice.value = ''
}

onBeforeUnmount(() => {
  invalidateQrSession()
})

// ==================== 签到结果解析（按用户绑定） ====================

interface GameItem {
  game: string
  status: string
  reward: string
  reason: string
}

interface AccountGroup {
  account_alias: string
  account_uid: string
  games: GameItem[]
}

interface PlatformResult {
  [platform: string]: AccountGroup[]
}

const signResult = computed<PlatformResult>(() => {
  try {
    const resultStr = config.Result
    if (!resultStr || resultStr === '{}' || resultStr === '-') return {}
    return JSON.parse(resultStr)
  } catch {
    return {}
  }
})

// 标签云状态类型
type TagStatus = 'signed' | 'partial' | 'unsigned' | 'failed' | 'risk' | 'unconfigured'

// 平台标签数据结构
interface PlatformTag {
  platform: string
  status: TagStatus
  games: GameItem[]
  groups: AccountGroup[]
  signedCount: number
  totalCount: number
  failedCount: number
  riskCount: number
}

// 将每个用户的社区标签预计算为响应式 Map
// 使用 computed 确保当 signResult 或 accounts 变化时自动重新计算
const userTagsMap = computed<Map<string, PlatformTag[]>>(() => {
  const result = signResult.value
  const map = new Map<string, PlatformTag[]>()

  for (const account of accounts.value) {
    const tags: PlatformTag[] = []
    for (const platform of ['米游社', '森空岛', '库街区']) {
      const hasToken =
        (platform === '米游社' && !!account.MiyousheToken) ||
        (platform === '库街区' && !!account.KuroToken) ||
        (platform === '森空岛' && !!account.SklandToken)
      if (!hasToken) continue

      const platformData = result[platform]
      const games: GameItem[] = []
      const groups: AccountGroup[] = []
      if (platformData) {
        for (const group of platformData) {
          if (group.account_uid === account.uid) {
            games.push(...group.games)
            groups.push(group)
          }
        }
      }

      const totalCount = games.length
      const signedCount = games.filter(g => g.status === '成功' || g.status === '已签到').length
      const failedCount = games.filter(g => g.status === '失败').length
      const riskCount = games.filter(g => g.status === '风控').length

      let status: TagStatus
      if (totalCount === 0) {
        status = 'unsigned'
      } else if (riskCount > 0) {
        status = 'risk'
      } else if (failedCount > 0) {
        status = 'failed'
      } else if (signedCount === totalCount) {
        status = 'signed'
      } else if (signedCount > 0) {
        status = 'partial'
      } else {
        status = 'unsigned'
      }

      tags.push({
        platform,
        status,
        games,
        groups,
        signedCount,
        totalCount,
        failedCount,
        riskCount,
      })
    }
    map.set(account.uid, tags)
  }
  return map
})

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

// 标签文字 — 尚无结果时只显示社区名，执行后显示成功数/总数
const getTagText = (tag: PlatformTag) => {
  return tag.totalCount > 0 ? `${tag.platform}${tag.signedCount}/${tag.totalCount}` : tag.platform
}

// 标签 CSS 类
const getTagClass = (status: TagStatus) => `tag-${status}`

// ==================== 通用变更处理 ====================

const handleChange = async (key: string, value: any) => {
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
    const response = await Service.manualGameSignApiToolsSignPost()
    if (response.code === 409) {
      const warning = response.message || '自动签到正在执行，请稍后再试'
      logger.warn(`手动签到被拒绝: ${warning}`)
      message.warning(warning)
      return
    }
    if (response.code !== 200 && response.code !== 0) {
      throw new Error(response.message || '签到失败')
    }
    logger.info('游戏签到完成')
    if (response.status === 'warning') {
      message.warning(response.message || '签到完成，但部分通知发送失败')
    } else {
      message.success(response.message || '签到完成')
    }
    // 立即刷新签到结果（不等父组件轮询）
    if (onRefreshConfig) await onRefreshConfig()
    await loadAccounts()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`签到失败: ${errorMsg}`)
    message.error(`签到失败: ${errorMsg}`)
  } finally {
    signLoading.value = false
  }
}

// ==================== 生命周期 ====================

onMounted(() => {
  loadAccounts()
})
</script>

<template>
  <div class="tab-content">
    <!-- 全局设置区 -->
    <div class="form-section">
      <div class="section-header">
        <h3>游戏社区签到</h3>
        <div class="section-header-actions">
          <a
            href="https://doc.auto-mas.top/docs/script-guide/maa.html#%E6%A3%AE%E7%A9%BA%E5%B2%9B%E8%87%AA%E5%8A%A8%E7%AD%BE%E5%88%B0"
            class="section-doc-link"
            title="查看森空岛签到配置文档"
            @click="handleExternalLink"
          >
            文档
          </a>
          <a-button
            type="primary"
            :loading="signLoading"
            :disabled="disabled || !config.Enabled"
            @click="handleManualSign"
          >
            <template #icon><SwapOutlined /></template>
            全部签到
          </a-button>
        </div>
      </div>
      <a-row :gutter="24">
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用签到</span>
              <a-tooltip title="是否启用每日自动游戏社区签到">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="config.Enabled"
              size="large"
              style="width: 100%"
              :disabled="disabled"
              @change="handleChange('Enabled', $event)"
              @dropdown-visible-change="onSelectVisibleChange"
            >
              <a-select-option :value="true">启用</a-select-option>
              <a-select-option :value="false">禁用</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">签到后通知</span>
              <a-tooltip title="签到完成后通过已配置的通知渠道推送结果">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="config.NotifyEnabled"
              size="large"
              style="width: 100%"
              :disabled="disabled || notifySaving"
              :loading="notifySaving"
              @change="handleNotifyEnabledChange"
              @dropdown-visible-change="onSelectVisibleChange"
            >
              <a-select-option :value="true">启用</a-select-option>
              <a-select-option :value="false">禁用</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启动时签到</span>
              <a-tooltip title="应用启动后立即执行一次签到">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="config.RunOnStartup"
              size="large"
              style="width: 100%"
              :disabled="disabled"
              @change="handleChange('RunOnStartup', $event)"
              @dropdown-visible-change="onSelectVisibleChange"
            >
              <a-select-option :value="true">启用</a-select-option>
              <a-select-option :value="false">禁用</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">自动签到</span>
              <a-tooltip title="运行 MAS 定时、手动或启动时代理任务时执行每日自动签到">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-switch
              :checked="config.ScheduledRun"
              :disabled="disabled"
              checked-children="开"
              un-checked-children="关"
              @change="handleChange('ScheduledRun', $event)"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <!-- 用户列表 -->
    <div class="form-section">
      <div class="section-header">
        <h3>用户列表</h3>
        <a-button
          type="primary"
          ghost
          size="middle"
          :loading="addLoading"
          :disabled="disabled"
          @click="handleAddAccount"
        >
          <template #icon><PlusOutlined /></template>
          添加用户
        </a-button>
      </div>

      <div class="user-table-container">
        <!-- 表头 -->
        <div class="user-table-header">
          <div class="header-cell drag-cell"></div>
          <div class="header-cell name-cell">用户名</div>
          <div class="header-cell status-cell">状态</div>
          <div class="header-cell tags-cell">各社区签到情况</div>
          <div class="header-cell actions-cell">操作</div>
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
                <span class="drag-handle" title="拖拽排序">
                  <span class="drag-dots"></span>
                </span>
              </div>
              <!-- 用户名 -->
              <div class="row-cell name-cell">
                <span class="user-name-text">{{ account.Name }}</span>
              </div>
              <!-- 状态 -->
              <div class="row-cell status-cell">
                <a-select
                  v-model:value="account.Enabled"
                  size="middle"
                  style="width: 100px"
                  :disabled="disabled"
                  @change="handleAccountFieldSave(account)"
                  @dropdown-visible-change="onSelectVisibleChange"
                >
                  <a-select-option :value="true">启用</a-select-option>
                  <a-select-option :value="false">禁用</a-select-option>
                </a-select>
              </div>
              <!-- 社区签到情况（标签云） -->
              <div class="row-cell tags-cell">
                <a-space :size="6" wrap>
                  <a-tooltip
                    v-for="tag in getUserPlatformTagsReactive(account)"
                    :key="tag.platform"
                  >
                    <template #title>
                      <div class="sign-tooltip">
                        <div class="sign-tooltip-title">{{ tag.platform }} - 签到详情</div>
                        <template
                          v-for="(group, gIdx) in getAccountGroupsForPlatformReactive(
                            account,
                            tag.platform
                          )"
                          :key="gIdx"
                        >
                          <div class="sign-tooltip-alias">{{ group.account_alias }}</div>
                          <div
                            v-for="game in group.games"
                            :key="game.game"
                            class="sign-tooltip-row"
                          >
                            <span>{{ game.game }}</span>
                            <span
                              :class="
                                game.status === '成功' || game.status === '已签到'
                                  ? 'tt-signed'
                                  : game.status === '风控'
                                    ? 'tt-risk'
                                    : game.status === '失败'
                                      ? 'tt-failed'
                                      : 'tt-unsigned'
                              "
                            >
                              ●
                              {{
                                game.status === '成功' || game.status === '已签到'
                                  ? '已签'
                                  : game.status === '风控'
                                    ? '风控'
                                    : game.status === '失败'
                                      ? '失败'
                                      : '未签'
                              }}
                            </span>
                            <span v-if="game.reward" class="tt-reward">{{ game.reward }}</span>
                          </div>
                        </template>
                        <div v-if="tag.games.length === 0" class="sign-tooltip-empty">
                          暂无签到数据
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
                    编辑
                  </a-button>
                  <a-popconfirm
                    title="确定要删除此用户吗？"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="handleDeleteAccount(account)"
                  >
                    <a-button size="middle" class="action-btn delete-btn">
                      <template #icon><DeleteOutlined /></template>
                      删除
                    </a-button>
                  </a-popconfirm>
                </a-space>
              </div>
            </div>
          </template>
        </draggable>

        <!-- 空状态 -->
        <div v-if="accounts.length === 0" class="empty-state">
          <div class="empty-hint">暂无用户</div>
          <div class="empty-guide">点击右上角「添加用户」创建</div>
        </div>
      </div>
    </div>

    <!-- 编辑 Token 模态框 -->
    <a-modal
      v-model:open="editModalVisible"
      :title="`编辑 — ${editingAccount?.Name || ''}`"
      ok-text="保存"
      cancel-text="取消"
      :width="560"
      @ok="handleEditModalOk"
    >
      <div v-if="editingAccount" class="modal-form">
        <div class="form-item-vertical">
          <span class="form-label">用户名称</span>
          <a-input v-model:value="editingAccount.Name" size="large" />
        </div>
        <a-divider orientation="left" class="community-divider">米游社</a-divider>
        <div class="form-item-vertical">
          <a-input-password
            v-model:value="editingAccount.MiyousheToken"
            size="large"
            placeholder="浏览器 F12 → document.cookie 获取"
            allow-clear
          />
          <a-button size="small" style="margin-top: 6px" :loading="qrLoading" @click="startQrLogin">
            <template #icon><QrcodeOutlined /></template>
            扫码登录获取 Token
          </a-button>
        </div>
        <a-divider orientation="left" class="community-divider">库街区</a-divider>
        <div class="form-item-vertical">
          <a-input-password
            v-model:value="editingAccount.KuroToken"
            size="large"
            placeholder="抓包或短信验证码获取 Token"
            allow-clear
          />
        </div>
        <a-divider orientation="left" class="community-divider">森空岛</a-divider>
        <div class="form-item-vertical">
          <a-input-password
            v-model:value="editingAccount.SklandToken"
            size="large"
            placeholder="鹰角网络通行证登录凭证"
            allow-clear
          />
        </div>
      </div>
    </a-modal>

    <!-- 扫码登录弹窗 -->
    <a-modal
      v-model:open="qrModalVisible"
      title="米游社扫码登录"
      :footer="null"
      :width="360"
      @cancel="closeQrModal"
    >
      <div class="qr-login-container">
        <!-- 二维码 -->
        <div
          v-if="qrCodeDataUrl && qrStatus !== 'error' && qrStatus !== 'expired'"
          class="qr-code-wrapper"
        >
          <img :src="qrCodeDataUrl" alt="扫码登录" class="qr-code-img" />
        </div>

        <!-- 加载中 -->
        <div v-if="qrStatus === 'loading'" class="qr-status">
          <a-spin />
          <span style="margin-left: 8px">{{ qrStatusText }}</span>
        </div>

        <!-- 状态提示 -->
        <div v-if="qrStatus !== 'loading'" class="qr-status">
          <span v-if="qrStatus === 'waiting'" class="qr-status-primary">
            ⏳ {{ qrStatusText }}
          </span>
          <span v-else-if="qrStatus === 'scanned'" class="qr-status-warning">
            📱 {{ qrStatusText }}
          </span>
          <span v-else-if="qrStatus === 'exchanging'" class="qr-status-primary">
            ⚙️ {{ qrStatusText }}
          </span>
          <span v-else-if="qrStatus === 'done'" class="qr-status-success">
            ✅ {{ qrStatusText }}
          </span>
          <span v-else-if="qrStatus === 'expired'" class="qr-status-error">
            ⚠️ {{ qrStatusText }}
          </span>
          <span v-else-if="qrStatus === 'error'" class="qr-status-error">
            ❌ {{ qrStatusText }}
          </span>
        </div>

        <div v-if="qrStatus === 'waiting' || qrStatus === 'scanned'" class="qr-hint">
          打开米游社 APP → 左上角扫码 → 扫描上方二维码
        </div>

        <div v-if="qrStatus === 'expired' || qrStatus === 'error'" class="qr-actions">
          <a-button type="primary" size="small" :loading="qrLoading" @click="startQrLogin">
            <template #icon><ReloadOutlined /></template>
            重新生成二维码
          </a-button>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
/* 用户启用状态通过选项文字表达，保留 Ant Design 默认边框。 */

.section-header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.section-doc-link {
  color: var(--ant-color-primary) !important;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--ant-color-primary);
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 4px;
}

.section-doc-link:hover {
  color: var(--ant-color-primary-hover) !important;
  background-color: var(--ant-color-primary-bg);
  border-color: var(--ant-color-primary-hover);
  text-decoration: none;
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
  width: 120px;
  min-width: 120px;
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

/* ==================== 状态下拉框 - 对齐 TimeSetManager ==================== */
.status-select :deep(.ant-select-selector) {
  background: transparent !important;
  border: none !important;
  padding: 0 6px !important;
  min-height: 28px !important;
  line-height: 26px !important;
  box-shadow: none !important;
  text-align: center;
}

.status-select :deep(.ant-select-selection-item) {
  line-height: 26px !important;
  color: var(--ant-color-text) !important;
  font-weight: 500;
  padding: 0;
  margin: 0;
}

.status-select :deep(.ant-select-selection-placeholder) {
  line-height: 26px !important;
  color: var(--ant-color-text-placeholder) !important;
  padding: 0;
  margin: 0;
}

.status-select :deep(.ant-select-clear) {
  display: none !important;
}

.status-select :deep(.ant-select-selection-search) {
  margin: 0 !important;
  padding: 0;
}

.status-select :deep(.ant-select-selection-search-input) {
  padding: 0 !important;
  margin: 0 !important;
  height: 26px !important;
}

.status-select:hover :deep(.ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

.status-select:focus-within :deep(.ant-select-selector),
.status-select.ant-select-focused :deep(.ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  outline: none !important;
}

.status-select :deep(.ant-select-arrow) {
  right: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 10px;
}

.status-select :deep(.ant-select-arrow:hover) {
  color: var(--ant-color-primary);
}

/* ==================== 社区标签云（小标签 + 红绿黄） ==================== */
.platform-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  line-height: 1.5;
  border: 1px solid transparent;
  cursor: default;
  white-space: nowrap;
}

/* 绿色：签到成功 */
.tag-signed {
  background: #f6ffed;
  border-color: #b7eb8f;
  color: #52c41a;
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
.sign-tooltip {
  min-width: 220px;
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
}
.sign-tooltip-alias:first-of-type {
  margin-top: 0;
}
.sign-tooltip-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 0;
  font-size: 13px;
  gap: 12px;
}
.tt-signed {
  color: #52c41a;
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

.community-divider {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

/* ==================== 扫码登录弹窗 ==================== */
.qr-login-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0;
}
.qr-code-wrapper {
  margin-bottom: 16px;
}
.qr-code-img {
  width: 240px;
  height: 240px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}
.qr-status {
  text-align: center;
  font-size: 14px;
  margin-bottom: 12px;
  min-height: 24px;
}
.qr-status-primary {
  color: var(--ant-color-primary);
}
.qr-status-warning {
  color: var(--ant-color-warning);
}
.qr-status-success {
  color: var(--ant-color-success);
}
.qr-status-error {
  color: var(--ant-color-error);
}
.qr-hint {
  text-align: center;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
.qr-actions {
  margin-top: 4px;
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
