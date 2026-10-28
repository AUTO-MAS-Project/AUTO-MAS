<script setup lang="ts">
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { useI18n } from 'vue-i18n'
import { BookOutlined, BugOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { ref, watch } from 'vue'
import LogRuleCard from './LogRuleCard.vue'
import type { PushLogPattern, PushLogPatternType } from '../composables/usePushLogPatterns'

const { t } = useI18n()

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

const onNameChange = (name: string | undefined) => {
  local.value.name = name
  commit()
}

const onLogTypeChange = (logType: string) => {
  local.value.logType = logType
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
  { value: 'split', label: t('core.edit.stringSplitting') },
  { value: 'regex', label: t('core.edit.expression') },
  { value: 'multiline', label: t('core.edit.multiLineAggregation') },
]

const logTypeOptions = [
  { value: '普通', label: t('core.edit.normal'), color: 'primary' },
  { value: '失败', label: t('core.edit.failed'), color: 'error' },
]
</script>

<template>
  <LogRuleCard
    :name="local.name"
    :index="index"
    :enabled="local.enabled !== false"
    show-debug
    @update:name="onNameChange"
    @update:enabled="onEnabledChange"
    @remove="emit('remove')"
    @debug="emit('debug')"
  >
    <template #type>
      <a-select :value="local.type" class="rule-type-select" size="small" @change="onTypeChange">
        <a-select-option v-for="opt in typeOptions" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </a-select-option>
      </a-select>
    </template>

    <template #header-extra>
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
    </template>

    <template #debug-icon>
      <BugOutlined />
    </template>

    <!-- 字符串切割 -->
    <template v-if="local.type === 'split'">
      <a-row :gutter="16">
        <a-col :span="24">
          <a-form-item class="compact-form-item">
            <template #label>
              <a-tooltip :title="t('core.edit.requiredEmptyValueDisables2')">
                <span class="form-label">
                  {{ t('core.edit.keyword') }}
                  <QuestionCircleOutlined class="help-icon" />
                  <span class="doc-link" @click.stop="$emit('open-docs', 'split')">
                    <BookOutlined />
                    {{ t('core.edit.documentation') }}
                  </span>
                </span>
              </a-tooltip>
            </template>
            <a-input
              v-model:value="local.match"
              :placeholder="t('core.edit.exampleTaskDoneSuccess')"
              size="middle"
              @blur="commit"
            />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item class="compact-form-item">
            <template #label>
              <FieldLabelWithHint
                :text="t('core.edit.leadingKeyword')"
                :hint="t('core.edit.cutFromStartLine')"
                variant="form"
              />
            </template>
            <div class="inline-checkbox-row">
              <a-input
                v-model:value="local.head"
                :placeholder="t('core.edit.leaveEmptySkipLeading')"
                size="middle"
                @blur="commit"
              />
              <a-checkbox v-model:checked="local.headInclude" @change="commit">{{
                t('core.edit.include')
              }}</a-checkbox>
            </div>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item class="compact-form-item">
            <template #label>
              <FieldLabelWithHint
                :text="t('core.edit.trailingKeyword')"
                :hint="t('core.edit.cutFromKeywordEnd')"
                variant="form"
              />
            </template>
            <div class="inline-checkbox-row">
              <a-input
                v-model:value="local.tail"
                :placeholder="t('core.edit.leaveEmptySkipTrailing')"
                size="middle"
                @blur="commit"
              />
              <a-checkbox v-model:checked="local.tailInclude" @change="commit">{{
                t('core.edit.include')
              }}</a-checkbox>
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
              <a-tooltip :title="t('core.edit.requiredEmptyValueDisables4')">
                <span class="form-label">
                  {{ t('core.edit.matchPattern') }}
                  <QuestionCircleOutlined class="help-icon" />
                  <span class="doc-link" @click.stop="$emit('open-docs', 'regex')">
                    <BookOutlined />
                    {{ t('core.edit.documentation') }}
                  </span>
                </span>
              </a-tooltip>
            </template>
            <a-input
              v-model:value="local.match"
              :placeholder="t('core.edit.exampleTaskRun')"
              size="middle"
              @blur="commit"
            />
          </a-form-item>
        </a-col>
        <a-col :span="24">
          <a-form-item class="compact-form-item">
            <template #label>
              <a-tooltip :title="t('core.edit.expressionSyntaxHint')">
                <span class="form-label">
                  {{ t('core.edit.extractionPattern') }}
                  <QuestionCircleOutlined class="help-icon" />
                  <span class="doc-link" @click.stop="$emit('open-docs', 'expression')">
                    <BookOutlined />
                    {{ t('core.edit.documentation') }}
                  </span>
                </span>
              </a-tooltip>
            </template>
            <a-input
              v-model:value="local.extract"
              :placeholder="t('core.edit.exampleTaskRunS')"
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
              <FieldLabelWithHint
                :text="t('core.edit.startPattern')"
                :hint="t('core.edit.requiredEmptyValueDisables')"
                variant="form"
              />
            </template>
            <a-input
              v-model:value="local.start"
              :placeholder="t('core.edit.exampleFullRunStarted')"
              size="middle"
              @blur="commit"
            />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item class="compact-form-item">
            <template #label>
              <FieldLabelWithHint
                :text="t('core.edit.endPattern')"
                :hint="t('core.edit.lineMatchingThisPattern')"
                variant="form"
              />
            </template>
            <a-input
              v-model:value="local.end"
              :placeholder="t('core.edit.exampleTaskFinished')"
              size="middle"
              @blur="commit"
            />
          </a-form-item>
        </a-col>
        <a-col :span="20">
          <a-form-item class="compact-form-item">
            <template #label>
              <a-tooltip :title="t('core.edit.windowExtractionHint')">
                <span class="form-label">
                  {{ t('core.edit.extractionPattern') }}
                  <QuestionCircleOutlined class="help-icon" />
                  <span class="doc-link" @click.stop="$emit('open-docs', 'expression')">
                    <BookOutlined />
                    {{ t('core.edit.documentation') }}
                  </span>
                </span>
              </a-tooltip>
            </template>
            <a-input
              v-model:value="local.extract"
              :placeholder="t('core.edit.exampleStartSEnd')"
              size="middle"
              @blur="commit"
            />
          </a-form-item>
        </a-col>
        <a-col :span="4">
          <a-form-item class="compact-form-item">
            <template #label>
              <a-tooltip :title="t('core.edit.maximumLinesWindowBefore')">
                <span class="form-label">{{ t('core.edit.maximumLines') }}</span>
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

    <template #footer>
      <div class="rule-footer-content">
        <div class="footer-left">
          <span class="footer-type-tag">{{ getPatternTypeLabel(local.type) }}</span>
          <span class="footer-hint">{{ getPatternTypeHint(local.type) }}</span>
        </div>
        <div class="footer-right">
          <a-tag size="small" :color="local.logType === '失败' ? 'error' : 'processing'">
            {{ local.logType || t('core.edit.normal') }}
          </a-tag>
          <span class="footer-hint">{{ getLogTypeHint(local.logType) }}</span>
        </div>
      </div>
    </template>
  </LogRuleCard>
</template>

<style scoped>
.rule-type-select {
  width: 120px;
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

.rule-footer-content {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
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
