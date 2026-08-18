<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import {
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
import type {
  CancelablePromise,
  GameSignAccountGroupConfig,
  OutBase,
  QrCheckOut,
  QrCreateOut,
  ToolsConfig_GameSign,
} from '@/api'
import { useGameSignAccountApi } from '@/composables/useGameSignAccountApi'
import { handleExternalLink } from '@/utils/openExternal'
import { useGameSignApi } from './useGameSignApi'

const {
  config,
  disabled = false,
  onFieldChange = undefined,
  onRefreshConfig = undefined,
} = defineProps<{
  config: ToolsConfig_GameSign
  disabled?: boolean
  /* eslint-disable no-unused-vars -- Callback parameter names document the prop contract. */
  onFieldChange?: (key: string, value: any) => void | Promise<void>
  /* eslint-enable no-unused-vars */
  onRefreshConfig?: () => Promise<void>
}>()

const logger = window.electronAPI.getLogger('游戏签到')
const signLoading = ref(false)
const notifySaving = ref(false)
const credentialToolDescription =
  '游戏签到社区工具用于管理各社区凭据，并按配置执行启动时、任务调度和手动签到。'
const credentialPrivacyNotice =
  '账密获取 Token 不保存任何账号密码；本次登录使用的账号密码仅存在于当前登录请求的内存中，登录完成或失败后立即清理，不写入配置、日志或通知。'

// ==================== 账号管理 ====================

interface AccountInstance {
  uid: string
  type: string
  Name: string
  Enabled: boolean
  MiyousheToken: string
  KuroToken: string
  SklandToken: string
  TaygedoToken: string
}

const { addAccount, updateAccount, loginTaygedo, loginSkland, deleteAccount } =
  useGameSignAccountApi()
const {
  listAccounts,
  reorderAccounts,
  manualSign,
  createMiyousheQr,
  checkMiyousheQr,
  saveMiyousheQr,
} = useGameSignApi()
const accounts = ref<AccountInstance[]>([])
const addLoading = ref(false)
const isDragging = ref(false)
const credentialAction = ref<'taygedo-login' | 'skland-login' | null>(null)

const loadAccounts = async () => {
  try {
    const response = await listAccounts()
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
        TaygedoToken: accountData.TaygedoToken || '',
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
  TaygedoToken: account.TaygedoToken,
})

const handleAddAccount = async () => {
  addLoading.value = true
  try {
    const result = await addAccount()
    if (result) {
      const defaultName = `用户 ${accounts.value.length + 1}`
      const data = result.data || {}
      const newAccount: AccountInstance = {
        uid: result.accountId,
        type: 'GameSignAccountGroup',
        Name: data.Name || defaultName,
        Enabled: data.Enabled ?? true,
        MiyousheToken: data.MiyousheToken || '',
        KuroToken: data.KuroToken || '',
        SklandToken: data.SklandToken || '',
        TaygedoToken: data.TaygedoToken || '',
      }
      accounts.value.push(newAccount)
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

const handleAccountEnabledChange = async (account: AccountInstance, enabled: boolean) => {
  const previousEnabled = account.Enabled
  account.Enabled = enabled
  try {
    await updateAccount(account.uid, { Enabled: enabled })
  } catch {
    account.Enabled = previousEnabled
    message.error('保存失败，请重试')
  }
}

// ==================== 拖拽排序 ====================

const onDragEnd = async (evt: any) => {
  if (evt.oldIndex === evt.newIndex) return
  isDragging.value = true
  try {
    const order = accounts.value.map(a => a.uid)
    const response = await reorderAccounts(order)
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
const taygedoLoginModalVisible = ref(false)
const taygedoLoginAccountId = ref('')
const taygedoLoginPhone = ref('')
const taygedoLoginPassword = ref('')
const sklandLoginModalVisible = ref(false)
const sklandLoginAccountId = ref('')
const sklandLoginPhone = ref('')
const sklandLoginPassword = ref('')

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

const openSklandLoginModal = () => {
  if (!editingAccount.value) return
  sklandLoginAccountId.value = editingAccount.value.uid
  sklandLoginPhone.value = ''
  sklandLoginPassword.value = ''
  sklandLoginModalVisible.value = true
}

const openEditModal = (account: AccountInstance) => {
  closeTaygedoLoginModal()
  closeSklandLoginModal()
  editingAccount.value = { ...account }
  editModalVisible.value = true
}

const handleEditModalCancel = () => {
  closeQrModal()
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
    message.success('Token 已保存')
    closeQrModal()
    editModalVisible.value = false
    editingAccount.value = null
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 Token 失败: ${errorMsg}`)
    message.error('保存失败，请重试')
  }
}

const handleTaygedoLogin = async () => {
  const accountId = taygedoLoginAccountId.value
  const phone = taygedoLoginPhone.value.trim()
  const password = taygedoLoginPassword.value
  if (!accountId) return
  if (!phone || !password) {
    message.warning('请填写塔吉多账号和密码')
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
    message.warning('请填写森空岛手机号和密码')
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

type QrApiResponse = QrCreateOut & QrCheckOut & OutBase

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

const abortableQrRequest = async <T,>(
  request: CancelablePromise<T>,
  signal?: AbortSignal
): Promise<T> => {
  let aborted = signal?.aborted ?? false
  const handleAbort = () => {
    aborted = true
    request.cancel()
  }
  signal?.addEventListener('abort', handleAbort, { once: true })
  if (aborted) request.cancel()

  try {
    return await request
  } catch (error) {
    if (aborted) {
      const abortError = new Error('Request aborted')
      abortError.name = 'AbortError'
      throw abortError
    }
    throw error
  } finally {
    signal?.removeEventListener('abort', handleAbort)
  }
}

const qrFetch = async (
  path: string,
  body?: Record<string, string>,
  signal?: AbortSignal
): Promise<QrApiResponse> => {
  let response: QrApiResponse
  if (path === '/create') {
    response = await abortableQrRequest(createMiyousheQr(), signal)
  } else if (path === '/check') {
    response = await abortableQrRequest(
      checkMiyousheQr(body?.ticket || '', body?.device || ''),
      signal
    )
  } else if (path === '/save') {
    response = await abortableQrRequest(
      saveMiyousheQr(body?.account_uid || '', body?.cookie || ''),
      signal
    )
  } else {
    throw new Error('未知二维码请求')
  }
  if (!response || typeof response !== 'object' || Array.isArray(response)) {
    throw new Error(QR_RESPONSE_INVALID_MESSAGE)
  }
  // 二维码 URL、ticket、设备标识和 Cookie 都是登录凭据，禁止写入前端日志。
  const logData = {
    ...response,
    ticket: undefined,
    qr_url: undefined,
    device: undefined,
    cookies_str: undefined,
  }
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
  account?: string
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
    const taygedoCredential = (() => {
      const raw = account.TaygedoToken?.trim()
      if (!raw) return { taygedo: false, cloud: false }
      try {
        const parsed = JSON.parse(raw) as Record<string, unknown>
        return {
          taygedo: Boolean(parsed.refreshToken || parsed.accessToken),
          cloud: Boolean(parsed.cloudToken && parsed.cloudUserId),
        }
      } catch {
        return { taygedo: true, cloud: false }
      }
    })()
    for (const platform of ['米游社', '森空岛', '库街区', '塔吉多', '云异环']) {
      const hasToken =
        (platform === '米游社' && !!account.MiyousheToken) ||
        (platform === '库街区' && !!account.KuroToken) ||
        (platform === '森空岛' && !!account.SklandToken) ||
        (platform === '塔吉多' && taygedoCredential.taygedo) ||
        (platform === '云异环' && taygedoCredential.cloud)
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

const getSignDetailAlias = (group: AccountGroup, game: GameItem): string => {
  const account = game.account?.trim() || ''
  const alias = account.split('/', 1)[0]?.trim()
  if (alias && alias !== '未知' && alias !== '未知用户') return alias
  return group.account_alias?.trim() || '未知用户'
}

const getSignStatusText = (status: string): string => {
  if (status === '成功' || status === '已签到') return '已签'
  if (status === '风控') return '风控'
  if (status === '失败') return '失败'
  return '未签'
}

const getSignDetailClass = (status: string): string => {
  if (status === '成功' || status === '已签到') return 'tt-signed'
  if (status === '风控') return 'tt-risk'
  if (status === '失败') return 'tt-failed'
  return 'tt-unsigned'
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
    const response = await manualSign()
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
        <h3>签到设置</h3>
        <div class="section-header-actions">
          <a
            href="https://doc.auto-mas.top/docs/advanced-features/game-sign.html"
            class="section-doc-link"
            title="查看森空岛签到配置文档"
            @click="handleExternalLink"
          >
            文档
          </a>
          <a-button
            type="primary"
            size="small"
            class="section-update-button primary-style"
            :loading="signLoading"
            :disabled="disabled || !config.Enabled"
            @click="handleManualSign"
          >
            <template #icon><SwapOutlined /></template>
            全部签到
          </a-button>
        </div>
      </div>
      <a-alert class="game-sign-notice" type="info" show-icon>
        <template #message>功能说明与隐私声明</template>
        <template #description>
          <div>{{ credentialToolDescription }}</div>
          <div>{{ credentialPrivacyNotice }}</div>
        </template>
      </a-alert>
      <div class="settings-list">
        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-title">启用签到工具</span>
            <span class="setting-desc"
              >启用后按 MAS 任务调度执行签到，手动签到不受每日自动签到限制</span
            >
          </div>
          <a-switch
            :checked="config.Enabled"
            :disabled="disabled"
            @change="handleChange('Enabled', $event)"
          />
        </div>
        <div class="setting-row">
          <div class="setting-info">
            <span class="setting-title">结果通知</span>
            <span class="setting-desc">签到完成后通过已配置的通知渠道推送结果</span>
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
            <span class="setting-title">启动时签到</span>
            <span class="setting-desc">应用启动后立即执行一次签到</span>
          </div>
          <a-switch
            :checked="config.RunOnStartup"
            :disabled="disabled"
            @change="handleChange('RunOnStartup', $event)"
          />
        </div>
        <div class="setting-row setting-row-static">
          <div class="setting-info">
            <span class="setting-title">上次签到</span>
            <span class="setting-desc">最近一次完成签到的日期</span>
          </div>
          <span class="setting-value">{{
            config.LastSignDate && config.LastSignDate !== '2000-01-01'
              ? config.LastSignDate
              : '从未签到'
          }}</span>
        </div>
      </div>
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
          <div class="header-cell status-cell">启用</div>
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
                        <div class="sign-tooltip-title">{{ tag.platform }} - 签到详情</div>
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
                              {{ getSignDetailAlias(group, game) }}
                            </div>
                            <div class="sign-tooltip-row">
                              <span>{{ game.game }}</span>
                              <span :class="getSignDetailClass(game.status)">
                                ● {{ getSignStatusText(game.status) }}
                              </span>
                              <span v-if="game.reward" class="tt-reward">{{ game.reward }}</span>
                            </div>
                          </template>
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
                  <a-button
                    size="middle"
                    class="action-btn delete-btn"
                    @click="handleDeleteAccount(account)"
                  >
                    <template #icon><DeleteOutlined /></template>
                    删除
                  </a-button>
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
      @cancel="handleEditModalCancel"
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
          <a-button
            size="small"
            class="credential-helper-btn"
            danger
            style="margin-top: 6px"
            :loading="qrLoading"
            @click="startQrLogin"
          >
            <template #icon><QrcodeOutlined /></template>
            扫码获取 Token
          </a-button>
        </div>
        <a-divider orientation="left" class="community-divider">库街区</a-divider>
        <div class="form-item-vertical">
          <a-input-password
            v-model:value="editingAccount.KuroToken"
            size="large"
            placeholder="粘贴已从库街区客户端获取的 Token"
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
          <a-button
            size="small"
            class="credential-helper-btn"
            danger
            style="margin-top: 6px"
            :loading="credentialAction === 'skland-login'"
            :disabled="credentialAction !== null"
            @click="openSklandLoginModal"
          >
            账密获取 Token
          </a-button>
        </div>
        <a-divider orientation="left" class="community-divider">塔吉多 / 云异环</a-divider>
        <div class="form-item-vertical">
          <a-input-password
            v-model:value="editingAccount.TaygedoToken"
            size="large"
            placeholder="refreshToken 或凭据 JSON（可含 cloudToken/cloudUserId/cloudDeviceId）"
            allow-clear
          />
          <a-button
            size="small"
            class="credential-helper-btn"
            danger
            style="margin-top: 6px"
            :loading="credentialAction === 'taygedo-login'"
            :disabled="credentialAction !== null"
            @click="openTaygedoLoginModal"
          >
            账密获取 Token
          </a-button>
        </div>
      </div>
    </a-modal>

    <!-- 塔吉多账号密码登录弹窗 -->
    <a-modal
      v-model:open="taygedoLoginModalVisible"
      title="塔吉多账密获取 Token"
      :footer="null"
      :width="420"
      @cancel="closeTaygedoLoginModal"
    >
      <div class="modal-form">
        <a-alert class="credential-disclaimer" type="warning" show-icon>
          <template #message>账密获取 Token 免责声明</template>
          <template #description>{{ credentialPrivacyNotice }}</template>
        </a-alert>
        <div class="form-item-vertical">
          <span class="form-label">当前账号</span>
          <a-input :value="editingAccount?.Name || ''" disabled />
        </div>
        <div class="form-item-vertical">
          <span class="form-label">账号或手机号</span>
          <a-input
            v-model:value="taygedoLoginPhone"
            autocomplete="off"
            placeholder="请输入塔吉多账号或手机号"
            allow-clear
          />
        </div>
        <div class="form-item-vertical">
          <span class="form-label">密码</span>
          <a-input-password
            v-model:value="taygedoLoginPassword"
            autocomplete="new-password"
            placeholder="请输入塔吉多账号密码"
            allow-clear
          />
        </div>
        <a-space style="width: 100%; justify-content: flex-end">
          <a-button @click="closeTaygedoLoginModal">取消</a-button>
          <a-button
            type="primary"
            class="credential-helper-btn"
            danger
            :loading="credentialAction === 'taygedo-login'"
            :disabled="credentialAction !== null"
            @click="handleTaygedoLogin"
          >
            获取并保存 Token
          </a-button>
        </a-space>
      </div>
    </a-modal>

    <!-- 森空岛账密获取 Token 弹窗 -->
    <a-modal
      v-model:open="sklandLoginModalVisible"
      title="森空岛账密获取 Token"
      :footer="null"
      :width="420"
      @cancel="closeSklandLoginModal"
    >
      <div class="modal-form">
        <a-alert class="credential-disclaimer" type="warning" show-icon>
          <template #message>账密获取 Token 免责声明</template>
          <template #description>{{ credentialPrivacyNotice }}</template>
        </a-alert>
        <div class="form-item-vertical">
          <span class="form-label">当前账号</span>
          <a-input :value="editingAccount?.Name || ''" disabled />
        </div>
        <div class="form-item-vertical">
          <span class="form-label">手机号</span>
          <a-input
            v-model:value="sklandLoginPhone"
            autocomplete="off"
            placeholder="请输入鹰角网络通行证手机号"
            allow-clear
          />
        </div>
        <div class="form-item-vertical">
          <span class="form-label">密码</span>
          <a-input-password
            v-model:value="sklandLoginPassword"
            autocomplete="new-password"
            placeholder="请输入鹰角网络通行证密码"
            allow-clear
          />
        </div>
        <a-space style="width: 100%; justify-content: flex-end">
          <a-button @click="closeSklandLoginModal">取消</a-button>
          <a-button
            type="primary"
            class="credential-helper-btn"
            danger
            :loading="credentialAction === 'skland-login'"
            :disabled="credentialAction !== null"
            @click="handleSklandLogin"
          >
            获取并保存 Token
          </a-button>
        </a-space>
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
  background: linear-gradient(
    135deg,
    var(--ant-color-primary),
    var(--ant-color-primary-hover)
  ) !important;
  border: 1px solid var(--ant-color-primary) !important;
  color: #fff !important;
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
