<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { DownOutlined, PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { computed, ref } from 'vue'
import draggable from 'vuedraggable'

import LogHookRule from './LogHookRule.vue'
import {
  useLogHookRules,
  type LogHookRule as LogHookRuleItem,
  type LogHookType,
} from '../composables/useLogHookRules'

const { t } = useI18n()

const props = defineProps<{
  enabled: boolean
  rules: string
}>()

const emit = defineEmits<{
  'update:enabled': [value: boolean]
  'update:rules': [value: string]
  change: [group: string, key: string, value: unknown]
}>()

const {
  rules: hookRules,
  activeRuleCount,
  addRule,
  removeRule,
  updateRuleType,
  onRuleFieldChange,
  save,
} = useLogHookRules({
  rulesJson: computed(() => props.rules),
  masterEnabled: computed(() => props.enabled),
  onChange: json => {
    emit('update:rules', json)
    emit('change', 'Script', 'LogHookRules', json)
  },
})

// 标题栏支持点击折叠/展开，默认折叠；启用开关时自动展开
const collapsed = ref(true)
const toggleCollapsed = () => {
  collapsed.value = !collapsed.value
}

// 兼容父组件的 v-model:enabled 事件签名
const onEnabledChange = (value: boolean) => {
  emit('update:enabled', value)
  emit('change', 'Script', 'LogHookEnabled', value)
  // 启用时自动展开编辑区方便直接配置规则，停用时自动收起，保持折叠态与开关一致
  collapsed.value = !value
}

const addMenuItems = [
  { key: 'drop', label: t('edit.dropLine'), title: t('edit.dropWholeLineWhen') },
  { key: 'replace', label: t('edit.rewriteLine'), title: t('edit.rewriteLineMatchPattern') },
]

const onAddMenuClick = ({ key }: { key: string }) => {
  addRule(key as LogHookType)
}

const onRuleTypeChange = (idx: number, type: LogHookType) => {
  updateRuleType(idx, type)
}

const onRuleUpdate = (idx: number, value: LogHookRuleItem) => {
  hookRules.value[idx] = value
  onRuleFieldChange()
}

// 拖拽排序：规则按列表顺序执行，顺序本身是配置的一部分（结构性操作，不做缺必填字段提示）
const onDragEnd = () => {
  save({ warn: false })
}
</script>

<template>
  <div class="log-hook-config" :class="{ collapsed }">
    <div class="hook-config-header sub-section-header">
      <h3>
        <a-tooltip :title="collapsed ? t('edit.expandRulesArea') : t('edit.collapseRulesArea')">
          <span class="hook-config-title-text" @click="toggleCollapsed">
            {{ t('edit.logHooks') }}
            <DownOutlined class="hook-config-title-arrow" :class="{ collapsed }" />
          </span>
        </a-tooltip>
        <a-tooltip :title="t('edit.whenScriptLogPreprocessed')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
      </h3>
      <div class="hook-config-actions">
        <span v-if="collapsed && hookRules.length > 0" class="hook-config-summary">
          {{ t('edit.ruleCountSummary', { n: hookRules.length, m: activeRuleCount }) }}
        </span>
        <a-tooltip :title="t('edit.rulesApplyOnlyWhen')">
          <a-switch
            :checked="enabled"
            :checked-children="'启用'"
            :un-checked-children="'停用'"
            @change="onEnabledChange"
          />
        </a-tooltip>
      </div>
    </div>

    <div v-show="!collapsed" class="hook-config-body">
      <div v-if="!enabled" class="hook-config-disabled-tip">
        {{ t('edit.logHooksOffRules') }}
      </div>

      <draggable
        v-model="hookRules"
        item-key="_uid"
        handle=".drag-handle"
        :animation="200"
        ghost-class="hook-ghost"
        chosen-class="hook-chosen"
        drag-class="hook-drag"
        class="hook-rules-list"
        @end="onDragEnd"
      >
        <template #item="{ element, index }">
          <div class="hook-rule-item">
            <LogHookRule
              :model-value="element"
              :index="index"
              @update:model-value="value => onRuleUpdate(index, value)"
              @type-change="type => onRuleTypeChange(index, type)"
              @remove="removeRule(index)"
            />
          </div>
        </template>
      </draggable>

      <div class="hook-rules-footer">
        <a-dropdown :trigger="['click']">
          <a-button type="dashed" class="add-hook-btn">
            <PlusOutlined />
            {{ t('edit.addRule') }}
            <DownOutlined />
          </a-button>
          <template #overlay>
            <a-menu @click="onAddMenuClick">
              <a-menu-item v-for="item in addMenuItems" :key="item.key" :title="item.title">
                {{ item.label }}
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>

        <span class="hook-rules-count">
          {{ t('edit.ruleCountFooter', { n: hookRules.length, m: activeRuleCount }) }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-hook-config {
  width: 100%;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.hook-config-title-text {
  cursor: pointer;
  color: inherit;
  transition: color 0.2s ease;
}

.hook-config-title-text:hover {
  color: var(--ant-color-primary);
}

.hook-config-title-arrow {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  vertical-align: middle;
  transition: transform 0.2s ease;
}

.hook-config-title-arrow.collapsed {
  transform: rotate(-90deg);
}

/* 折叠时正文隐藏、底部 24px 留白随之消失，这里补回，避免与下一配置区贴太近 */
.log-hook-config.collapsed .hook-config-header {
  margin-bottom: 24px;
}

.hook-config-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.hook-config-summary {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.hook-config-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 24px;
}

.hook-config-disabled-tip {
  padding: 10px 14px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.hook-rules-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hook-rule-item {
  position: relative;
}

.hook-ghost {
  opacity: 0.5;
  background: var(--ant-color-primary-bg);
  border: 1px dashed var(--ant-color-primary);
  border-radius: 8px;
}

.hook-chosen {
  cursor: grabbing;
}

.hook-drag {
  opacity: 0.8;
}

.hook-rules-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.add-hook-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.hook-rules-count {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}
</style>
