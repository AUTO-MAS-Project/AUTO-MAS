<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { QuestionCircleOutlined, EditOutlined, DeleteOutlined, PlusOutlined, SwapOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import dayjs from 'dayjs'
import draggable from 'vuedraggable'
import type { ToolsConfig_GameSign, GameSignAccountGroupConfig } from '@/api'
import { Service } from '@/api'
import { useGameSignAccountApi } from '@/composables/useGameSignAccountApi'

const { config, disabled, onFieldChange, onSelectVisibleChange, onRefreshConfig } = defineProps<{
    config: ToolsConfig_GameSign
    disabled?: boolean
    onFieldChange?: (key: string, value: any) => void
    onSelectVisibleChange?: (visible: boolean) => void
    onRefreshConfig?: () => Promise<void>
}>()

const logger = window.electronAPI.getLogger('游戏签到')
const signLoading = ref(false)

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
    } catch {
        // 静默失败
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
        await Service.reorderGameSignAccountsApiToolsSignAccountReorderPost({ order })
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
    try {
        const uid = editingAccount.value.uid
        const idx = accounts.value.findIndex(a => a.uid === uid)
        if (idx >= 0) {
            accounts.value[idx] = { ...editingAccount.value }
            await updateAccount(uid, getAccountAllData(editingAccount.value))
            message.success('Token 已保存')
        }
    } catch {
        message.error('保存失败，请重试')
    }
    editModalVisible.value = false
}

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
type TagStatus = 'signed' | 'partial' | 'unsigned' | 'failed' | 'unconfigured'

// 平台标签数据结构
interface PlatformTag {
    platform: string
    status: TagStatus
    games: GameItem[]
    groups: AccountGroup[]
    signedCount: number
    totalCount: number
    failedCount: number
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

            let status: TagStatus
            if (totalCount === 0) {
                status = 'unsigned'
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
                signedCount: status === 'unsigned' ? 0 : signedCount,
                totalCount: status === 'unsigned' ? 0 : totalCount,
                failedCount: status === 'unsigned' ? 0 : failedCount,
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
const getAccountGroupsForPlatformReactive = (account: AccountInstance, platform: string): AccountGroup[] => {
    const tags = userTagsMap.value.get(account.uid) || []
    const tag = tags.find(t => t.platform === platform)
    return tag?.groups || []
 }

// 标签文字 — 只显示社区名，状态由标签颜色表达
const getTagText = (tag: { platform: string; status: TagStatus; signedCount: number; totalCount: number; failedCount: number }) => {
    return tag.platform
}

// 标签 CSS 类
const getTagClass = (status: TagStatus) => `tag-${status}`

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

// ==================== 手动签到 ====================

const handleManualSign = async () => {
    signLoading.value = true
    try {
        const response = await Service.manualGameSignApiToolsSignPost()
        if (response.code !== 200 && response.code !== 0) {
            throw new Error(response.message || '签到失败')
        }
        logger.info('游戏签到完成')
        message.success('签到完成')
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
                <a-button type="primary" :loading="signLoading"
                    :disabled="disabled || !config.Enabled"
                    @click="handleManualSign">
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
                        <a-select v-model:value="config.Enabled" size="large" style="width: 100%" :disabled="disabled"
                            @change="handleChange('Enabled', $event)" @dropdownVisibleChange="onSelectVisibleChange">
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
                        <a-select v-model:value="config.NotifyEnabled" size="large" style="width: 100%"
                            :disabled="disabled" @change="handleChange('NotifyEnabled', $event)"
                            @dropdownVisibleChange="onSelectVisibleChange">
                            <a-select-option :value="true">启用</a-select-option>
                            <a-select-option :value="false">禁用</a-select-option>
                        </a-select>
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
                        <a-time-picker :value="windowStartValue" format="HH:mm" placeholder="08:00" size="large"
                            style="width: 100%" :disabled="disabled"
                            @change="handleTimeChange('WindowStart', $event)" />
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
                        <a-time-picker :value="windowEndValue" format="HH:mm" placeholder="22:00" size="large"
                            style="width: 100%" :disabled="disabled"
                            @change="handleTimeChange('WindowEnd', $event)" />
                    </div>
                </a-col>
            </a-row>
        </div>

        <!-- 用户列表 -->
        <div class="form-section">
            <div class="section-header">
                <h3>用户列表</h3>
                <a-button type="primary" ghost size="middle" :loading="addLoading" :disabled="disabled"
                    @click="handleAddAccount">
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
                <draggable v-model="accounts" item-key="uid" :animation="200" :disabled="disabled || isDragging"
                    ghost-class="user-ghost" chosen-class="user-chosen" drag-class="user-drag" handle=".drag-handle"
                    class="user-draggable" @end="onDragEnd">
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
                                <a-select v-model:value="account.Enabled" size="middle" style="width: 100px"
                                    :disabled="disabled" @change="handleAccountFieldSave(account)"
                                    @dropdownVisibleChange="onSelectVisibleChange"
                                    :class="{ 'select-enabled': account.Enabled }">
                                    <a-select-option :value="true">启用</a-select-option>
                                    <a-select-option :value="false">禁用</a-select-option>
                                </a-select>
                            </div>
                            <!-- 社区签到情况（标签云） -->
                            <div class="row-cell tags-cell">
                                <a-space :size="6" wrap>
                                    <a-tooltip v-for="tag in getUserPlatformTagsReactive(account)" :key="tag.platform">
                                        <template #title>
                                            <div class="sign-tooltip">
                                                <div class="sign-tooltip-title">{{ tag.platform }} - 签到详情</div>
                                                <template v-for="(group, gIdx) in getAccountGroupsForPlatformReactive(account, tag.platform)" :key="gIdx">
                                                    <div class="sign-tooltip-alias">{{ group.account_alias }}</div>
                                                    <div v-for="game in group.games" :key="game.game" class="sign-tooltip-row">
                                                        <span>{{ game.game }}</span>
                                                        <span :class="game.status === '成功' || game.status === '已签到' ? 'tt-signed' : game.status === '失败' ? 'tt-failed' : 'tt-unsigned'">
                                                            ● {{ game.status === '成功' || game.status === '已签到' ? '已签' : game.status === '失败' ? '失败' : '未签' }}
                                                        </span>
                                                        <span v-if="game.reward" class="tt-reward">{{ game.reward }}</span>
                                                    </div>
                                                </template>
                                                <div v-if="tag.games.length === 0" class="sign-tooltip-empty">暂无签到数据</div>
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
                                    <a-button size="middle" class="action-btn edit-btn" @click="openEditModal(account)">
                                        <template #icon><EditOutlined /></template>
                                        编辑
                                    </a-button>
                                    <a-popconfirm title="确定要删除此用户吗？" ok-text="确定" cancel-text="取消"
                                        @confirm="handleDeleteAccount(account)">
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
        <a-modal v-model:open="editModalVisible" :title="`编辑 — ${editingAccount?.Name || ''}`"
            @ok="handleEditModalOk" ok-text="保存" cancel-text="取消" :width="560">
            <div v-if="editingAccount" class="modal-form">
                <div class="form-item-vertical">
                    <span class="form-label">用户名称</span>
                    <a-input v-model:value="editingAccount.Name" size="large" />
                </div>
                <a-divider orientation="left" style="font-size: 13px; color: #666;">米游社</a-divider>
                <div class="form-item-vertical">
                    <a-input-password v-model:value="editingAccount.MiyousheToken" size="large"
                        placeholder="浏览器 F12 → document.cookie 获取" allow-clear />
                </div>
                <a-divider orientation="left" style="font-size: 13px; color: #666;">库街区</a-divider>
                <div class="form-item-vertical">
                    <a-input-password v-model:value="editingAccount.KuroToken" size="large"
                        placeholder="抓包或短信验证码获取 Token" allow-clear />
                </div>
                <a-divider orientation="left" style="font-size: 13px; color: #666;">森空岛</a-divider>
                <div class="form-item-vertical">
                    <a-input-password v-model:value="editingAccount.SklandToken" size="large"
                        placeholder="鹰角网络通行证登录凭证" allow-clear />
                </div>
            </div>
        </a-modal>
    </div>
</template>

<style scoped>
/* ==================== 选中启用时边框变绿 ==================== */
.select-enabled :deep(.ant-select-selector) {
    border-color: #52c41a !important;
}

/* ==================== 用户列表表格 ==================== */
.user-table-container {
    border: 1px solid var(--ant-color-border);
    border-radius: 6px;
    overflow: hidden;
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

.drag-cell { width: 36px; min-width: 36px; max-width: 36px; text-align: center; }
.name-cell { width: 140px; min-width: 140px; }
.status-cell { width: 120px; min-width: 120px; }
.tags-cell { flex: 1; min-width: 0; }
.actions-cell { width: 180px; min-width: 180px; text-align: right; }

.user-draggable { min-height: 60px; }

.user-row {
    display: flex;
    align-items: center;
    min-height: 64px;
    border-bottom: 1px solid var(--ant-color-border);
    padding: 0;
    transition: background 0.2s ease;
    cursor: default;
}

.user-row:last-child { border-bottom: none; }
.user-row:hover { background-color: var(--ant-color-fill-quaternary); }

.row-cell {
    padding: 14px 16px;
    text-align: center;
    border-right: 1px solid var(--ant-color-border);
    display: flex;
    align-items: center;
    justify-content: center;
}

.row-cell:last-child { border-right: none; }

.row-cell.name-cell { justify-content: flex-start; }
.row-cell.tags-cell { justify-content: flex-start; padding-right: 16px; }
.row-cell.actions-cell { justify-content: flex-end; padding-left: 24px; }

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

.drag-handle:active { cursor: grabbing; }

.drag-dots {
    width: 10px;
    height: 16px;
    display: block;
    background-image: radial-gradient(currentColor 1.2px, transparent 1.2px);
    background-size: 5px 5px;
    opacity: 0.65;
}

.drag-handle:hover .drag-dots { opacity: 0.85; }

/* 拖拽视觉反馈 */
.user-ghost { opacity: 0 !important; background: transparent !important; border-color: transparent !important; }
.user-chosen { cursor: grabbing !important; }
.user-drag { transform: rotate(3deg); opacity: 1 !important; }

/* 用户名 */
.user-name-text { font-weight: 600; font-size: 14px; color: var(--ant-color-text); }

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

.status-select :deep(.ant-select-clear) { display: none !important; }

.status-select :deep(.ant-select-selection-search) { margin: 0 !important; padding: 0; }

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

/* 橙色：部分签到 */
.tag-partial {
    background: #fff7e6;
    border-color: #ffd591;
    color: #fa8c16;
}

/* ==================== Tooltip 签到详情 ==================== */
.sign-tooltip { min-width: 220px; }
.sign-tooltip-title {
    font-size: 13px; font-weight: 600;
    padding-bottom: 8px; margin-bottom: 6px;
    border-bottom: 1px solid #f0f0f0;
}
.sign-tooltip-alias {
    font-size: 12px; font-weight: 600; color: var(--ant-color-text);
    padding: 4px 0 2px; margin-top: 4px;
}
.sign-tooltip-alias:first-of-type { margin-top: 0; }
.sign-tooltip-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 2px 0; font-size: 13px; gap: 12px;
}
.tt-signed { color: #52c41a; }
.tt-unsigned { color: #d4b106; }
.tt-failed { color: #f5222d; }
.tt-reward { color: var(--ant-color-text-tertiary); font-size: 12px; }
.sign-tooltip-empty { color: var(--ant-color-text-quaternary); font-size: 13px; text-align: center; padding: 8px 0; }

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
    border-color: #d9d9d9;
    color: #666;
}

.edit-btn:hover {
    border-color: #1890ff;
    color: #1890ff;
}

.delete-btn {
    border-color: #ff4d4f;
    color: #ff4d4f;
}

.delete-btn:hover {
    border-color: #ff7875;
    color: #ff7875;
}

/* ==================== 空状态 ==================== */
.empty-state { text-align: center; padding: 48px 0; }
.empty-hint { color: var(--ant-color-text-tertiary); font-size: 15px; margin-bottom: 6px; }
.empty-guide { color: var(--ant-color-text-quaternary); font-size: 13px; }

/* ==================== 模态框 ==================== */
.modal-form .form-item-vertical { margin-bottom: 16px; }
</style>
