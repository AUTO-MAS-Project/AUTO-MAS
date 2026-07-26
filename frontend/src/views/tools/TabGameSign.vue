<script setup lang="ts">
/**
 * Lane 8：游戏签到 Tab。
 *
 * 拆分后职责：
 * - 全局签到设置（启用/通知/时间窗口）
 * - 异步签到任务管理（useToolsAsyncTask）
 * - 账号 CRUD 与拖拽排序
 * - 协调子组件：GameSignUserTable / GameSignEditModal / MiyousheQrModal
 *
 * 拆出的模块：
 * - composables/useMiyousheQrLogin.ts：扫码登录状态与轮询
 * - composables/useSignResultTags.ts：签到结果标签云计算
 * - components/GameSignUserTable.vue：用户列表表格（含拖拽 + 标签云）
 * - components/GameSignEditModal.vue：编辑 Token 模态框
 * - components/MiyousheQrModal.vue：扫码登录弹窗
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { QuestionCircleOutlined, SwapOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import dayjs from 'dayjs'
import type { ToolsConfig_GameSign, GameSignAccountGroupConfig } from '@/api'
import { Service } from '@/api'
import { useGameSignAccountApi } from '@/composables/useGameSignAccountApi'
import { useToolsAsyncTask } from '@/composables/useToolsAsyncTask'
import ToolsTaskPanel from './components/ToolsTaskPanel.vue'
import GameSignUserTable from './components/GameSignUserTable.vue'
import GameSignEditModal from './components/GameSignEditModal.vue'
import MiyousheQrModal from './components/MiyousheQrModal.vue'
import { useMiyousheQrLogin } from './composables/useMiyousheQrLogin'
import { useSignResultTags, type AccountLike } from './composables/useSignResultTags'
import type { AccountInstance } from './components/GameSignUserTable.vue'

const {
  config,
  disabled = false,
  onFieldChange = undefined,
  onSelectVisibleChange = undefined,
  onRefreshConfig = undefined,
} = defineProps<{
  config: ToolsConfig_GameSign
  disabled?: boolean
  onFieldChange?: (key: string, value: any) => void
  onSelectVisibleChange?: (visible: boolean) => void
  onRefreshConfig?: () => Promise<void>
}>()

const logger = window.electronAPI.getLogger('游戏签到')

// ==================== 异步签到任务 ====================

const signTask = useToolsAsyncTask({ taskName: '游戏签到' })

const performSign = async (signal: AbortSignal) => {
  const response = await Service.manualGameSignApiToolsSignPost()
  // 取消信号到达时直接返回，不再触发后续刷新，避免旧请求迟到覆盖新状态。
  if (signal.aborted) return
  if (response.code !== 200 && response.code !== 0) {
    throw new Error(response.message || '签到失败')
  }
  logger.info('游戏签到完成')
  if (onRefreshConfig) await onRefreshConfig()
  // 再次检查取消信号，避免刷新过程中用户点了取消却仍执行 loadAccounts。
  if (signal.aborted) return
  await loadAccounts()
}

const handleManualSign = async () => {
  // Lane 8：禁止重复执行。运行中再次点击直接忽略。
  if (signTask.isRunning.value) return
  await signTask.run(performSign)
  if (signTask.status.value === 'success') {
    message.success('签到完成')
  }
}

const handleSignCancel = () => {
  // Lane 8：取消只是停止前端等待结果，后端 HTTP 请求无法真正中断。
  // UI 文案由 ToolsTaskPanel 显示"已停止等待结果（后端可能仍在执行）"。
  signTask.cancel()
  logger.info('用户停止了签到等待（后端可能仍在执行）')
}

const handleSignRetry = async () => {
  // Lane 8：重试同样禁止重复执行，防止用户连点导致后端并发签到。
  if (signTask.isRunning.value) {
    logger.warn('签到任务正在运行，忽略重试请求')
    return
  }
  await signTask.run(performSign)
  if (signTask.status.value === 'success') {
    message.success('签到完成')
  }
}

const handleSignDismiss = () => {
  signTask.reset()
}

// ==================== 账号管理 ====================

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
  let createdUid = ''
  let pushedIndex = -1
  try {
    const result = await addAccount()
    if (!result) {
      // addAccount 已在内部提示错误
      return
    }
    createdUid = result.accountId
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
    // 先保存到本地，再尝试初始化保存。若 updateAccount 失败需回滚本地状态。
    accounts.value.push(newAccount)
    pushedIndex = accounts.value.length - 1
    try {
      await updateAccount(result.accountId, getAccountAllData(newAccount))
      message.success('用户已添加')
      openEditModal(newAccount)
    } catch (updateError) {
      // updateAccount 失败：回滚本地添加，并尝试清理后端创建的占位账号。
      if (pushedIndex >= 0 && accounts.value[pushedIndex]?.uid === createdUid) {
        accounts.value.splice(pushedIndex, 1)
      }
      const errorMsg = updateError instanceof Error ? updateError.message : String(updateError)
      logger.error(`初始化新账号 ${createdUid} 失败，尝试清理后端占位: ${errorMsg}`)
      try {
        await deleteAccount(createdUid)
      } catch (cleanupError) {
        const cleanupMsg =
          cleanupError instanceof Error ? cleanupError.message : String(cleanupError)
        logger.error(`清理后端占位账号 ${createdUid} 失败: ${cleanupMsg}`)
        message.error(`添加失败且临时账号 ${createdUid} 未能自动清理，请手动删除`)
        return
      }
      message.error(`添加用户失败: ${errorMsg}`)
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
      // Lane 8：先调用后端删除，成功后才更新本地状态。
      // 失败时抛出错误让 Modal 保持 loading 状态并提示用户。
      try {
        await deleteAccount(account.uid)
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`删除用户失败: ${errorMsg}`)
        // 重新抛出，让 a-modal 的 onOk Promise 拒绝，保持弹窗打开
        throw error
      }
      accounts.value = accounts.value.filter(a => a.uid !== account.uid)
      message.success('用户已删除')
    },
  })
}

/**
 * Lane 8：行内字段保存（如 Enabled 切换）。
 *
 * GameSignUserTable 的 a-select 通过 v-model:value 直接修改 account 对象，
 * 然后 emit('field-save', account)。这意味着本地状态已被修改。
 * 失败时必须恢复旧值，否则 UI 与后端不一致。
 */
const handleAccountFieldSave = async (account: AccountInstance) => {
  // 找到本地索引并保存旧值快照
  const idx = accounts.value.findIndex(a => a.uid === account.uid)
  if (idx < 0) {
    // 本地不存在该账号，无法保存
    return
  }
  const snapshot: AccountInstance = { ...accounts.value[idx] }
  try {
    await updateAccount(account.uid, getAccountAllData(account))
  } catch (error) {
    // 回滚本地状态到旧值
    accounts.value[idx] = snapshot
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存用户 ${account.uid} 字段失败，已回滚本地状态: ${errorMsg}`)
    message.error(`保存失败，已恢复原值: ${errorMsg}`)
  }
}

// ==================== 拖拽排序 ====================

const onDragEnd = async (evt: any) => {
  if (evt.oldIndex === evt.newIndex) return
  isDragging.value = true
  try {
    const order = accounts.value.map(a => a.uid)
    const resp = await Service.reorderGameSignAccountsApiToolsSignAccountReorderPost({ order })
    if (resp.code !== 200) {
      throw new Error(resp.message || '排序保存失败')
    }
    logger.info('用户排序已保存')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`排序保存失败: ${errorMsg}`)
    message.error('排序保存失败')
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
  const uid = editingAccount.value.uid
  const idx = accounts.value.findIndex(a => a.uid === uid)
  if (idx < 0) {
    // 账号已被删除，直接关闭模态框
    editModalVisible.value = false
    return
  }
  // Lane 8：保留旧值快照，API 失败时恢复本地状态并保留用户输入。
  // 只有 API 成功后才把 editingAccount 同步到 accounts 列表并关闭模态框。
  const snapshot: AccountInstance = { ...accounts.value[idx] }
  try {
    await updateAccount(uid, getAccountAllData(editingAccount.value))
    // API 成功后再提交本地状态变更
    accounts.value[idx] = { ...editingAccount.value }
    message.success('Token 已保存')
    editModalVisible.value = false
  } catch (error) {
    // 失败时恢复本地状态，但保留 editingAccount 中的用户输入，让用户可以重试。
    accounts.value[idx] = snapshot
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 Token 失败 (uid=${uid}): ${errorMsg}`)
    message.error(`保存失败: ${errorMsg}`)
    // 不关闭模态框，让用户可以修改后重试
  }
}

// ==================== 米游社扫码登录 ====================

const qrLogin = useMiyousheQrLogin({
  logger,
  onConfirmed: async (cookiesStr: string) => {
    if (!editingAccount.value) return false
    // 保存旧 Token，API 失败时回滚编辑态，避免错误格式 Token 被后续保存
    const oldToken = editingAccount.value.MiyousheToken
    editingAccount.value.MiyousheToken = cookiesStr
    try {
      // 保存到后端
      const { OpenAPI } = await import('@/api')
      const { authenticatedApiFetch } = await import('@/utils/httpSecurity')
      const resp = await authenticatedApiFetch(`${OpenAPI.BASE}/api/tools/sign/miyoushe/qr/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_uid: editingAccount.value.uid, cookie: cookiesStr }),
      })
      const text = await resp.text()
      const data = JSON.parse(text)
      if (data.code !== 200 || data.status === 'error') {
        throw new Error(data.message || '保存 Token 失败')
      }
      // 同步到 accounts 列表
      const idx = accounts.value.findIndex(a => a.uid === editingAccount.value!.uid)
      if (idx >= 0) {
        accounts.value[idx].MiyousheToken = cookiesStr
      }
      return true
    } catch (error) {
      // 回滚编辑态到旧 Token
      editingAccount.value.MiyousheToken = oldToken
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`扫码保存 Token 失败: ${errorMsg}`)
      return false
    }
  },
  onRefresh: async () => {
    await loadAccounts()
    if (onRefreshConfig) await onRefreshConfig()
  },
})

// ==================== 签到结果标签云 ====================

const resultStr = computed(() => config.Result)
const accountsForTags = computed<AccountLike[]>(() => accounts.value)
const { getTagsForAccount, getGroupsForPlatform } = useSignResultTags(resultStr, accountsForTags)

// ==================== 时间选择器 ====================

const windowStartValue = computed(() => {
  if (config.WindowStart) return dayjs(config.WindowStart, 'HH:mm')
  return null
})

const windowEndValue = computed(() => {
  if (config.WindowEnd) return dayjs(config.WindowEnd, 'HH:mm')
  return null
})

const handleTimeChange = (key: string, dayjsValue: any) => {
  if (dayjsValue) {
    handleChange(key, dayjsValue.format('HH:mm'))
  } else {
    handleChange(key, '')
  }
}

// ==================== 通用变更处理 ====================

const handleChange = (key: string, value: any) => {
  if (onFieldChange) onFieldChange(key, value)
}

// ==================== 生命周期 ====================

onBeforeUnmount(() => {
  if (signTask.isRunning.value) {
    signTask.cancel()
  }
})

onMounted(() => {
  loadAccounts()
})
</script>

<template>
  <div class="tab-content">
    <!-- Lane 8：异步任务状态面板 -->
    <ToolsTaskPanel
      :status="signTask.status.value"
      :error="signTask.error.value"
      :progress="signTask.progress.value"
      :task-name="signTask.taskName"
      :can-cancel="signTask.canCancel.value"
      :can-retry="signTask.canRetry.value"
      :progress-percent="signTask.progressPercent.value"
      @cancel="handleSignCancel"
      @retry="handleSignRetry"
      @dismiss="handleSignDismiss"
    />

    <!-- 全局设置区 -->
    <div class="form-section">
      <div class="section-header">
        <h3>游戏社区签到</h3>
        <a-button
          type="primary"
          :loading="signTask.isRunning.value"
          :disabled="disabled || !config.Enabled || signTask.isRunning.value"
          @click="handleManualSign"
        >
          <template #icon><SwapOutlined /></template>
          全部签到
        </a-button>
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
            <a-switch
              v-model:checked="config.Enabled"
              :disabled="disabled"
              @change="handleChange('Enabled', $event)"
            />
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
            <a-switch
              v-model:checked="config.NotifyEnabled"
              :disabled="disabled"
              @change="handleChange('NotifyEnabled', $event)"
            />
          </div>
        </a-col>
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">窗口起点</span>
              <a-tooltip title="每日签到的最早时间">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-time-picker
              :value="windowStartValue"
              format="HH:mm"
              placeholder="08:00"
              size="large"
              style="width: 100%"
              :disabled="disabled"
              @change="handleTimeChange('WindowStart', $event)"
            />
          </div>
        </a-col>
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">窗口终点</span>
              <a-tooltip title="每日签到的最晚时间">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-time-picker
              :value="windowEndValue"
              format="HH:mm"
              placeholder="22:00"
              size="large"
              style="width: 100%"
              :disabled="disabled"
              @change="handleTimeChange('WindowEnd', $event)"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <!-- 用户列表 -->
    <GameSignUserTable
      :accounts="accounts"
      :add-loading="addLoading"
      :disabled="disabled"
      :is-dragging="isDragging"
      :get-tags-for-account="getTagsForAccount"
      :get-groups-for-platform="getGroupsForPlatform"
      @add="handleAddAccount"
      @delete="handleDeleteAccount"
      @edit="openEditModal"
      @field-save="handleAccountFieldSave"
      @reorder="onDragEnd"
      @select-visible-change="onSelectVisibleChange"
    />

    <!-- 编辑 Token 模态框 -->
    <GameSignEditModal
      :visible="editModalVisible"
      :account="editingAccount"
      :qr-loading="qrLogin.loading.value"
      @update:visible="editModalVisible = $event"
      @save="handleEditModalOk"
      @start-qr="qrLogin.start"
    />

    <!-- 扫码登录弹窗 -->
    <MiyousheQrModal
      :visible="qrLogin.modalVisible.value"
      :status="qrLogin.status.value"
      :status-text="qrLogin.statusText.value"
      :qr-url="qrLogin.qrUrl.value"
      @cancel="qrLogin.close"
    />
  </div>
</template>

<style scoped>
.tab-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/*
 * iPad 设置式自适应瀑布双栏：
 * 宽容器（tools-page 容器 >980px）时卡片流入两列、各自纵向堆叠；
 * 窄容器保持上方基础规则的单列 flex 堆叠。
 * 采用 CSS multi-column：卡片 break-inside: avoid + inline-block/width:100% 防断裂，
 * 卡片内部结构不做任何改动。
 */
@container tools-page (min-width: 981px) {
  .tab-content {
    display: block;
    columns: 2;
    column-gap: var(--v6-space-3);
  }

  .tab-content > * {
    display: inline-block;
    width: 100%;
    vertical-align: top;
    break-inside: avoid;
    margin: 0 0 var(--v6-space-3);
  }

  /* 异步任务状态面板为全宽横幅，横跨双栏，出现/消失不引起列内卡片跳列 */
  .tab-content > .tools-task-panel {
    column-span: all;
  }
}

.form-section {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  padding: 20px 24px;
  border: 1px solid var(--ant-color-border);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.form-item-vertical {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.form-item-vertical :deep(.ant-switch) {
  align-self: flex-start;
  width: auto;
  max-width: 96px;
}

.form-label-wrapper {
  display: flex;
  align-items: center;
  gap: 4px;
}

.form-label {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.help-icon {
  color: var(--ant-color-text-quaternary);
  font-size: 12px;
  cursor: help;
}
</style>
