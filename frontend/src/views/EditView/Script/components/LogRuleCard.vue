<script setup lang="ts">
import { DeleteOutlined, EditOutlined } from '@ant-design/icons-vue'
import { nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import DragHandle from '@/components/DragHandle.vue'

const { t } = useI18n()

interface Props {
  name?: string
  index: number
  enabled: boolean
  showDebug?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  name: '',
  showDebug: false,
})

const emit = defineEmits<{
  'update:name': [value: string | undefined]
  'update:enabled': [value: boolean]
  remove: []
  debug: []
}>()

const editingName = ref(false)
const nameInputRef = ref<{ focus: () => void } | null>(null)
const nameValue = ref('')

const startEditName = () => {
  if (editingName.value) return
  nameValue.value = props.name || ''
  editingName.value = true
  nextTick(() => nameInputRef.value?.focus())
}

const finishEditName = () => {
  if (!editingName.value) return
  const trimmed = nameValue.value.trim()
  emit('update:name', trimmed || undefined)
  editingName.value = false
}

const onEnabledChange = (enabled: boolean) => {
  emit('update:enabled', enabled)
}
</script>

<template>
  <div :class="['log-rule-card', { 'rule-disabled': !enabled }]">
    <div class="rule-header">
      <div class="rule-header-left">
        <DragHandle :title="t('edit.dragRule')" />
        <slot name="type" />
      </div>

      <div class="rule-title-wrap" @click="startEditName">
        <EditOutlined v-if="!editingName" class="rule-title-icon" />
        <span v-if="!editingName" class="rule-title">
          {{ name?.trim() || `规则${index + 1}` }}
        </span>
        <a-input
          v-else
          ref="nameInputRef"
          v-model:value="nameValue"
          class="rule-title-input"
          size="small"
          :placeholder="t('edit.ruleTitle')"
          @click.stop
          @blur="finishEditName"
          @press-enter="finishEditName"
        />
      </div>

      <div class="rule-header-right">
        <slot name="header-extra" />
        <a-switch :checked="enabled" size="small" @change="onEnabledChange" />

        <a-tooltip v-if="showDebug" :title="t('edit.debug')">
          <a-button
            size="small"
            class="rule-op-btn"
            :aria-label="t('edit.debug')"
            @click="emit('debug')"
          >
            <slot name="debug-icon" />
          </a-button>
        </a-tooltip>

        <a-tooltip :title="t('edit.delete')">
          <a-button
            size="small"
            danger
            class="rule-op-btn"
            :aria-label="t('edit.delete')"
            @click="emit('remove')"
          >
            <DeleteOutlined />
          </a-button>
        </a-tooltip>
      </div>
    </div>

    <div class="rule-body">
      <slot />
    </div>

    <div v-if="$slots.footer" class="rule-footer">
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped>
.log-rule-card {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 16px;
  transition: opacity 0.2s;
}

.log-rule-card.rule-disabled {
  opacity: 0.55;
}

.log-rule-card.rule-disabled:hover {
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

.rule-op-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px;
}

.rule-body {
  padding-top: 4px;
}

.rule-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px dashed var(--ant-color-border-secondary);
}
</style>
