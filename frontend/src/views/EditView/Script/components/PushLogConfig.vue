<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  BookOutlined,
  DownOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { computed, ref } from 'vue'
import draggable from 'vuedraggable'
import LogPatternRule from './LogPatternRule.vue'
import LogPatternDebugModal from './LogPatternDebugModal.vue'
import LogPatternDocsModal from '../LogPatternDocsModal.vue'
import {
  usePushLogPatterns,
  type PushLogPattern,
  type PushLogPatternType,
} from '../composables/usePushLogPatterns'

const { t } = useI18n()

const props = defineProps<{
  enabled: boolean
  patterns: string
  logPath?: string | null
}>()

const emit = defineEmits<{
  'update:enabled': [value: boolean]
  'update:patterns': [value: string]
  change: [group: string, key: string, value: unknown]
}>()

const {
  patterns,
  activePatternCount,
  addPattern,
  removePattern,
  updatePatternType,
  onPatternFieldChange,
  save,
} = usePushLogPatterns({
  patternsJson: computed(() => props.patterns),
  onChange: json => {
    emit('update:patterns', json)
    emit('change', 'Script', 'PushLogPatterns', json)
  },
})

// 兼容父组件的 v-model:enabled 事件签名
const onEnabledChange = (value: boolean) => {
  emit('update:enabled', value)
  emit('change', 'Script', 'PushLogEnabled', value)
}

const addMenuItems = [
  { key: 'split', label: t('edit.stringSplitting'), title: t('edit.filterLinesByKeyword') },
  { key: 'regex', label: t('edit.expression'), title: t('edit.matchLineRegexThen') },
  {
    key: 'multiline',
    label: t('edit.multiLineAggregation'),
    title: t('edit.extractFieldsFromWindow'),
  },
]

const onAddMenuClick = ({ key }: { key: string }) => {
  addPattern(key as PushLogPatternType)
}

const onRuleTypeChange = (idx: number, type: PushLogPatternType) => {
  updatePatternType(idx, type)
}

const onRuleUpdate = (idx: number, value: PushLogPattern) => {
  patterns.value[idx] = value
  onPatternFieldChange()
}

// 拖拽排序（结构性操作，不做缺必填字段提示）
const onDragEnd = () => {
  save({ warn: false })
}

// 调试弹窗
const activePatternForDebug = ref<PushLogPattern | null>(null)
const debugModalOpen = ref(false)

const openDebug = (idx: number) => {
  const pattern = patterns.value[idx]
  if (!pattern) return
  activePatternForDebug.value = pattern
  debugModalOpen.value = true
}

// 文档弹窗
const docsOpen = ref(false)
const docsActiveKey = ref<'split' | 'regex' | 'expression' | 'multiline'>('regex')

const openDocs = (key: 'split' | 'regex' | 'expression' | 'multiline') => {
  docsActiveKey.value = key
  docsOpen.value = true
}

// 标题栏支持点击折叠/展开，默认展开；鼠标悬停标题时提示
const collapsed = ref(false)
const toggleCollapsed = () => {
  collapsed.value = !collapsed.value
}
</script>

<template>
  <div class="log-rule-config" :class="{ collapsed }">
    <div class="log-rule-config-header push-config-header">
      <h3>
        <a-tooltip :title="collapsed ? t('edit.expandRulesArea') : t('edit.collapseRulesArea')">
          <span class="log-rule-config-title" @click="toggleCollapsed">
            {{ t('edit.pushSettings') }}
            <DownOutlined class="log-rule-config-title-arrow" :class="{ collapsed }" />
          </span>
        </a-tooltip>
        <a-tooltip :title="t('edit.whenTaskProgressCollected')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
      </h3>
      <div class="log-rule-config-actions">
        <a-tooltip :title="t('edit.progressCollectedOnlyWhen')">
          <a-switch
            :checked="enabled"
            :checked-children="'启用'"
            :un-checked-children="'停用'"
            @change="onEnabledChange"
          />
        </a-tooltip>
        <a-tooltip :title="t('edit.readExtractionPatternReference')">
          <a-button size="small" class="docs-btn" @click="openDocs('regex')">
            <BookOutlined />
            {{ t('edit.documentation') }}
          </a-button>
        </a-tooltip>
      </div>
    </div>

    <div v-show="!collapsed" class="log-rule-config-body">
      <div v-if="!enabled" class="log-rule-config-disabled-tip">
        {{ t('edit.pushCollectionOffRules') }}
      </div>

      <draggable
        v-model="patterns"
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
            <LogPatternRule
              :model-value="element"
              :index="index"
              @update:model-value="value => onRuleUpdate(index, value)"
              @type-change="type => onRuleTypeChange(index, type)"
              @remove="removePattern(index)"
              @debug="openDebug(index)"
              @open-docs="openDocs"
            />
          </div>
        </template>
      </draggable>

      <div class="log-rule-footer">
        <a-dropdown :trigger="['click']">
          <a-button type="dashed" class="add-log-rule-btn">
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

        <span class="log-rule-count">
          {{ t('edit.ruleCountSummary', { n: patterns.length, m: activePatternCount }) }}
        </span>
      </div>
    </div>

    <LogPatternDebugModal
      v-model:open="debugModalOpen"
      :pattern="activePatternForDebug"
      :log-path="logPath"
    />

    <LogPatternDocsModal v-model:open="docsOpen" v-model:active-key="docsActiveKey" />
  </div>
</template>

<style scoped src="./logRuleConfig.css"></style>

<style scoped>
.push-config-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.push-config-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.push-config-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.docs-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}
</style>
