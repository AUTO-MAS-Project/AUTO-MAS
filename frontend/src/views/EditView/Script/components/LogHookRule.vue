<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { computed, ref, watch } from 'vue'

import { validateRegexPattern } from '../logRegex'
import LogRuleCard from './LogRuleCard.vue'
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

const onNameChange = (name: string | undefined) => {
  local.value.name = name
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
  { value: 'drop', label: t('edit.drop') },
  { value: 'replace', label: t('edit.rewrite') },
]
</script>

<template>
  <LogRuleCard
    :name="local.name"
    :index="index"
    :enabled="local.enabled !== false"
    @update:name="onNameChange"
    @update:enabled="onEnabledChange"
    @remove="emit('remove')"
  >
    <template #type>
      <a-select :value="local.type" class="rule-type-select" size="small" @change="onTypeChange">
        <a-select-option v-for="opt in typeOptions" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </a-select-option>
      </a-select>
    </template>

    <div class="hook-rule-form">
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

    <template #footer>
      <div class="hook-rule-footer">
        <span class="footer-type-tag">{{
          local.type === 'drop' ? t('edit.drop') : t('edit.rewrite')
        }}</span>
        <span class="footer-hint">{{ getTypeHint(local.type) }}</span>
      </div>
    </template>
  </LogRuleCard>
</template>

<style scoped>
.rule-type-select {
  width: 96px;
}

.hook-rule-form :deep(.compact-form-item) {
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

.hook-rule-footer {
  display: flex;
  align-items: center;
  gap: 8px;
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
