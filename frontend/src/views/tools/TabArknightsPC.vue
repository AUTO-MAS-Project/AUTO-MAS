<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined, WarningOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import type { ToolsConfig_ArknightsPC } from '@/api'

const { t } = useI18n()

type ArknightsPCFieldKey = keyof ToolsConfig_ArknightsPC
type ArknightsPCKeyField = Exclude<ArknightsPCFieldKey, 'Enabled' | 'Status'>

const { config, disabled, onFieldChange, recordingKeyField, startRecordKey, stopRecordKey } =
  defineProps<{
    config: ToolsConfig_ArknightsPC
    disabled?: boolean
    onFieldChange: <K extends ArknightsPCFieldKey>(
      key: K,
      value: ToolsConfig_ArknightsPC[K]
    ) => void
    recordingKeyField: ArknightsPCKeyField | null
    startRecordKey: (fieldName: ArknightsPCKeyField) => void
    stopRecordKey: () => void
  }>()

// 处理字段变更
const handleChange = <K extends ArknightsPCFieldKey>(key: K, value: ToolsConfig_ArknightsPC[K]) => {
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
          <span>{{ t('tools.ark.introTitle') }}</span>
        </div>
        <div class="card-content">
          <p class="intro-text">
            {{ t('tools.ark.introText') }}
          </p>
        </div>
      </div>

      <div class="intro-divider"></div>

      <!-- 使用要求 -->
      <div class="detail-card requirement-card">
        <div class="card-header">
          <WarningOutlined />
          <span>{{ t('tools.ark.requirementTitle') }}</span>
        </div>
        <div class="card-content">
          <div class="content-item">
            <span class="item-dot"></span>
            <span>{{ t('tools.ark.reqScale') }} <strong>100%</strong></span>
          </div>
          <div class="content-item">
            <span class="item-dot"></span>
            <span
              >{{ t('tools.ark.reqRatio') }} <strong>16:9</strong>
              <span class="item-hint">{{ t('tools.ark.reqRatioHint') }}</span></span
            >
          </div>
        </div>
      </div>

      <div class="intro-divider"></div>

      <!-- 工具性能 -->
      <div class="detail-card performance-card">
        <div class="card-header">
          <ThunderboltOutlined />
          <span>{{ t('tools.ark.performanceTitle') }}</span>
        </div>
        <div class="card-content">
          <div class="content-item">
            <span class="item-dot"></span>
            <span
              >{{ t('tools.ark.perfLabel') }} <strong>{{ t('tools.ark.perfValue') }}</strong></span
            >
          </div>
        </div>
      </div>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('tools.ark.basicSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('tools.ark.enable') }}</span>
              <a-tooltip :title="t('tools.ark.enableTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-switch
              :checked="config.Enabled"
              :disabled="disabled"
              @change="handleChange('Enabled', $event)"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('tools.ark.keySection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('tools.ark.pause') }}</span>
              <a-tooltip :title="t('tools.ark.pauseTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="config.PauseKey"
              :placeholder="
                isRecording('PauseKey') ? t('tools.ark.pressKey') : t('tools.ark.clickRecord')
              "
              size="large"
              :disabled="disabled || !config.Enabled || isRecording('PauseKey')"
              readonly
              style="cursor: not-allowed"
            >
              <template #suffix>
                <a-button
                  v-if="!isRecording('PauseKey')"
                  type="default"
                  size="small"
                  :disabled="disabled || !config.Enabled"
                  @click="startRecordKey?.('PauseKey')"
                >
                  {{ t('tools.ark.record') }}
                </a-button>
                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                  {{ t('common.cancel') }}
                </a-button>
              </template>
            </a-input>
          </div>
        </a-col>

        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('tools.ark.selectDeployed') }}</span>
              <a-tooltip :title="t('tools.ark.selectDeployedTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="config.SelectDeployedKey"
              :placeholder="
                isRecording('SelectDeployedKey')
                  ? t('tools.ark.pressKey')
                  : t('tools.ark.clickRecord')
              "
              size="large"
              :disabled="disabled || !config.Enabled || isRecording('SelectDeployedKey')"
              readonly
              style="cursor: not-allowed"
            >
              <template #suffix>
                <a-button
                  v-if="!isRecording('SelectDeployedKey')"
                  type="default"
                  size="small"
                  :disabled="disabled || !config.Enabled"
                  @click="startRecordKey?.('SelectDeployedKey')"
                >
                  {{ t('tools.ark.record') }}
                </a-button>
                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                  {{ t('common.cancel') }}
                </a-button>
              </template>
            </a-input>
          </div>
        </a-col>

        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('tools.ark.useSkill') }}</span>
              <a-tooltip :title="t('tools.ark.useSkillTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="config.UseSkillKey"
              :placeholder="
                isRecording('UseSkillKey') ? t('tools.ark.pressKey') : t('tools.ark.clickRecord')
              "
              size="large"
              :disabled="disabled || !config.Enabled || isRecording('UseSkillKey')"
              readonly
              style="cursor: not-allowed"
            >
              <template #suffix>
                <a-button
                  v-if="!isRecording('UseSkillKey')"
                  type="default"
                  size="small"
                  :disabled="disabled || !config.Enabled"
                  @click="startRecordKey?.('UseSkillKey')"
                >
                  {{ t('tools.ark.record') }}
                </a-button>
                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                  {{ t('common.cancel') }}
                </a-button>
              </template>
            </a-input>
          </div>
        </a-col>

        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('tools.ark.retreat') }}</span>
              <a-tooltip :title="t('tools.ark.retreatTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="config.RetreatKey"
              :placeholder="
                isRecording('RetreatKey') ? t('tools.ark.pressKey') : t('tools.ark.clickRecord')
              "
              size="large"
              :disabled="disabled || !config.Enabled || isRecording('RetreatKey')"
              readonly
              style="cursor: not-allowed"
            >
              <template #suffix>
                <a-button
                  v-if="!isRecording('RetreatKey')"
                  type="default"
                  size="small"
                  :disabled="disabled || !config.Enabled"
                  @click="startRecordKey?.('RetreatKey')"
                >
                  {{ t('tools.ark.record') }}
                </a-button>
                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                  {{ t('common.cancel') }}
                </a-button>
              </template>
            </a-input>
          </div>
        </a-col>

        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('tools.ark.nextFrame') }}</span>
              <a-tooltip :title="t('tools.ark.nextFrameTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="config.NextFrameKey"
              :placeholder="
                isRecording('NextFrameKey') ? t('tools.ark.pressKey') : t('tools.ark.clickRecord')
              "
              size="large"
              :disabled="disabled || !config.Enabled || isRecording('NextFrameKey')"
              readonly
              style="cursor: not-allowed"
            >
              <template #suffix>
                <a-button
                  v-if="!isRecording('NextFrameKey')"
                  type="default"
                  size="small"
                  :disabled="disabled || !config.Enabled"
                  @click="startRecordKey?.('NextFrameKey')"
                >
                  {{ t('tools.ark.record') }}
                </a-button>
                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                  {{ t('common.cancel') }}
                </a-button>
              </template>
            </a-input>
          </div>
        </a-col>

        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('tools.ark.anotherQuit') }}</span>
              <a-tooltip :title="t('tools.ark.anotherQuitTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input
              :value="config.AnotherQuitKey"
              :placeholder="
                isRecording('AnotherQuitKey') ? t('tools.ark.pressKey') : t('tools.ark.clickRecord')
              "
              size="large"
              :disabled="disabled || !config.Enabled || isRecording('AnotherQuitKey')"
              readonly
              style="cursor: not-allowed"
            >
              <template #suffix>
                <a-button
                  v-if="!isRecording('AnotherQuitKey')"
                  type="default"
                  size="small"
                  :disabled="disabled || !config.Enabled"
                  @click="startRecordKey?.('AnotherQuitKey')"
                >
                  {{ t('tools.ark.record') }}
                </a-button>
                <a-button v-else type="primary" danger size="small" @click="stopRecordKey?.()">
                  {{ t('common.cancel') }}
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
  border-left: 3px solid var(--ant-color-warning);
  background: linear-gradient(to right, var(--ant-color-warning-bg), transparent);
  margin-left: -1px;
  border-radius: 6px 0 0 6px;
}

.requirement-card .card-header {
  color: var(--ant-color-warning);
}

.requirement-card .item-dot {
  background: var(--ant-color-warning);
}

.requirement-card .content-item strong {
  color: var(--ant-color-warning);
  background: rgba(250, 173, 20, 0.15);
}

/* 工具性能卡片 */
.performance-card {
  border-left: 3px solid var(--ant-color-primary);
  background: linear-gradient(to right, var(--ant-color-primary-bg), transparent);
  margin-left: -1px;
  border-radius: 6px 0 0 6px;
}

.performance-card .card-header {
  color: var(--ant-color-primary-hover);
}

.performance-card .item-dot {
  background: var(--ant-color-primary);
}

.performance-card .content-item strong {
  color: var(--ant-color-primary-hover);
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
    border-left: 3px solid var(--ant-color-warning);
    background: linear-gradient(
      135deg,
      var(--ant-color-warning-bg) 0%,
      rgba(255, 251, 230, 0.3) 100%
    );
  }

  .performance-card {
    border-left: 3px solid var(--ant-color-primary);
    background: linear-gradient(
      135deg,
      var(--ant-color-primary-bg) 0%,
      rgba(230, 244, 255, 0.3) 100%
    );
  }
}
</style>
