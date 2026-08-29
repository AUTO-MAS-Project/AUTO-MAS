<script setup lang="ts">
import { DownOutlined, PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'
import draggable from 'vuedraggable'

import LogHookRule from './LogHookRule.vue'
import {
  useLogHookRules,
  type LogHookRule as LogHookRuleItem,
  type LogHookType,
} from '../composables/useLogHookRules'

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
  onChange: json => {
    emit('update:rules', json)
    emit('change', 'Script', 'LogHookRules', json)
  },
})

// 兼容父组件的 v-model:enabled 事件签名
const onEnabledChange = (value: boolean) => {
  emit('update:enabled', value)
  emit('change', 'Script', 'LogHookEnabled', value)
}

const addMenuItems = [
  { key: 'drop', label: '丢弃行', title: '匹配正则命中的日志行整行丢弃' },
  { key: 'replace', label: '改写行', title: '按匹配正则替换行内内容后继续交给后续规则' },
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

// 拖拽排序：规则按列表顺序执行，顺序本身是配置的一部分
const onDragEnd = () => {
  save()
}
</script>

<template>
  <div class="log-hook-config">
    <div class="hook-config-header">
      <h3>
        日志处理钩子
        <a-tooltip
          title="开启后按下列规则逐行预处理脚本日志：丢弃命中的噪声行、改写需要脱敏或归一化的内容。钩子先于任务日志、推送日志采集与成功/失败判定执行，被丢弃的行不会进入其中任何一环，请勿丢弃成功/失败标志所在的行。"
        >
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
      </h3>
      <a-tooltip title="开启后才会按规则处理日志；关闭时配置仍保留，行为与未配置钩子一致">
        <a-switch
          :checked="enabled"
          :checked-children="'启用'"
          :un-checked-children="'停用'"
          @change="onEnabledChange"
        />
      </a-tooltip>
    </div>

    <div class="hook-config-body">
      <div v-if="!enabled" class="hook-config-disabled-tip">
        日志处理钩子已停用，规则不会参与日志处理。
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
            添加规则
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
          共 {{ hookRules.length }} 条规则，{{ activeRuleCount }} 条生效，按列表顺序执行
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-hook-config {
  width: 100%;
}

.hook-config-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.hook-config-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 6px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
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
