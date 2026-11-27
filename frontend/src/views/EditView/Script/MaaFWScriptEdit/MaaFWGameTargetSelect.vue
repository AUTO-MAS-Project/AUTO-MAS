<template>
  <a-form-item>
    <template #label>
      <span class="form-label">{{ label }}</span>
    </template>
    <!-- 第一项「未选择」用来清空；当前已选但类型不符或已不在列表里的项排在末尾并禁用 -->
    <a-select
      :value="binding.targetValue"
      :placeholder="placeholder"
      :loading="binding.loading"
      :disabled="binding.disabled"
      show-search
      option-filter-prop="label"
      :dropdown-render="binding.hasCandidates ? undefined : renderDropdown"
      @change="binding.selectTarget"
    >
      <a-select-option value="-" :label="t('core.games.noTarget')">
        {{ t('core.games.noTarget') }}
      </a-select-option>
      <a-select-option
        v-for="option in binding.targetOptions"
        :key="option.value"
        :value="option.value"
        :label="option.label"
        :disabled="option.disabled"
        :title="option.note || undefined"
      >
        {{ option.label
        }}<span v-if="option.note" :class="{ 'option-warning': !option.disabled }">
          — {{ option.note }}</span
        >
      </a-select-option>
    </a-select>
  </a-form-item>
</template>

<script setup lang="ts">
import { h, type VNode } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { MaaFWInlineGameBinding } from './useMaaFWInlineGameBinding'

defineProps<{
  binding: MaaFWInlineGameBinding
  label: string
  placeholder: string
}>()

const { t } = useI18n()

// 没有可选的目标时，下拉底部给一个去游戏管理添加的入口
const renderDropdown = ({ menuNode }: { menuNode: VNode }) =>
  h('div', [
    menuNode,
    h(
      RouterLink,
      { to: '/games', class: 'maafw-target-empty-link' },
      () => `${t('core.games.manageTargets')} →`
    ),
  ])
</script>

<style scoped src="./maafwSection.css"></style>

<style scoped>
.option-warning {
  color: var(--ant-color-warning);
}

:global(.maafw-target-empty-link) {
  display: block;
  padding: 8px 12px 4px;
  font-size: 13px;
  color: var(--ant-color-link);
}
</style>
