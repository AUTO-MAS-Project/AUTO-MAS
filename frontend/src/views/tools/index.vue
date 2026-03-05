<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref, computed } from 'vue'
import { useEventListener } from '@vueuse/core'
import type { ToolsConfig } from '@/api'
import { useToolsApi } from '@/composables/useToolsApi'
import { useStatusTag, createStatusTag } from '@/composables/useStatusTag'
import TabArknightsPC from './TabArknightsPC.vue'
const logger = window.electronAPI.getLogger('工具')

const { loading, getTools, updateTools } = useToolsApi()

// 活动标签
const activeKey = ref('arknightspc')

// 工具数据
const toolsConfig = reactive<ToolsConfig>({
    ArknightsPC: {
        Enabled: false,
        PauseKey: 'f10',
        SelectDeployedKey: 'w',
        UseSkillKey: 'r',
        RetreatKey: 't',
        NextFrameKey: 'f',
        AnotherQuitKey: 'space',
        Status: '-',
    },
})

// 本地编辑状态
const editingConfig = reactive<ToolsConfig>({
    ArknightsPC: {
        Enabled: false,
        PauseKey: 'f10',
        SelectDeployedKey: 'w',
        UseSkillKey: 'r',
        RetreatKey: 't',
        NextFrameKey: 'f',
        AnotherQuitKey: 'space',
        Status: '-',
    },
})

// 使用通用的状态标签解析
const arknightsPCStatusTag = useStatusTag(
    () => toolsConfig.ArknightsPC?.Status,
    createStatusTag('未启用', 'default')
)

// 轮询定时器
let pollTimer: NodeJS.Timeout | null = null

// 仅更新状态（不影响编辑状态）
const updateStatus = async () => {
    // 如果下拉框正在打开，跳过更新避免干扰用户操作
    if (isSelectOpen.value) {
        return
    }
    try {
        const data = await getTools()
        if (data.ArknightsPC?.Status) {
            // 只更新 toolsConfig 的状态，不更新 editingConfig
            // 这样轮询只影响状态标签显示，不会触发编辑表单重新渲染
            toolsConfig.ArknightsPC!.Status = data.ArknightsPC.Status
        }
    } catch (error) {
        // 静默失败，不影响用户操作
    }
}

// 启动状态轮询
const startStatusPolling = () => {
    if (pollTimer) {
        clearInterval(pollTimer)
    }
    pollTimer = setInterval(() => {
        updateStatus()
    }, 1000) // 每秒更新一次
}

// 停止状态轮询
const stopStatusPolling = () => {
    if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
    }
}

// 加载配置
const loadTools = async () => {
    try {
        const data = await getTools()
        // 确保 ArknightsPC 配置存在
        if (!data.ArknightsPC) {
            data.ArknightsPC = {
                Enabled: false,
                PauseKey: 'f10',
                SelectDeployedKey: 'w',
                UseSkillKey: 'r',
                RetreatKey: 't',
                NextFrameKey: 'f',
                AnotherQuitKey: 'space',
                Status: '-',
            }
        }
        Object.assign(toolsConfig, data)
        Object.assign(editingConfig, JSON.parse(JSON.stringify(data)))
        logger.info('工具加载完成')
    } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`加载工具失败: ${errorMsg}`)
    }
}

// 保存单个字段的变更（实时保存）
const handleFieldChange = async (key: string, value: any) => {
    if (!editingConfig.ArknightsPC) return

    try {
        // 更新编辑状态
        (editingConfig.ArknightsPC as any)[key] = value

        // 立即保存到后端
        await updateTools(editingConfig)

        // 保存成功后只同步修改的字段到 toolsConfig，不触碰 Status
        if (toolsConfig.ArknightsPC && key !== 'Status') {
            (toolsConfig.ArknightsPC as any)[key] = value
        }

        logger.info(`${key} 已保存`)
    } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`保存 ${key} 失败: ${errorMsg}`)
    }
}

// 键位录制状态
const recordingKeyField = ref<string | null>(null)

// 下拉框打开状态
const isSelectOpen = ref<boolean>(false)

// 处理下拉框可见性变化
const handleSelectVisibleChange = (visible: boolean) => {
    isSelectOpen.value = visible
    if (visible) {
        logger.debug('下拉框打开，暂停轮询')
    } else {
        logger.debug('下拉框关闭，恢复轮询')
    }
}

// 开始录制键位
const startRecordKey = (fieldName: string) => {
    recordingKeyField.value = fieldName
    logger.info(`开始录制键位: ${fieldName}`)
}

// 停止录制键位
const stopRecordKey = () => {
    recordingKeyField.value = null
}

// 键盘事件处理 - 捕获单个键
const handleKeyDown = async (event: KeyboardEvent) => {
    if (!recordingKeyField.value) return

    event.preventDefault()
    event.stopPropagation()

    // 获取按键名称
    let keyName: string

    // 特殊键处理
    if (event.key === ' ') {
        keyName = 'space'
    } else if (event.key.length === 1) {
        // 单字符键，转为小写
        keyName = event.key.toLowerCase()
    } else {
        // 功能键（如 F1-F12, Escape, Enter 等）
        keyName = event.key.toLowerCase()
    }

    const fieldName = recordingKeyField.value

    // 停止录制
    stopRecordKey()

    // 立即保存
    await handleFieldChange(fieldName, keyName)
}

// 使用 VueUse 的 useEventListener 管理键盘事件
useEventListener(document, 'keydown', handleKeyDown)

// 生命周期：加载配置并启动轮询
onMounted(async () => {
    await loadTools()
    startStatusPolling()
})

// 生命周期：停止轮询
onUnmounted(() => {
    stopStatusPolling()
})
</script>

<template>
    <div class="settings-container">
        <div class="settings-header">
            <h1 class="page-title">工具</h1>
        </div>
        <div class="settings-content">
            <a-tabs v-model:active-key="activeKey" type="card" :loading="loading" class="settings-tabs">
                <a-tab-pane key="arknightspc">
                    <template #tab>
                        <span style="display: flex; align-items: center; gap: 8px;">
                            <span>明日方舟PC端</span>
                            <a-tag v-if="arknightsPCStatusTag" :color="arknightsPCStatusTag.color"
                                style="margin: 0; font-size: 12px;">
                                {{ arknightsPCStatusTag.text }}
                            </a-tag>
                        </span>
                    </template>
                    <TabArknightsPC v-if="editingConfig.ArknightsPC" :config="editingConfig.ArknightsPC"
                        :disabled="loading" :on-field-change="handleFieldChange"
                        :recording-key-field="recordingKeyField" :start-record-key="startRecordKey"
                        :stop-record-key="stopRecordKey" :on-select-visible-change="handleSelectVisibleChange" />
                </a-tab-pane>
            </a-tabs>
        </div>


    </div>
</template>

<style scoped>
/* 统一样式，使用 :deep 作用到子组件内部 */
.settings-container {
    /* Allow the settings page to expand with the window width */
    width: 100%;
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    /* Use full viewport min-height so the page can grow and scroll */
    display: flex;
    flex-direction: column;
    height: 100%;
}

.settings-header {
    margin-bottom: 16px;
    padding: 0 4px;
}

.page-title {
    margin: 0;
    font-size: 32px;
    font-weight: 700;
    color: var(--ant-color-text);
    background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.settings-content {
    background: var(--ant-color-bg-container);
    /* Rounded on all corners for a consistent card look */
    border-radius: 12px;
    width: 100%;
    flex: 1;
    /* allow inner scrolling and cooperate with flexbox
     min-height:0 prevents flex children from overflowing the container */
    min-height: 0;
    overflow: auto;
    display: flex;
    flex-direction: column;
}

.settings-tabs {
    margin: 0;
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 12px;
    /* ensure children with overflow:auto can scroll inside this flex item */
    min-height: 0;
}

.settings-tabs :deep(.ant-tabs-nav) {
    padding: 0;
    margin: 0;
}

.settings-tabs :deep(.ant-tabs-content-holder) {
    flex: 1;
    overflow: auto;
}

.settings-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab) {
    background: transparent;
    border: 1px solid var(--ant-color-border);
    border-radius: 8px 8px 0 0;
    margin-right: 8px;
}

.settings-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab-active) {
    background: var(--ant-color-bg-container);
    border-bottom-color: var(--ant-color-bg-container);
}

:deep(.tab-content) {
    padding: 24px;
    width: 100%;
}

:deep(.form-section) {
    margin-bottom: 32px;
}

:deep(.form-section:last-child) {
    margin-bottom: 0;
}

:deep(.section-header) {
    margin-bottom: 20px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--ant-color-border-secondary);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

:deep(.section-header h3) {
    margin: 0;
    font-size: 20px;
    font-weight: 700;
    color: var(--ant-color-text);
    display: flex;
    align-items: center;
    gap: 12px;
}

:deep(.section-header h3::before) {
    content: '';
    width: 4px;
    height: 24px;
    background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
    border-radius: 2px;
}

:deep(.section-description) {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--ant-color-text-secondary);
}

:deep(.form-item-vertical) {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
}

:deep(.form-label-wrapper) {
    display: flex;
    align-items: center;
    gap: 8px;
}

:deep(.form-label) {
    font-weight: 600;
    color: var(--ant-color-text);
    font-size: 14px;
}

:deep(.help-icon) {
    color: #8c8c8c;
    font-size: 14px;
}

/* Tab 标签中的状态标签样式 - 与脚本管理页统一 */
.settings-tabs :deep(.ant-tabs-tab) {
    .ant-tag {
        font-size: 11px;
        font-weight: 500;
        border-radius: 4px;
        margin: 0;
        border: 1px solid rgba(0, 0, 0, 0.15);
    }
}
</style>
