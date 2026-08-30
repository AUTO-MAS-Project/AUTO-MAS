<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  DeleteOutlined,
  DragOutlined,
  EditOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { computed, nextTick, ref, watch } from 'vue'

import { validateRegexPattern } from '../logRegex'
import type { LogHookRule, LogHookType } from '../composables/useLogHookRules'

const { t } = useI18n()

const props = defineProps<{
  modelValue: LogHookRule
  index: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: LogHookRule]
  'type-change': [type: LogHookType]
  remove: []
}>()

const local = ref<LogHookRule>({ ...props.modelValue })

watch(
  () => props.modelValue,
  val => {
    local.value = { ...val }
  },
  { deep: true }
)

const commit = () => {
  emit('update:modelValue', { ...local.value })
}

const onTypeChange = (type: LogHookType) => {
  emit('type-change', type)
}

const onEnabledChange = (enabled: boolean) => {
  local.value.enabled = enabled
  commit()
}

const editingName = ref(false)
const nameInputRef = ref<HTMLInputElement | null>(null)
const nameValue = ref('')

const startEditName = () => {
  nameValue.value = local.value.name || ''
  editingName.value = true
  nextTick(() => nameInputRef.value?.focus())
}

const finishEditName = () => {
  const trimmed = nameValue.value.trim()
  local.value.name = trimmed || undefined
  editingName.value = false
  commit()
}

// 正则语法提示：后端仍是唯一判据，非法正则在运行时只是被跳过
const matchError = computed(() => {
  const error = validateRegexPattern(local.value.match || '')
  return error ? `正则语法错误：${error}` : null
})

const getTypeHint = (type: LogHookType): string =>
  type === 'drop'
    ? '命中即丢弃该行，用于过滤心跳、进度刷屏等噪声日志'
    : '按匹配正则替换命中内容后继续交给后续规则，用于脱敏与格式归一化'

const typeOptions = [
  { value: 'drop', label: '丢弃' },
  { value: 'replace', label: '改写' },
]
</script>

<template>
  <div :class="['log-hook-rule', { 'rule-disabled': local.enabled === false }]">
    <!-- 规则头部：拖拽、类型、标题、开关、删除 -->
    <div class="rule-header">
      <div class="rule-header-left">
        <span class="drag-handle">
          <DragOutlined />
        </span>
        <a-select :value="local.type" class="rule-type-select" size="small" @change="onTypeChange">
          <a-select-option v-for="opt in typeOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </a-select-option>
        </a-select>
      </div>

      <div class="rule-title-wrap" @click="startEditName">
        <EditOutlined v-if="!editingName" class="rule-title-icon" />
        <span v-if="!editingName" class="rule-title">
          {{ local.name?.trim() || `规则${index + 1}` }}
        </span>
        <a-input
          v-else
          ref="nameInputRef"
          v-model:value="nameValue"
          class="rule-title-input"
          size="small"
          :placeholder="t('edit.ruleTitle')"
          @blur="finishEditName"
          @press-enter="finishEditName"
        />
      </div>

      <div class="rule-header-right">
        <a-switch :checked="local.enabled !== false" size="small" @change="onEnabledChange" />

        <a-tooltip :title="t('edit.delete')">
          <a-button size="small" danger class="rule-op-btn" @click="emit('remove')">
            <DeleteOutlined />
          </a-button>
        </a-tooltip>
      </div>
    </div>

    <!-- 规则表单区 -->
    <div class="rule-body">
      <a-row :gutter="16">
        <a-col :span="local.type === 'replace' ? 12 : 24">
          <a-form-item
            class="compact-form-item"
            :validate-status="matchError ? 'error' : undefined"
            :help="matchError || undefined"
          >
            <template #label>
              <a-tooltip :title="t('edit.requiredEmptyValueDisables3')">
                <span class="form-label">
                  {{ t('edit.matchPattern') }}
                  <QuestionCircleOutlined class="help-icon" />
                </span>
              </a-tooltip>
            </template>
            <a-input
              v-model:value="local.match"
              :placeholder="t('edit.exampleHeartbeatCurrentProgress')"
              size="middle"
              @blur="commit"
            />
          </a-form-item>
        </a-col>
        <a-col v-if="local.type === 'replace'" :span="12">
          <a-form-item class="compact-form-item">
            <template #label>
              <a-tooltip :title="t('edit.replacementTextMatchBack')">
                <span class="form-label">
                  {{ t('edit.replace') }}
                  <QuestionCircleOutlined class="help-icon" />
                </span>
              </a-tooltip>
            </template>
            <a-input
              v-model:value="local.replace"
              :placeholder="t('edit.exampleToken')"
              size="middle"
              @blur="commit"
            />
          </a-form-item>
        </a-col>
      </a-row>
    </div>

    <!-- 规则底部提示 -->
    <div class="rule-footer">
      <span class="footer-type-tag">{{ local.type === 'drop' ? '丢弃' : '改写' }}</span>
      <span class="footer-hint">{{ getTypeHint(local.type) }}</span>
    </div>
  </div>
</template>

<style scoped>
.log-hook-rule {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 16px;
  transition: opacity 0.2s;
}

.log-hook-rule.rule-disabled {
  opacity: 0.55;
}

.log-hook-rule.rule-disabled:hover {
  opacity: 0.85;
}

.rule-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.rule-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--ant-color-text-tertiary);
  cursor: grab;
  border-radius: 4px;
}

.drag-handle:hover {
  color: var(--ant-color-text);
  background: var(--ant-color-fill-quaternary);
}

.drag-handle:active {
  cursor: grabbing;
}

.rule-type-select {
  width: 96px;
}

.rule-title-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: text;
  padding: 0 8px;
}

.rule-title-icon {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.rule-title {
  font-size: 14px;
  color: var(--ant-color-text);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 2px 6px;
}

.rule-title-input {
  max-width: 220px;
}

.rule-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.rule-op-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.rule-body :deep(.compact-form-item) {
  margin-bottom: 0;
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.rule-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--ant-color-border-secondary);
}

.footer-type-tag {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-quaternary);
  border-radius: 4px;
  padding: 1px 6px;
}

.footer-hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>
