<script setup lang="ts">
import {
  BugOutlined,
  DeleteOutlined,
  DragOutlined,
  EditOutlined,
  QuestionCircleOutlined,
  BookOutlined,
} from '@ant-design/icons-vue'
import { ref, watch, nextTick } from 'vue'
import type { PushLogPattern, PushLogPatternType } from '../composables/usePushLogPatterns'

const props = defineProps<{
  modelValue: PushLogPattern
  index: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: PushLogPattern]
  'type-change': [type: PushLogPatternType]
  remove: []
  debug: []
  'open-docs': [key: 'split' | 'regex' | 'expression' | 'multiline']
}>()

const local = ref<PushLogPattern>({ ...props.modelValue })

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

const onTypeChange = (type: PushLogPatternType) => {
  emit('type-change', type)
}

const onEnabledChange = (enabled: boolean) => {
  local.value.enabled = enabled
  commit()
}

const onLogTypeChange = (logType: string) => {
  local.value.logType = logType
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

const getLogTypeHint = (logType: string | undefined): string => {
  if (logType === '失败') {
    return '仅在本次任务存在未完成用户时纳入推送报告'
  }
  return '始终纳入推送报告'
}

const getPatternTypeHint = (type: PushLogPatternType): string => {
  if (type === 'split') {
    return '按关键字过滤行后，用头/尾关键字截取中间内容，多个关键字以「|」分隔任一命中'
  }
  if (type === 'regex') {
    return '先用匹配正则过滤日志行，再用表达式中 $() 提取字段并支持函数链'
  }
  return '用起始/结束正则划定多行窗口，达到最大行数强制关闭，再用表达式提取并拼接字段'
}

const getPatternTypeLabel = (type: PushLogPatternType): string => {
  if (type === 'split') return '字符串切割'
  if (type === 'regex') return '表达式'
  return '多行聚合'
}

const typeOptions = [
  { value: 'split', label: '字符串切割' },
  { value: 'regex', label: '表达式' },
  { value: 'multiline', label: '多行聚合' },
]

const logTypeOptions = [
  { value: '普通', label: '普通', color: 'primary' },
  { value: '失败', label: '失败', color: 'error' },
]
</script>

<template>
  <div :class="['log-pattern-rule', { 'rule-disabled': local.enabled === false }]">
    <!-- 规则头部：拖拽、类型、标题、开关、操作 -->
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
          placeholder="规则标题"
          @blur="finishEditName"
          @press-enter="finishEditName"
        />
      </div>

      <div class="rule-header-right">
        <a-radio-group
          :value="local.logType || '普通'"
          size="small"
          class="rule-log-type-group"
          @change="(e: any) => onLogTypeChange(e.target.value)"
        >
          <a-radio-button
            v-for="opt in logTypeOptions"
            :key="opt.value"
            :value="opt.value"
            :class="`is-${opt.color}`"
          >
            {{ opt.label }}
          </a-radio-button>
        </a-radio-group>

        <a-switch :checked="local.enabled !== false" size="small" @change="onEnabledChange" />

        <a-tooltip title="调试">
          <a-button size="small" class="rule-op-btn" @click="emit('debug')">
            <BugOutlined />
          </a-button>
        </a-tooltip>

        <a-tooltip title="删除">
          <a-button size="small" danger class="rule-op-btn" @click="emit('remove')">
            <DeleteOutlined />
          </a-button>
        </a-tooltip>
      </div>
    </div>

    <!-- 规则表单区 -->
    <div class="rule-body">
      <!-- 字符串切割 -->
      <template v-if="local.type === 'split'">
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item class="compact-form-item">
              <template #label>
                <a-tooltip
                  title="必填，留空则该规则不生效；多个关键字以「 | 」分隔，任一命中即通过"
                >
                  <span class="form-label">
                    匹配关键字
                    <QuestionCircleOutlined class="help-icon" />
                    <span class="doc-link" @click.stop="$emit('open-docs', 'split')">
                      <BookOutlined />
                      说明文档
                    </span>
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="local.match"
                placeholder="例如：任务完成|成功|失败"
                size="middle"
                @blur="commit"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item class="compact-form-item">
              <template #label>
                <a-tooltip
                  title="从行首截取到关键字处；勾选「包含」则连同关键字一起去除，不勾选则保留关键字"
                >
                  <span class="form-label">
                    掐头关键字
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <div class="inline-checkbox-row">
                <a-input
                  v-model:value="local.head"
                  placeholder="留空不掐头"
                  size="middle"
                  @blur="commit"
                />
                <a-checkbox v-model:checked="local.headInclude" @change="commit"> 包含 </a-checkbox>
              </div>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item class="compact-form-item">
              <template #label>
                <a-tooltip
                  title="从关键字处截取到行尾；勾选「包含」则连同关键字一起去除，不勾选则保留关键字"
                >
                  <span class="form-label">
                    去尾关键字
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <div class="inline-checkbox-row">
                <a-input
                  v-model:value="local.tail"
                  placeholder="留空不去尾"
                  size="middle"
                  @blur="commit"
                />
                <a-checkbox v-model:checked="local.tailInclude" @change="commit"> 包含 </a-checkbox>
              </div>
            </a-form-item>
          </a-col>
        </a-row>
      </template>

      <!-- 正则 -->
      <template v-else-if="local.type === 'regex'">
        <a-row :gutter="16">
          <a-col :span="24">
            <a-form-item class="compact-form-item">
              <template #label>
                <a-tooltip title="必填，留空则该规则不生效；用于过滤行的正则表达式">
                  <span class="form-label">
                    匹配正则
                    <QuestionCircleOutlined class="help-icon" />
                    <span class="doc-link" @click.stop="$emit('open-docs', 'regex')">
                      <BookOutlined />
                      说明文档
                    </span>
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="local.match"
                placeholder="例如：任务执行"
                size="middle"
                @blur="commit"
              />
            </a-form-item>
          </a-col>
          <a-col :span="24">
            <a-form-item class="compact-form-item">
              <template #label>
                <a-tooltip
                  title='使用 $() 包裹正则提取内容，支持 +（同行拼接）、;（换行拼接）、""（字面量）和函数链；留空则返回整行'
                >
                  <span class="form-label">
                    提取表达式
                    <QuestionCircleOutlined class="help-icon" />
                    <span class="doc-link" @click.stop="$emit('open-docs', 'expression')">
                      <BookOutlined />
                      说明文档
                    </span>
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="local.extract"
                placeholder="例如：$(任务执行: (\S+))"
                size="middle"
                @blur="commit"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </template>

      <!-- 多行聚合 -->
      <template v-else>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item class="compact-form-item">
              <template #label>
                <a-tooltip title="必填，留空则该规则不生效；匹配到此正则的行作为窗口起始（含该行）">
                  <span class="form-label">
                    起始正则
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="local.start"
                placeholder="例如：一条龙任务执行"
                size="middle"
                @blur="commit"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item class="compact-form-item">
              <template #label>
                <a-tooltip title="匹配到此正则的行作为窗口结束（含该行）；留空则不限定结束">
                  <span class="form-label">
                    结束正则
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="local.end"
                placeholder="例如：任务结束"
                size="middle"
                @blur="commit"
              />
            </a-form-item>
          </a-col>
          <a-col :span="20">
            <a-form-item class="compact-form-item">
              <template #label>
                <a-tooltip
                  title='使用 $() 语法从窗口内容中提取字段；留空返回窗口原文。详见"表达式"说明文档'
                >
                  <span class="form-label">
                    提取表达式
                    <QuestionCircleOutlined class="help-icon" />
                    <span class="doc-link" @click.stop="$emit('open-docs', 'expression')">
                      <BookOutlined />
                      说明文档
                    </span>
                  </span>
                </a-tooltip>
              </template>
              <a-input
                v-model:value="local.extract"
                placeholder="例如：$(开始时间: (\S+));$(结束时间: (\S+))"
                size="middle"
                @blur="commit"
              />
            </a-form-item>
          </a-col>
          <a-col :span="4">
            <a-form-item class="compact-form-item">
              <template #label>
                <a-tooltip title="窗口最大跨行数，达到后强制关闭">
                  <span class="form-label">最大行数</span>
                </a-tooltip>
              </template>
              <a-input-number
                v-model:value="local.maxLines"
                :min="2"
                :step="1"
                size="middle"
                style="width: 100%"
                @blur="commit"
                @change="commit"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </template>
    </div>

    <!-- 规则底部提示：一行：模式类型在左，日志类型（普通/失败）在右 -->
    <div class="rule-footer">
      <div class="footer-left">
        <span class="footer-type-tag">{{ getPatternTypeLabel(local.type) }}</span>
        <span class="footer-hint">{{ getPatternTypeHint(local.type) }}</span>
      </div>
      <div class="footer-right">
        <a-tag size="small" :color="local.logType === '失败' ? 'error' : 'processing'">
          {{ local.logType || '普通' }}
        </a-tag>
        <span class="footer-hint">{{ getLogTypeHint(local.logType) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-pattern-rule {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 16px;
  transition: opacity 0.2s;
}

.log-pattern-rule.rule-disabled {
  opacity: 0.55;
}

.log-pattern-rule.rule-disabled:hover {
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
  width: 120px;
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
  border-bottom: 1px dashed transparent;
  transition: border-color 0.2s;
}

.rule-title:hover {
  border-bottom-color: var(--ant-color-text-quaternary);
}

.rule-title-input {
  max-width: 280px;
  text-align: center;
}

.rule-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.rule-log-type-group :deep(.ant-radio-button-wrapper) {
  padding: 0 8px;
  font-size: 12px;
}

.rule-log-type-group :deep(.ant-radio-button-wrapper-checked.is-primary) {
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.rule-log-type-group :deep(.ant-radio-button-wrapper-checked.is-error) {
  color: var(--ant-color-error);
  background: var(--ant-color-error-bg);
}

.rule-op-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px;
}

.rule-body {
  padding-top: 4px;
}

.compact-form-item {
  margin-bottom: 16px;
}

.compact-form-item :deep(.ant-form-item-label > label) {
  font-size: 13px;
}

.inline-checkbox-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.inline-checkbox-row .ant-input {
  flex: 1;
  min-width: 0;
}

.inline-checkbox-row .ant-checkbox-wrapper {
  flex-shrink: 0;
  white-space: nowrap;
}

.rule-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px dashed var(--ant-color-border-secondary);
}

.footer-left,
.footer-right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  line-height: 1.6;
}

.footer-right {
  justify-content: flex-end;
}

.footer-type-tag {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  font-size: 12px;
  line-height: 20px;
  border: 1px solid var(--ant-color-border);
  border-radius: 4px;
  color: var(--ant-color-text-secondary);
  background: transparent;
  white-space: nowrap;
}

.footer-hint {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.doc-link {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: 8px;
  color: var(--ant-color-primary);
  font-size: 12px;
  cursor: pointer;
}

.doc-link:hover {
  text-decoration: underline;
}
</style>
