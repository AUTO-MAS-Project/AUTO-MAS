<template>
  <a-popover :open="open" trigger="click" placement="bottomRight" @open-change="setOpen">
    <template #content>
      <div class="weekly-editor">
        <div class="weekly-columns">
          <div class="weekly-options">
            <a-button
              v-for="target in options"
              :key="target"
              type="text"
              :disabled="disabled"
              class="weekly-option"
              @click="add(target)"
              >{{ targetLabel(target) }}</a-button
            >
          </div>
          <div class="weekly-selection">
            <div
              v-for="(target, index) in draftMode === 'custom' ? draftTargets : []"
              :key="index"
              class="weekly-row"
            >
              <span class="weekly-name">{{ index + 1 }}. {{ targetLabel(target) }}</span>
              <a-button
                type="text"
                size="small"
                :disabled="disabled || index === 0"
                :aria-label="t('core.plan.oknte.weeklyUp')"
                @click="move(index, -1)"
                ><UpOutlined
              /></a-button>
              <a-button
                type="text"
                size="small"
                :disabled="disabled || index === draftTargets.length - 1"
                :aria-label="t('core.plan.oknte.weeklyDown')"
                @click="move(index, 1)"
                ><DownOutlined
              /></a-button>
              <a-button
                type="text"
                size="small"
                :disabled="disabled"
                :aria-label="t('core.plan.oknte.weeklyRemove', { index: index + 1 })"
                @click="remove(index)"
                ><DeleteOutlined
              /></a-button>
            </div>
            <span v-if="draftMode !== 'custom' || !draftTargets.length" class="weekly-empty">{{
              draftMode === 'inherit'
                ? t('core.plan.oknte.weeklyUseAccount')
                : draftMode === 'off'
                  ? t('core.plan.oknte.weeklyDisabled')
                  : t('core.plan.oknte.weeklyAddHint')
            }}</span>
          </div>
        </div>
        <div class="weekly-footer">
          <a-space>
            <a-button
              type="text"
              size="small"
              :disabled="disabled"
              :class="{ 'weekly-mode-selected': draftMode === 'off' }"
              :aria-pressed="draftMode === 'off'"
              @click="selectMode('off')"
              >{{ t('core.plan.oknte.weeklyOff') }}</a-button
            >
            <a-button
              type="text"
              size="small"
              :disabled="disabled"
              :class="{ 'weekly-mode-selected': draftMode === 'inherit' }"
              :aria-pressed="draftMode === 'inherit'"
              @click="selectMode('inherit')"
              >{{ t('core.plan.oknte.weeklyInherit') }}</a-button
            >
          </a-space>
          <a-button
            type="primary"
            size="small"
            :disabled="disabled && !saving"
            :loading="saving"
            :aria-label="t('core.plan.oknte.weeklyConfirm')"
            @click="confirm"
            >{{ t('core.plan.oknte.weeklyConfirm') }}</a-button
          >
        </div>
      </div>
    </template>
    <a-button
      type="text"
      class="weekly-trigger"
      :class="{ inherited: enabled === undefined && targets === undefined }"
      :disabled="disabled"
      :aria-label="t('core.plan.oknte.weeklyTitle')"
    >
      <span class="weekly-summary" :title="summary">{{ summary }}</span
      ><DownOutlined />
    </a-button>
  </a-popover>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { DeleteOutlined, DownOutlined, UpOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { oknteWeeklyLabel } from '../oknteWeekly'
const props = defineProps<{
  enabled?: boolean
  targets?: string[]
  options: string[]
  disabled: boolean
  save: (targets: string[] | null) => Promise<void>
}>()
const { t } = useI18n()
const targetLabel = (value: string) => oknteWeeklyLabel(value, t)
const open = ref(false)
const saving = ref(false)
const dirty = ref(false)
const draftMode = ref<'custom' | 'off' | 'inherit'>('inherit')
const draftTargets = ref<string[]>([])
function setOpen(value: boolean) {
  if (saving.value) return
  if (value) {
    draftTargets.value = [...(props.targets ?? [])]
    draftMode.value =
      props.enabled === false
        ? 'off'
        : props.enabled === undefined && props.targets === undefined
          ? 'inherit'
          : 'custom'
    dirty.value = false
  }
  open.value = value
}
async function selectMode(mode: 'off' | 'inherit') {
  draftMode.value = mode
  dirty.value = true
  await confirm()
}
function add(target: string) {
  if (draftMode.value !== 'custom') draftTargets.value = []
  draftMode.value = 'custom'
  draftTargets.value.push(target)
  dirty.value = true
}
async function confirm() {
  if (!dirty.value) {
    open.value = false
    return
  }
  saving.value = true
  try {
    await props.save(
      draftMode.value === 'inherit'
        ? null
        : draftMode.value === 'off'
          ? []
          : [...draftTargets.value]
    )
    open.value = false
  } catch {
    // 保存入口已提示错误，保留草稿以便重试。
  } finally {
    saving.value = false
  }
}
const summary = computed(() => {
  if (props.enabled === false) return t('core.plan.oknte.weeklyOff')
  if (props.targets?.length) return props.targets.map(targetLabel).join('、')
  return t(
    props.enabled === undefined && props.targets === undefined
      ? 'core.plan.oknte.inheritShort'
      : 'core.plan.oknte.basedOnDetail'
  )
})
function remove(index: number) {
  draftTargets.value.splice(index, 1)
  dirty.value = true
}
function move(index: number, offset: number) {
  const next = [...draftTargets.value]
  ;[next[index], next[index + offset]] = [next[index + offset]!, next[index]!]
  draftTargets.value = next
  dirty.value = true
}
</script>
<style scoped>
.weekly-editor {
  width: min(580px, 80vw);
}
.weekly-columns {
  display: grid;
  grid-template-columns: 210px minmax(0, 1fr);
}
.weekly-options {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  padding-right: 12px;
  border-right: 1px solid var(--ant-color-border-secondary);
}
.weekly-option {
  text-align: left;
  white-space: normal;
  height: auto;
  min-height: 36px;
}
.weekly-selection {
  padding-left: 12px;
  max-height: 320px;
  overflow-y: auto;
}
.weekly-row {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 36px;
}
.weekly-name {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.weekly-empty {
  color: var(--ant-color-text-placeholder);
  display: block;
  padding: 8px 0;
}
.weekly-mode-selected {
  color: var(--ant-color-primary);
}
.weekly-footer {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--ant-color-border-secondary);
}
.weekly-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.weekly-summary {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.inherited {
  color: var(--ant-color-text-placeholder);
}
</style>
