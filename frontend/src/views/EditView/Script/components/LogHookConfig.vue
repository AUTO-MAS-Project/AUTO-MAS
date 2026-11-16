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
  { key: 'drop', label: t('core.edit.dropLine'), title: t('core.edit.dropWholeLineWhen') },
  {
    key: 'replace',
    label: t('core.edit.rewriteLine'),
    title: t('core.edit.rewriteLineMatchPattern'),
  },
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
  <div class="log-rule-config" :class="{ collapsed }">
    <div class="log-rule-config-header sub-section-header">
      <h3>
        <a-tooltip
          :title="collapsed ? t('core.edit.expandRulesArea') : t('core.edit.collapseRulesArea')"
        >
          <span class="log-rule-config-title" @click="toggleCollapsed">
            {{ t('core.edit.logHooks') }}
            <DownOutlined class="log-rule-config-title-arrow" :class="{ collapsed }" />
          </span>
        </a-tooltip>
        <a-tooltip :title="t('core.edit.whenScriptLogPreprocessed')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
      </h3>
      <div class="log-rule-config-actions">
        <span v-if="collapsed && hookRules.length > 0" class="hook-config-summary">
          {{ t('core.edit.ruleCountSummary', { n: hookRules.length, m: activeRuleCount }) }}
        </span>
        <a-tooltip :title="t('core.edit.rulesApplyOnlyWhen')">
          <a-switch
            :checked="enabled"
            :checked-children="'启用'"
            :un-checked-children="'停用'"
            @change="onEnabledChange"
          />
        </a-tooltip>
      </div>
    </div>

    <div v-show="!collapsed" class="log-rule-config-body">
      <div v-if="!enabled" class="log-rule-config-disabled-tip">
        {{ t('core.edit.logHooksOffRules') }}
      </div>

      <draggable
        v-model="hookRules"
        item-key="_uid"
        handle=".drag-handle"
        :animation="200"
        ghost-class="log-rule-ghost"
        chosen-class="log-rule-chosen"
        drag-class="log-rule-drag"
        class="log-rule-list"
        @end="onDragEnd"
      >
        <template #item="{ element, index }">
          <div class="log-rule-item">
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

      <div class="log-rule-footer">
        <a-dropdown :trigger="['click']">
          <a-button type="dashed" class="add-log-rule-btn">
            <PlusOutlined />
            {{ t('core.edit.addRule') }}
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

        <span class="log-rule-count">
          {{ t('core.edit.ruleCountFooter', { n: hookRules.length, m: activeRuleCount }) }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped src="./logRuleConfig.css"></style>

<style scoped>
.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.hook-config-summary {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}
</style>
