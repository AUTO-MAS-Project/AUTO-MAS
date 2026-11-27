<template>
  <a-form-item>
    <template #label>
      <span class="form-label">{{ label }}</span>
    </template>
    <!-- 所绑设备已删除时仍列出（禁用并标「已删除」），框里不露出设备 uid -->
    <a-select
      :value="binding.targetSelected ? binding.deviceValue : undefined"
      :placeholder="binding.targetSelected ? t('core.games.selectDevice') : emptyPlaceholder"
      :loading="binding.loading"
      :disabled="binding.deviceDisabled"
      @change="binding.selectDevice"
    >
      <a-select-option value="-">{{ t('core.games.noTarget') }}</a-select-option>
      <a-select-option
        v-for="device in binding.deviceOptions"
        :key="device.value"
        :value="device.value"
        :disabled="device.disabled"
      >
        {{ device.label }}
      </a-select-option>
    </a-select>
  </a-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { MaaFWInlineGameBinding } from './useMaaFWInlineGameBinding'

defineProps<{
  binding: MaaFWInlineGameBinding
  label: string
  /** 还没选目标时的占位文字 */
  emptyPlaceholder: string
}>()

const { t } = useI18n()
</script>

<style scoped src="./maafwSection.css"></style>
