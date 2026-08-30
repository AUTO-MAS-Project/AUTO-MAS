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
  logPath?: string
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
  { key: 'split', label: '字符串切割', title: '按关键字过滤行，再掐头去尾提取内容' },
  { key: 'regex', label: '表达式', title: '正则匹配行后用 $() 表达式提取内容' },
  { key: 'multiline', label: '多行聚合', title: '由起始/结束正则划定窗口后提取字段' },
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

// 拖拽排序
const onDragEnd = () => {
  save()
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
</script>

<template>
  <div class="push-log-config">
    <div class="push-config-header">
      <h3>
        {{ t('edit.pushSettings') }}
        <a-tooltip :title="t('edit.whenTaskProgressCollected')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
      </h3>
      <div class="push-config-actions">
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

    <div class="push-config-body">
      <div v-if="!enabled" class="push-config-disabled-tip">
        {{ t('edit.pushCollectionOffRules') }}
      </div>

      <draggable
        v-model="patterns"
        item-key="_uid"
        handle=".drag-handle"
        :animation="200"
        ghost-class="pattern-ghost"
        chosen-class="pattern-chosen"
        drag-class="pattern-drag"
        class="patterns-list"
        @end="onDragEnd"
      >
        <template #item="{ element, index }">
          <div class="pattern-item">
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

      <div class="patterns-footer">
        <a-dropdown :trigger="['click']">
          <a-button type="dashed" class="add-pattern-btn">
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

        <span class="patterns-count">
          共 {{ patterns.length }} 条规则，{{ activePatternCount }} 条生效
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

<style scoped>
.push-log-config {
  width: 100%;
}

.push-config-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.push-config-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 6px;
}

.push-config-actions {
  display: flex;
  align-items: center;
  gap: 12px;
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

.push-config-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 24px;
}

.push-config-disabled-tip {
  padding: 10px 14px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.patterns-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pattern-item {
  position: relative;
}

.pattern-ghost {
  opacity: 0.5;
  background: var(--ant-color-primary-bg);
  border: 1px dashed var(--ant-color-primary);
  border-radius: 8px;
}

.pattern-chosen {
  cursor: grabbing;
}

.pattern-drag {
  opacity: 0.8;
}

.patterns-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.add-pattern-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.patterns-count {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}
</style>
