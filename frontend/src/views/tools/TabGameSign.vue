<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { QuestionCircleOutlined, EditOutlined, DeleteOutlined, PlusOutlined, SwapOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import dayjs from 'dayjs'
import draggable from 'vuedraggable'
import type { ToolsConfig_GameSign, GameSignAccountGroupConfig } from '@/api'
import { Service } from '@/api'
import { useGameSignAccountApi } from '@/composables/useGameSignAccountApi'

const { config, disabled, onFieldChange, onSelectVisibleChange } = defineProps<{
    config: ToolsConfig_GameSign
    disabled?: boolean
    onFieldChange?: (key: string, value: any) => void
    onSelectVisibleChange?: (visible: boolean) => void
}>()

const logger = window.electronAPI.getLogger('游戏签到')
const signLoading = ref(false)

// ==================== 账号管理 ====================

interface AccountInstance {
    uid: string
    type: string
    Name: string
    Enabled: boolean
    MiyousheEnabled: boolean
    MiyousheToken: string
    KuroEnabled: boolean
    KuroToken: string
    SklandEnabled: boolean
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
                MiyousheEnabled: accountData.MiyousheEnabled ?? true,
                MiyousheToken: accountData.MiyousheToken || '',
                KuroEnabled: accountData.KuroEnabled ?? true,
                KuroToken: accountData.KuroToken || '',
                SklandEnabled: accountData.SklandEnabled ?? true,
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
    MiyousheEnabled: account.MiyousheEnabled,
    MiyousheToken: account.MiyousheToken,
    KuroEnabled: account.KuroEnabled,
    KuroToken: account.KuroToken,
    SklandEnabled: account.SklandEnabled,
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
                MiyousheEnabled: true,
                MiyousheToken: '',
                KuroEnabled: true,
                KuroToken: '',
                SklandEnabled: true,
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

// 社区与游戏的映射
const platformGames: Record<string, string[]> = {
    '米游社': ['原神', '崩坏：星穹铁道', '绝区零', '崩坏3rd'],
    '森空岛': ['明日方舟', '终末地'],
    '库街区': ['鸣潮'],
}

// 获取某用户在某社区的签到结果（只绑定该用户数据）
const getUserPlatformGames = (account: AccountInstance, platform: string): GameItem[] => {
    const platformData = signResult.value[platform]
    if (!platformData) return []

    // 用用户名匹配 account_alias（别名 = account 中 '/' 前的部分）
    const userAlias = account.Name
    for (const group of platformData) {
        if (group.account_alias === userAlias) {
            return group.games
        }
    }
    return []
}

// 标签云状态类型
type TagStatus = 'signed' | 'partial' | 'unsigned' | 'unconfigured'

// 获取某用户在某社区的标签状态
const getUserPlatformStatus = (account: AccountInstance, platform: string): {
    status: TagStatus
    games: GameItem[]
    signedCount: number
    totalCount: number
} => {
    const hasToken =
        (platform === '米游社' && account.MiyousheToken && account.MiyousheEnabled) ||
        (platform === '库街区' && account.KuroToken && account.KuroEnabled) ||
        (platform === '森空岛' && account.SklandToken && account.SklandEnabled)

    if (!hasToken) {
        return { status: 'unconfigured', games: [], signedCount: 0, totalCount: 0 }
    }

    const games = getUserPlatformGames(account, platform)
    const totalCount = games.length
    const signedCount = games.filter(g => g.status === '成功' || g.status === '已签到').length

    if (totalCount === 0) {
        return { status: 'unsigned', games, signedCount: 0, totalCount: 0 }
    }
    if (signedCount === totalCount) {
        return { status: 'signed', games, signedCount, totalCount }
    }
    if (signedCount > 0) {
        return { status: 'partial', games, signedCount, totalCount }
    }
    return { status: 'unsigned', games, signedCount, totalCount }
}

// 获取某用户的所有社区标签（含未配置）
const getUserPlatformTags = (account: AccountInstance) => {
    const tags: { platform: string; status: TagStatus; games: GameItem[]; signedCount: number; totalCount: number }[] = []
    for (const platform of ['米游社', '森空岛', '库街区']) {
        const ps = getUserPlatformStatus(account, platform)
        tags.push({ platform, ...ps })
    }
    return tags
}

// 计算距离上次签到的相对时间
const getLastSignRelative = () => {
    const d = config.LastSignDate
    if (!d || d === '2000-01-01') return ''
    const signDay = dayjs(d, 'YYYY-MM-DD')
    const now = dayjs()
    const diffMinutes = now.diff(signDay, 'minute')
    if (diffMinutes < 1) return '刚刚'
    if (diffMinutes < 60) return `${diffMinutes}分钟前`
    const diffHours = now.diff(signDay, 'hour')
    if (diffHours < 24) return `${diffHours}小时前`
    const diffDays = now.diff(signDay, 'day')
    if (diffDays < 30) return `${diffDays}天前`
    return signDay.format('MM-DD')
}

const lastSignRelative = computed(() => getLastSignRelative())

// 标签文字
const getTagText = (tag: { platform: string; status: TagStatus; signedCount: number; totalCount: number }) => {
    switch (tag.status) {
        case 'signed': return `${tag.platform} ✓ ${lastSignRelative.value}`
        case 'partial': return `${tag.platform} ! ${tag.signedCount}/${tag.totalCount}`
        case 'unsigned': return `${tag.platform} ✗`
        case 'unconfigured': return `${tag.platform} -`
    }
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
                                <a-space :size="8" wrap>
                                    <a-tooltip v-for="tag in getUserPlatformTags(account)" :key="tag.platform">
                                        <template #title>
                                            <div class="sign-tooltip">
                                                <div class="sign-tooltip-title">{{ tag.platform }} - 签到详情</div>
                                                <div v-for="game in tag.games" :key="game.game" class="sign-tooltip-row">
                                                    <span>{{ game.game }}</span>
                                                    <span :class="game.status === '成功' || game.status === '已签到' ? 'tt-signed' : 'tt-unsigned'">
                                                        ● {{ game.status === '成功' || game.status === '已签到' ? '已签' : '未签' }}
                                                    </span>
                                                </div>
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
            @ok="handleEditModalOk" ok-text="保存" cancel-text="取消" :width="520">
            <div v-if="editingAccount" class="modal-form">
                <div class="form-item-vertical">
                    <span class="form-label">用户名称</span>
                    <a-input v-model:value="editingAccount.Name" />
                </div>
                <div class="form-item-vertical">
                    <span class="form-label">是否启用</span>
                    <a-select v-model:value="editingAccount.Enabled" style="width: 100%">
                        <a-select-option :value="true">启用</a-select-option>
                        <a-select-option :value="false">禁用</a-select-option>
                    </a-select>
                </div>
                <a-divider orientation="left" style="font-size: 13px; color: #666;">米游社</a-divider>
                <div class="form-item-vertical">
                    <div class="modal-platform-row">
                        <a-select v-model:value="editingAccount.MiyousheEnabled" size="small" style="width: 72px">
                            <a-select-option :value="true">启用</a-select-option>
                            <a-select-option :value="false">禁用</a-select-option>
                        </a-select>
                        <span class="modal-platform-label">米游社签到</span>
                    </div>
                    <a-input-password v-model:value="editingAccount.MiyousheToken"
                        placeholder="浏览器 F12 → document.cookie 获取" allow-clear />
                </div>
                <a-divider orientation="left" style="font-size: 13px; color: #666;">库街区</a-divider>
                <div class="form-item-vertical">
                    <div class="modal-platform-row">
                        <a-select v-model:value="editingAccount.KuroEnabled" size="small" style="width: 72px">
                            <a-select-option :value="true">启用</a-select-option>
                            <a-select-option :value="false">禁用</a-select-option>
                        </a-select>
                        <span class="modal-platform-label">库街区签到</span>
                    </div>
                    <a-input-password v-model:value="editingAccount.KuroToken"
                        placeholder="抓包或短信验证码获取 Token" allow-clear />
                </div>
                <a-divider orientation="left" style="font-size: 13px; color: #666;">森空岛</a-divider>
                <div class="form-item-vertical">
                    <div class="modal-platform-row">
                        <a-select v-model:value="editingAccount.SklandEnabled" size="small" style="width: 72px">
                            <a-select-option :value="true">启用</a-select-option>
                            <a-select-option :value="false">禁用</a-select-option>
                        </a-select>
                        <span class="modal-platform-label">森空岛签到</span>
                    </div>
                    <a-input-password v-model:value="editingAccount.SklandToken"
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
    border: 1px solid var(--ant-color-border-secondary);
    border-radius: 8px;
    overflow: hidden;
}

.user-table-header {
    display: flex;
    align-items: center;
    background: var(--ant-color-fill-quaternary);
    border-bottom: 1px solid var(--ant-color-border-secondary);
    font-size: 14px;
    font-weight: 600;
    color: var(--ant-color-text-secondary);
    min-height: 48px;
}

.user-table-header .header-cell {
    padding: 14px 16px;
}

.drag-cell { width: 52px; min-width: 52px; text-align: center; }
.name-cell { width: 140px; min-width: 140px; }
.status-cell { width: 110px; min-width: 110px; }
.tags-cell { flex: 1; min-width: 0; }
.actions-cell { width: 180px; min-width: 180px; text-align: right; }

.user-draggable { min-height: 56px; }

.user-row {
    display: flex;
    align-items: center;
    min-height: 60px;
    border-bottom: 1px solid var(--ant-color-border-secondary);
    padding: 10px 0;
    transition: background 0.15s ease;
}

.user-row:last-child { border-bottom: none; }
.user-row:hover { background: var(--ant-color-fill-quaternary); }

.row-cell { padding: 8px 16px; }

/* 拖拽手柄 */
.drag-handle { cursor: grab; display: inline-flex; align-items: center; justify-content: center; }
.drag-handle:active { cursor: grabbing; }
.drag-dots {
    width: 14px; height: 20px; display: block;
    background-image: radial-gradient(currentColor 1.4px, transparent 1.4px);
    background-size: 6px 6px; opacity: 0.5;
}

/* 拖拽视觉反馈 */
.user-ghost { opacity: 0.4; background: #e6f7ff; }
.user-chosen { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12); }
.user-drag { box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15); }

/* 用户名 */
.user-name-text { font-weight: 600; font-size: 15px; color: var(--ant-color-text); }

/* ==================== 社区标签云（多色） ==================== */
.platform-tag {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 13px;
    line-height: 1.6;
    border: 1px solid transparent;
    cursor: default;
    white-space: nowrap;
}

.tag-signed {
    background: #f6ffed;
    border-color: #b7eb8f;
    color: #52c41a;
}

.tag-partial {
    background: #fff7e6;
    border-color: #ffd591;
    color: #fa8c16;
}

.tag-unsigned {
    background: #fff1f0;
    border-color: #ffa39e;
    color: #f5222d;
}

.tag-unconfigured {
    background: #f5f5f5;
    border-color: #d9d9d9;
    color: #999;
}

/* ==================== Tooltip 签到详情 ==================== */
.sign-tooltip { min-width: 200px; }
.sign-tooltip-title {
    font-size: 14px; font-weight: 600;
    padding-bottom: 8px; margin-bottom: 6px;
    border-bottom: 1px solid #f0f0f0;
}
.sign-tooltip-row { display: flex; justify-content: space-between; padding: 3px 0; font-size: 14px; }
.tt-signed { color: #52c41a; }
.tt-unsigned { color: #fa8c16; }
.sign-tooltip-empty { color: var(--ant-color-text-quaternary); font-size: 13px; text-align: center; padding: 8px 0; }

/* ==================== 操作按钮 ==================== */
.action-btn {
    padding: 5px 14px;
    border-radius: 4px;
    font-size: 14px;
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
.modal-platform-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.modal-platform-label { font-size: 14px; font-weight: 500; color: var(--ant-color-text); }
</style>
