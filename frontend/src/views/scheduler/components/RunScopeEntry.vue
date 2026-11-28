<template>
  <li>
    <div class="tree-group" :class="{ expanded }">
      <a-checkbox
        class="entry-check"
        :aria-label="t('core.scheduler.scope.selectEntry', { name })"
        :checked="checked"
        :indeterminate="selected.size > 0 && !checked"
        :disabled="disabled"
        @change="(event: CheckboxChangeEvent) => emit('select', !!event.target.checked)"
      />
      <button
        class="entry-disclosure"
        type="button"
        :disabled="disabled || entry.missing || !entry.users.length"
        :aria-expanded="expanded"
        :aria-controls="expanded ? accountsId : undefined"
        :aria-label="
          expanded
            ? t('core.scheduler.scope.collapse', { name })
            : t('core.scheduler.scope.expand', { name })
        "
        @click="emit('toggle')"
      >
        <span class="tree-arrow"
          ><RightOutlined v-if="!entry.missing && entry.users.length" :rotate="expanded ? 90 : 0"
        /></span>
        <span v-if="position" class="ordinal">{{ String(position).padStart(2, '0') }}</span>
        <span class="entry-name">{{ name }}</span>
        <span class="entry-count" :class="{ mixed }">{{
          t('core.scheduler.scope.accounts', {
            count: mixed ? `${selected.size}/${entry.users.length}` : entry.users.length,
          })
        }}</span>
      </button>
    </div>
    <a-alert
      v-if="unavailable"
      type="warning"
      show-icon
      :message="t('core.scheduler.scope.missing')"
    >
      <template #action>
        <a-button type="link" size="small" :disabled="disabled" @click="emit('refresh')">{{
          t('core.scheduler.scope.refresh')
        }}</a-button>
      </template>
    </a-alert>
    <div
      v-if="expanded && !entry.missing"
      :id="accountsId"
      class="tree-children"
      role="group"
      :aria-label="name"
    >
      <a-checkbox
        v-for="user in entry.users"
        :key="user.uid"
        :checked="selected.has(user.uid)"
        :disabled="disabled"
        @change="
          (event: CheckboxChangeEvent) => emit('selectUser', user.uid, !!event.target.checked)
        "
        >{{ user.name }}</a-checkbox
      >
    </div>
  </li>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { RightOutlined } from '@ant-design/icons-vue'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import type { TaskScopeEntry } from '@/composables/taskSelection'

const props = defineProps<{
  entry: TaskScopeEntry
  selected: Set<string>
  checked: boolean
  unavailable: boolean
  expanded: boolean
  position?: number
  disabled?: boolean
}>()
const emit = defineEmits<{
  toggle: []
  select: [checked: boolean]
  selectUser: [uid: string, checked: boolean]
  refresh: []
}>()
const { t } = useI18n()
const accountsId = useId()
const name = computed(() => props.entry.name || props.entry.scriptId)
const mixed = computed(
  () => props.selected.size > 0 && props.selected.size < props.entry.users.length
)
</script>

<style scoped>
.tree-group {
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding-inline: 16px;
}
.tree-group:hover,
.tree-group:focus-within {
  background: var(--ant-color-fill-quaternary);
}
.tree-group.expanded {
  background: var(--ant-color-primary-bg);
}
.entry-check {
  min-height: 32px;
  align-items: center;
  padding-inline: 2px;
}
.entry-disclosure {
  flex: 1;
  min-width: 0;
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 2px 0 3px;
  border: 0;
  border-radius: var(--ant-border-radius-sm);
  background: transparent;
  color: var(--ant-color-text);
  font: inherit;
  text-align: start;
  cursor: pointer;
}
.entry-disclosure:disabled {
  cursor: default;
}
.entry-disclosure:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}
.tree-arrow {
  width: 16px;
  flex: none;
  text-align: center;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}
.entry-disclosure:hover .tree-arrow,
.expanded .tree-arrow,
.entry-count.mixed {
  color: var(--ant-color-link);
}
.ordinal,
.entry-count {
  color: var(--ant-color-text-secondary);
  font-variant-numeric: tabular-nums;
}
.ordinal {
  width: 18px;
  flex: none;
  font-size: 12px;
}
.entry-name {
  min-width: 0;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.entry-count {
  margin-inline-start: auto;
  font-size: 13px;
  white-space: nowrap;
}
.tree-children {
  display: flex;
  flex-direction: column;
  margin-inline-start: 48px;
  padding: 0 10px 4px 16px;
  border-inline-start: 1px solid var(--ant-color-border-secondary);
}
.tree-children :deep(.ant-checkbox-wrapper) {
  margin: 0;
  min-height: 32px;
  align-items: center;
}
.tree-children :deep(.ant-checkbox-wrapper > span:last-child) {
  padding-inline-start: 10px;
  overflow-wrap: anywhere;
}
</style>
