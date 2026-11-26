<script setup lang="ts">
import { DeleteOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { ConfirmActionButton } from '@/components/ui'

withDefaults(
  defineProps<{
    title: string
    confirm: () => void | Promise<void>
    text?: string
    disabled?: boolean
    size?: 'middle' | 'large'
  }>(),
  { text: undefined, disabled: false, size: 'middle' }
)
const { t } = useI18n()
</script>

<template>
  <ConfirmActionButton
    risk="high"
    :title="title"
    :ok-text="t('core.queue.del')"
    :cancel-text="t('core.queue.cancel')"
    :size="size"
    :disabled="disabled"
    :confirm="confirm"
  >
    <template #icon><DeleteOutlined aria-hidden="true" /></template>
    {{ text ?? t('core.queue.del') }}
  </ConfirmActionButton>
</template>
