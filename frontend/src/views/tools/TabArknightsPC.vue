<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
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
        <div class="form-section">
            <div class="section-header">
                <h3>基础设置</h3>
            </div>
            <a-row :gutter="24">
                <a-col :span="24">
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
                            <span class="form-label">暂停键位</span>
                            <a-tooltip title="游戏内暂停的键位">
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
                            <span class="form-label">选中已部署干员键位</span>
                            <a-tooltip title="选中已部署干员的键位">
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
                            <span class="form-label">释放技能键位</span>
                            <a-tooltip title="释放干员技能的键位">
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
                            <span class="form-label">撤退键位</span>
                            <a-tooltip title="撤退干员的键位">
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
                            <span class="form-label">下一帧键位</span>
                            <a-tooltip title="逐帧播放的键位">
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
                            <span class="form-label">自定义退出/暂停键位</span>
                            <a-tooltip title="另外的退出或暂停键位">
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
