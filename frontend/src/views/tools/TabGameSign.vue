<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import dayjs from 'dayjs'
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

// ==================== 账号组管理 ====================

interface AccountInstance {
    uid: string
    type: string
    Name: string
    MiyousheToken: string
    KuroToken: string
    SklandToken: string
}

const { addAccount, updateAccount, deleteAccount } = useGameSignAccountApi()
const accounts = ref<AccountInstance[]>([])
const activeCollapseKeys = ref<string[]>([])
const addLoading = ref(false)

const loadAccounts = async () => {
    try {
        const response = await Service.listGameSignAccountsApiToolsSignAccountListPost()
        if (response.code !== 200) return
        const data = response.data as any
        const instances: AccountInstance[] = []
        // MultipleConfig.toDict() 格式: { instances: [{uid, type}], <uuid>: {GameSignAccount: {...}} }
        const instanceList = data?.instances || []
        for (const inst of instanceList) {
            const uid = inst.uid as string
            const accountData = data?.[uid]?.GameSignAccount || {}
            instances.push({
                uid,
                type: inst.type || 'GameSignAccountGroup',
                Name: accountData.Name || '默认账号',
                MiyousheToken: accountData.MiyousheToken || '',
                KuroToken: accountData.KuroToken || '',
                SklandToken: accountData.SklandToken || '',
            })
        }
        accounts.value = instances
        // 默认展开第一个
        if (instances.length > 0 && activeCollapseKeys.value.length === 0) {
            activeCollapseKeys.value = [instances[0].uid]
        }
    } catch {
        // 静默失败
    }
}

const handleAddAccount = async () => {
    addLoading.value = true
    try {
        const result = await addAccount()
        if (result) {
            // 自动命名：账号组 1、账号组 2、...
            const defaultName = `账号组 ${accounts.value.length + 1}`
            accounts.value.push({
                uid: result.accountId,
                type: 'GameSignAccountGroup',
                Name: defaultName,
                MiyousheToken: result.data.MiyousheToken || '',
                KuroToken: result.data.KuroToken || '',
                SklandToken: result.data.SklandToken || '',
            })
            activeCollapseKeys.value = [result.accountId]
            // 立即更新后端名称
            await updateAccount(result.accountId, {
                Name: defaultName,
                MiyousheToken: '',
                KuroToken: '',
                SklandToken: '',
            })
            message.success('账号组已添加')
        }
    } finally {
        addLoading.value = false
    }
}

const handleDeleteAccount = (account: AccountInstance) => {
    Modal.confirm({
        title: '删除账号组',
        content: `确定要删除「${account.Name}」吗？该操作不可撤销。`,
        okText: '删除',
        okType: 'danger',
        cancelText: '取消',
        onOk: async () => {
            await deleteAccount(account.uid)
            accounts.value = accounts.value.filter(a => a.uid !== account.uid)
            activeCollapseKeys.value = activeCollapseKeys.value.filter(k => k !== account.uid)
        },
    })
}

const handleTokenBlur = async (account: AccountInstance, field: keyof AccountInstance) => {
    try {
        await updateAccount(account.uid, {
            Name: account.Name,
            MiyousheToken: account.MiyousheToken,
            KuroToken: account.KuroToken,
            SklandToken: account.SklandToken,
        })
    } catch {
        message.error('保存失败，请重试')
    }
}

const getAccountSummary = (account: AccountInstance): string => {
    const platforms: string[] = []
    if (account.MiyousheToken) platforms.push('米游社 ✓')
    if (account.KuroToken) platforms.push('库街区 ✓')
    if (account.SklandToken) platforms.push('森空岛 ✓')
    return platforms.length > 0 ? platforms.join('  ') : '未配置任何平台'
}

// ==================== 签到结果解析 ====================

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

const platformOrder = ['米游社', '库街区', '森空岛']
const sortedPlatforms = computed(() => {
    const platforms = Object.keys(signResult.value)
    return platformOrder.filter(p => platforms.includes(p))
})
// 未出现在结果中的平台，用于填充空位卡片
const emptyPlatforms = computed(() => {
    return platformOrder.filter(p => !sortedPlatforms.value.includes(p))
})

// ==================== 时间选择器 ====================

const windowStartValue = computed(() => {
    if (config.WindowStart) {
        return dayjs(config.WindowStart, 'HH:mm')
    }
    return null
})

const windowEndValue = computed(() => {
    if (config.WindowEnd) {
        return dayjs(config.WindowEnd, 'HH:mm')
    }
    return null
})

const handleTimeChange = (key: string, dayjsValue: any) => {
    if (dayjsValue) {
        const timeStr = dayjsValue.format('HH:mm')
        handleChange(key, timeStr)
    } else {
        handleChange(key, '')
    }
}

// ==================== 通用变更处理 ====================

const handleChange = (key: string, value: any) => {
    if (onFieldChange) {
        onFieldChange(key, value)
    }
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
        <!-- 签到结果面板 -->
        <div class="form-section">
            <div class="section-header">
                <h3>签到结果</h3>
            </div>
            <a-row :gutter="16">
                <a-col :span="8" v-for="platform in sortedPlatforms" :key="platform">
                    <div class="result-panel">
                        <div class="panel-header">{{ platform }}</div>
                        <div class="panel-body">
                            <template v-if="signResult[platform]?.length">
                                <div v-for="account in signResult[platform]" :key="account.account_alias"
                                    class="account-row">
                                    <div class="account-name">{{ account.account_alias }}</div>
                                    <div v-for="game in account.games" :key="game.game" class="game-row">
                                        <a-tag :color="game.status === '成功' || game.status === '已签到' ? 'success' : 'error'"
                                            style="margin: 0;">
                                            {{ game.game }}
                                        </a-tag>
                                        <span class="game-detail">
                                            <template v-if="game.status === '成功'">
                                                成功<template v-if="game.reward"> ({{ game.reward }})</template>
                                            </template>
                                            <template v-else-if="game.status === '已签到'">
                                                已签
                                            </template>
                                            <template v-else>
                                                失败<template v-if="game.reason"> ({{ game.reason }})</template>
                                            </template>
                                        </span>
                                    </div>
                                </div>
                            </template>
                            <div v-else class="no-data">暂无数据</div>
                        </div>
                    </div>
                </a-col>
                <!-- 空位填充（平台不足3个时） -->
                <a-col :span="8" v-for="platform in emptyPlatforms" :key="'empty-' + platform">
                    <div class="result-panel">
                        <div class="panel-header">{{ platform }}</div>
                        <div class="panel-body">
                            <div class="no-data">暂无数据</div>
                        </div>
                    </div>
                </a-col>
            </a-row>
        </div>

        <!-- 签到设置 -->
        <div class="form-section">
            <div class="section-header">
                <h3>签到设置</h3>
                <a-button type="primary" :loading="signLoading" size="small"
                    :disabled="disabled || !config.Enabled" @click="handleManualSign">
                    立即签到
                </a-button>
            </div>
            <a-row :gutter="24">
                <a-col :span="8">
                    <div class="form-item-vertical">
                        <div class="form-label-wrapper">
                            <span class="form-label">启用签到</span>
                            <a-tooltip title="是否启用每日自动游戏社区签到">
                                <QuestionCircleOutlined class="help-icon" />
                            </a-tooltip>
                        </div>
                        <a-select v-model:value="config.Enabled" size="large" style="width: 100%" :disabled="disabled"
                            @change="handleChange('Enabled', $event)"
                            @dropdownVisibleChange="onSelectVisibleChange">
                            <a-select-option :value="true">启用</a-select-option>
                            <a-select-option :value="false">禁用</a-select-option>
                        </a-select>
                    </div>
                </a-col>
                <a-col :span="8">
                    <div class="form-item-vertical">
                        <div class="form-label-wrapper">
                            <span class="form-label">签到后发送通知</span>
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
            </a-row>
            <a-row :gutter="24" style="margin-top: 16px;">
                <a-col :span="8">
                    <div class="form-item-vertical">
                        <div class="form-label-wrapper">
                            <span class="form-label">签到窗口起点</span>
                            <a-tooltip title="每日签到的最早时间">
                                <QuestionCircleOutlined class="help-icon" />
                            </a-tooltip>
                        </div>
                        <a-time-picker :value="windowStartValue" format="HH:mm" placeholder="请选择时间" size="large"
                            style="width: 100%" :disabled="disabled"
                            @change="handleTimeChange('WindowStart', $event)" />
                    </div>
                </a-col>
                <a-col :span="8">
                    <div class="form-item-vertical">
                        <div class="form-label-wrapper">
                            <span class="form-label">签到窗口终点</span>
                            <a-tooltip title="每日签到的最晚时间">
                                <QuestionCircleOutlined class="help-icon" />
                            </a-tooltip>
                        </div>
                        <a-time-picker :value="windowEndValue" format="HH:mm" placeholder="请选择时间" size="large"
                            style="width: 100%" :disabled="disabled"
                            @change="handleTimeChange('WindowEnd', $event)" />
                    </div>
                </a-col>
            </a-row>
        </div>

        <!-- 账号管理（折叠式） -->
        <div class="form-section">
            <div class="section-header">
                <h3>账号管理</h3>
                <a-button type="dashed" size="small" :loading="addLoading" :disabled="disabled"
                    @click="handleAddAccount">
                    + 添加账号组
                </a-button>
            </div>
            <a-collapse v-model:activeKey="activeCollapseKeys" :bordered="false" class="account-collapse">
                <a-collapse-panel v-for="account in accounts" :key="account.uid">
                    <template #header>
                        <div class="account-panel-header">
                            <span class="account-panel-name">{{ account.Name }}</span>
                            <span class="account-panel-summary">{{ getAccountSummary(account) }}</span>
                        </div>
                    </template>
                    <a-row :gutter="24">
                        <a-col :span="8">
                            <div class="form-item-vertical">
                                <span class="form-label">米游社登录凭证</span>
                                <a-input-password v-model:value="account.MiyousheToken" size="large"
                                    placeholder="浏览器 F12 → document.cookie 获取" allow-clear :disabled="disabled"
                                    @blur="handleTokenBlur(account, 'MiyousheToken')" />
                            </div>
                        </a-col>
                        <a-col :span="8">
                            <div class="form-item-vertical">
                                <span class="form-label">库街区登录凭证</span>
                                <a-input-password v-model:value="account.KuroToken" size="large"
                                    placeholder="抓包或短信验证码获取 Token" allow-clear :disabled="disabled"
                                    @blur="handleTokenBlur(account, 'KuroToken')" />
                            </div>
                        </a-col>
                        <a-col :span="8">
                            <div class="form-item-vertical">
                                <span class="form-label">森空岛登录凭证</span>
                                <a-input-password v-model:value="account.SklandToken" size="large"
                                    placeholder="鹰角网络通行证登录凭证" allow-clear :disabled="disabled"
                                    @blur="handleTokenBlur(account, 'SklandToken')" />
                            </div>
                        </a-col>
                    </a-row>
                    <div class="account-actions">
                        <a-button type="text" danger size="small" @click="handleDeleteAccount(account)">
                            删除账号组
                        </a-button>
                    </div>
                </a-collapse-panel>
            </a-collapse>
            <div v-if="accounts.length === 0" class="no-accounts">
                <span>暂无账号组，请点击「+ 添加账号组」创建</span>
            </div>
        </div>
    </div>
</template>

<style scoped>
/* 签到结果面板 */
.result-panel {
    background: var(--ant-color-bg-container);
    border: 1px solid var(--ant-color-border);
    border-radius: 8px;
    padding: 12px;
    min-height: 120px;
    transition: all 0.3s ease;
}

.result-panel:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.panel-header {
    font-size: 14px;
    font-weight: 600;
    color: var(--ant-color-text);
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--ant-color-border-secondary);
}

.panel-body {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.account-row {
    margin-bottom: 6px;
}

.account-name {
    font-weight: 600;
    font-size: 13px;
    color: var(--ant-color-text);
    margin-bottom: 4px;
    padding-left: 8px;
    border-left: 3px solid var(--ant-color-primary);
}

.game-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    line-height: 1.6;
}

.game-detail {
    color: var(--ant-color-text-secondary);
}

.no-data {
    color: var(--ant-color-text-tertiary);
    font-size: 13px;
    text-align: center;
    padding: 16px 0;
}

/* 账号管理折叠面板 */
.account-collapse {
    background: transparent;
}

.account-collapse :deep(.ant-collapse-item) {
    border: 1px solid var(--ant-color-border);
    border-radius: 8px !important;
    margin-bottom: 8px;
    overflow: hidden;
}

.account-collapse :deep(.ant-collapse-header) {
    align-items: center !important;
}

.account-panel-header {
    display: flex;
    align-items: center;
    gap: 12px;
}

.account-panel-name {
    font-weight: 600;
    font-size: 14px;
    color: var(--ant-color-text);
}

.account-panel-summary {
    font-size: 12px;
    color: var(--ant-color-text-secondary);
}

.account-actions {
    margin-top: 12px;
    padding-top: 8px;
    border-top: 1px solid var(--ant-color-border-secondary);
    text-align: right;
}

.no-accounts {
    color: var(--ant-color-text-tertiary);
    font-size: 13px;
    text-align: center;
    padding: 24px 0;
}
</style>
