<script setup lang="ts">
import { QuestionCircleOutlined, WarningOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import type { ToolsConfig_ArknightsPC } from '@/api'

const { config, disabled, onFieldChange, recordingKeyField, startRecordKey, stopRecordKey, onSelectVisibleChange } = defineProps<{
    config: ToolsConfig_ArknightsPC
    disabled?: boolean
    onFieldChange?: (key: string, value: any) => void
    recordingKeyField?: string | null
    startRecordKey?: (fieldName: string) => void
    stopRecordKey?: () => void
    onSelectVisibleChange?: (visible: boolean) => void
}>()

// 处理字段变更
const handleChange = (key: string, value: any) => {
    if (onFieldChange) {
        onFieldChange(key, value)
    }
}

// 检查是否正在录制指定字段
const isRecording = (fieldName: string) => {
    return recordingKeyField === fieldName
}
</script>

<template>
    <div class="tab-content">
        <!-- 工具简介 -->
        <div class="tool-intro">
            <!-- 工具简介 -->
            <div class="detail-card intro-card">
                <div class="card-header">
                    <QuestionCircleOutlined />
                    <span>工具简介</span>
                </div>
                <div class="card-content">
                    <p class="intro-text">
                        尽管明日方舟已上线暂停时部署功能，但选中干员与跳帧操作仍未实现。本工具旨在提供极限操作支持，改善您的游戏体验。
                    </p>
                </div>
            </div>

            <div class="intro-divider"></div>

            <!-- 使用要求 -->
            <div class="detail-card requirement-card">
                <div class="card-header">
                    <WarningOutlined />
                    <span>使用要求</span>
                </div>
                <div class="card-content">
                    <div class="content-item">
                        <span class="item-dot"></span>
                        <span>游戏 UI 缩放设为 <strong>100%</strong></span>
                    </div>
                    <div class="content-item">
                        <span class="item-dot"></span>
                        <span>屏幕比例 <strong>16:9</strong> <span class="item-hint">（推荐 1280×720 / 1920×1080）</span></span>
                    </div>
                </div>
            </div>

            <div class="intro-divider"></div>

            <!-- 工具性能 -->
            <div class="detail-card performance-card">
                <div class="card-header">
                    <ThunderboltOutlined />
                    <span>工具性能</span>
                </div>
                <div class="card-content">
                    <div class="content-item">
                        <span class="item-dot"></span>
                        <span>操作精度：<strong>每帧 2 次有效操作</strong></span>
                    </div>
                </div>
            </div>
        </div>

        <div class="form-section">
            <div class="section-header">
                <h3>基础设置</h3>
            </div>
            <a-row :gutter="24">
                <a-col :span="12">
                    <div class="form-item-vertical">
                        <div class="form-label-wrapper">
                            <span class="form-label">明日方舟 PC 划火柴</span>
                            <a-tooltip title="是否启用明日方舟 PC 端划火柴工具">
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
            </a-row>
        </div>

        <div class="form-section">
            <div class="section-header">
                <h3>键位配置</h3>
            </div>
            <a-row :gutter="24">
                <a-col :span="12">
                    <div class="form-item-vertical">
                        <div class="form-label-wrapper">
                            <span class="form-label">划火柴功能暂停</span>
                            <a-tooltip title="暂停划火柴工具运行的键位">
                                <QuestionCircleOutlined class="help-icon" />
                            </a-tooltip>
                        </div>
                        <a-input :value="config.PauseKey"
                            :placeholder="isRecording('PauseKey') ? '请按下键位...' : '点击录制按钮修改'" size="large"
                            :disabled="disabled || !config.Enabled || isRecording('PauseKey')" readonly
                            style="cursor: not-allowed;">
                            <template #suffix>
                                <a-button v-if="!isRecording('PauseKey')" type="default" size="small"
                                    :disabled="disabled || !config.Enabled" @click="startRecordKey?.('PauseKey')">
                                    录制
                                </a-button>
                                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                                    取消
                                </a-button>
                            </template>
                        </a-input>
                    </div>
                </a-col>

                <a-col :span="12">
                    <div class="form-item-vertical">
                        <div class="form-label-wrapper">
                            <span class="form-label">选中已部署干员</span>
                            <a-tooltip title="游戏暂停时，鼠标悬浮于已部署干员上，按此键选中干员">
                                <QuestionCircleOutlined class="help-icon" />
                            </a-tooltip>
                        </div>
                        <a-input :value="config.SelectDeployedKey"
                            :placeholder="isRecording('SelectDeployedKey') ? '请按下键位...' : '点击录制按钮修改'" size="large"
                            :disabled="disabled || !config.Enabled || isRecording('SelectDeployedKey')" readonly
                            style="cursor: not-allowed;">
                            <template #suffix>
                                <a-button v-if="!isRecording('SelectDeployedKey')" type="default" size="small"
                                    :disabled="disabled || !config.Enabled"
                                    @click="startRecordKey?.('SelectDeployedKey')">
                                    录制
                                </a-button>
                                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                                    取消
                                </a-button>
                            </template>
                        </a-input>
                    </div>
                </a-col>

                <a-col :span="12">
                    <div class="form-item-vertical">
                        <div class="form-label-wrapper">
                            <span class="form-label">释放技能</span>
                            <a-tooltip title="游戏暂停时，鼠标悬浮于已部署干员上，按此键使释放干员技能">
                                <QuestionCircleOutlined class="help-icon" />
                            </a-tooltip>
                        </div>
                        <a-input :value="config.UseSkillKey"
                            :placeholder="isRecording('UseSkillKey') ? '请按下键位...' : '点击录制按钮修改'" size="large"
                            :disabled="disabled || !config.Enabled || isRecording('UseSkillKey')" readonly
                            style="cursor: not-allowed;">
                            <template #suffix>
                                <a-button v-if="!isRecording('UseSkillKey')" type="default" size="small"
                                    :disabled="disabled || !config.Enabled" @click="startRecordKey?.('UseSkillKey')">
                                    录制
                                </a-button>
                                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                                    取消
                                </a-button>
                            </template>
                        </a-input>
                    </div>
                </a-col>

                <a-col :span="12">
                    <div class="form-item-vertical">
                        <div class="form-label-wrapper">
                            <span class="form-label">撤退干员</span>
                            <a-tooltip title="游戏暂停时，鼠标悬浮于已部署干员上，按此键撤退干员">
                                <QuestionCircleOutlined class="help-icon" />
                            </a-tooltip>
                        </div>
                        <a-input :value="config.RetreatKey"
                            :placeholder="isRecording('RetreatKey') ? '请按下键位...' : '点击录制按钮修改'" size="large"
                            :disabled="disabled || !config.Enabled || isRecording('RetreatKey')" readonly
                            style="cursor: not-allowed;">
                            <template #suffix>
                                <a-button v-if="!isRecording('RetreatKey')" type="default" size="small"
                                    :disabled="disabled || !config.Enabled" @click="startRecordKey?.('RetreatKey')">
                                    录制
                                </a-button>
                                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                                    取消
                                </a-button>
                            </template>
                        </a-input>
                    </div>
                </a-col>

                <a-col :span="12">
                    <div class="form-item-vertical">
                        <div class="form-label-wrapper">
                            <span class="form-label">下一帧</span>
                            <a-tooltip title="让游戏向前进 1 帧">
                                <QuestionCircleOutlined class="help-icon" />
                            </a-tooltip>
                        </div>
                        <a-input :value="config.NextFrameKey"
                            :placeholder="isRecording('NextFrameKey') ? '请按下键位...' : '点击录制按钮修改'" size="large"
                            :disabled="disabled || !config.Enabled || isRecording('NextFrameKey')" readonly
                            style="cursor: not-allowed;">
                            <template #suffix>
                                <a-button v-if="!isRecording('NextFrameKey')" type="default" size="small"
                                    :disabled="disabled || !config.Enabled" @click="startRecordKey?.('NextFrameKey')">
                                    录制
                                </a-button>
                                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                                    取消
                                </a-button>
                            </template>
                        </a-input>
                    </div>
                </a-col>

                <a-col :span="12">
                    <div class="form-item-vertical">
                        <div class="form-label-wrapper">
                            <span class="form-label">自定义退出/暂停</span>
                            <a-tooltip title="自定义的退出/暂停键位，仅战斗中有效">
                                <QuestionCircleOutlined class="help-icon" />
                            </a-tooltip>
                        </div>
                        <a-input :value="config.AnotherQuitKey"
                            :placeholder="isRecording('AnotherQuitKey') ? '请按下键位...' : '点击录制按钮修改'" size="large"
                            :disabled="disabled || !config.Enabled || isRecording('AnotherQuitKey')" readonly
                            style="cursor: not-allowed;">
                            <template #suffix>
                                <a-button v-if="!isRecording('AnotherQuitKey')" type="default" size="small"
                                    :disabled="disabled || !config.Enabled" @click="startRecordKey?.('AnotherQuitKey')">
                                    录制
                                </a-button>
                                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                                    取消
                                </a-button>
                            </template>
                        </a-input>
                    </div>
                </a-col>
            </a-row>
        </div>
    </div>
</template>
<style scoped>
/* 工具简介 */
.tool-intro {
    background: var(--ant-color-bg-container);
    border: 1px solid var(--ant-color-border);
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 20px;
    display: flex;
    flex-direction: row;
    align-items: stretch;
    gap: 0;
    transition: all 0.3s ease;
}

.tool-intro:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.intro-divider {
    width: 1px;
    background: linear-gradient(to bottom, transparent, var(--ant-color-border), transparent);
    align-self: stretch;
    flex-shrink: 0;
}

.detail-card {
    flex: 1;
    padding: 0 20px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
}

/* 工具简介卡片 */
.intro-card {
    border-left: 3px solid var(--ant-color-info);
    background: linear-gradient(to right, var(--ant-color-info-bg), transparent);
    margin-left: -1px;
    border-radius: 6px 0 0 6px;
}

.intro-card .card-header {
    color: var(--ant-color-info-hover);
}

.intro-card .intro-text {
    margin: 0;
    font-size: 13px;
    line-height: 1.7;
    color: var(--ant-color-text-secondary);
}

/* 使用要求卡片 */
.requirement-card {
    border-left: 3px solid var(--ant-warning-color);
    background: linear-gradient(to right, var(--ant-warning-color-deprecated-bg), transparent);
    margin-left: -1px;
    border-radius: 6px 0 0 6px;
}

.requirement-card .card-header {
    color: var(--ant-warning-color-hover);
}

.requirement-card .item-dot {
    background: var(--ant-warning-color);
}

.requirement-card .content-item strong {
    color: var(--ant-warning-color-hover);
    background: rgba(250, 173, 20, 0.15);
}

/* 工具性能卡片 */
.performance-card {
    border-left: 3px solid var(--ant-primary-color);
    background: linear-gradient(to right, var(--ant-primary-color-deprecated-bg), transparent);
    margin-left: -1px;
    border-radius: 6px 0 0 6px;
}

.performance-card .card-header {
    color: var(--ant-primary-color-hover);
}

.performance-card .item-dot {
    background: var(--ant-primary-color);
}

.performance-card .content-item strong {
    color: var(--ant-primary-color-hover);
    background: rgba(24, 144, 255, 0.15);
}

.card-header {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 8px;
    font-size: 13px;
    font-weight: 600;
}

.card-header :deep(.anticon) {
    font-size: 14px;
}

.performance-icon {
    width: 14px;
    height: 14px;
}

.card-content {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.content-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    line-height: 1.6;
    color: var(--ant-color-text);
}

.item-dot {
    width: 4px;
    height: 4px;
    border-radius: 50%;
    flex-shrink: 0;
}

.content-item strong {
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 3px;
}

.item-hint {
    color: var(--ant-color-text-tertiary);
    font-size: 12px;
}

/* 响应式调整 */
@media (max-width: 1200px) {
    .tool-intro {
        flex-direction: column;
        gap: 12px;
    }

    .intro-divider {
        width: auto;
        height: 1px;
        background: linear-gradient(to right, transparent, var(--ant-color-border), transparent);
    }

    .detail-card {
        padding: 12px 16px;
        border-radius: 6px;
        margin-left: 0;
    }

    .intro-card {
        border-left: 3px solid var(--ant-color-info);
        background: linear-gradient(135deg, var(--ant-color-info-bg) 0%, rgba(230, 244, 255, 0.3) 100%);
    }

    .requirement-card {
        border-left: 3px solid var(--ant-warning-color);
        background: linear-gradient(135deg, var(--ant-warning-color-deprecated-bg) 0%, rgba(255, 251, 230, 0.3) 100%);
    }

    .performance-card {
        border-left: 3px solid var(--ant-primary-color);
        background: linear-gradient(135deg, var(--ant-primary-color-deprecated-bg) 0%, rgba(230, 244, 255, 0.3) 100%);
    }
}
</style>