<script setup lang="ts">
import { Modal } from 'ant-design-vue'
import { DeleteOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    title: string
    confirm: () => void | Promise<void>
    text?: string
    disabled?: boolean
    size?: 'middle' | 'large'
  }>(),
  { size: 'middle' }
)
const { t } = useI18n()
const [modal, ModalContextHolder] = Modal.useModal()

function confirmDelete() {
  modal.confirm({
    title: props.title,
    centered: true,
    width: 480,
    okText: t('core.queue.del'),
    okType: 'danger',
    cancelText: t('core.queue.cancel'),
    onOk: props.confirm,
  })
}
</script>

<template>
  <ModalContextHolder />
  <a-button danger :size="size" :disabled="disabled" @click="confirmDelete">
    <template #icon><DeleteOutlined aria-hidden="true" /></template>
    {{ text ?? t('core.queue.del') }}
  </a-button>
</template>
