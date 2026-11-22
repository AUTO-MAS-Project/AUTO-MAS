<script setup lang="ts">
import { computed, ref } from 'vue'
import { Modal, type ButtonProps } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useConfirm, type ConfirmTone } from '@/composables/useConfirm'

/**
 * 统一确认操作按钮。
 *
 * risk="low" 使用行内气泡确认（a-popconfirm）；
 * risk="high" 使用居中模态确认（useConfirm），自动防重入并同步 loading 态。
 */
defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    risk?: 'low' | 'high'
    tone?: ConfirmTone
    title: string
    description?: string
    okText?: string
    cancelText?: string
    danger?: boolean
    type?: ButtonProps['type']
    size?: ButtonProps['size']
    disabled?: boolean
    loading?: boolean
    confirm: () => void | Promise<unknown>
  }>(),
  {
    risk: 'low',
    tone: 'danger',
    description: undefined,
    okText: undefined,
    cancelText: undefined,
    danger: undefined,
    type: 'default',
    size: 'middle',
    disabled: false,
    loading: false,
  }
)

const { t } = useI18n()
const [modal, ModalContextHolder] = Modal.useModal()
const { confirm: openConfirmModal } = useConfirm(modal)
const running = ref(false)

const isDanger = computed(() => props.danger ?? props.tone === 'danger')
const isBusy = computed(() => props.loading || running.value)
const resolvedOkText = computed(() => props.okText ?? t('core.common.confirm'))
const resolvedCancelText = computed(() => props.cancelText ?? t('core.common.cancel'))

const executeConfirm = async () => {
  if (props.disabled || isBusy.value) return
  running.value = true
  try {
    await props.confirm()
  } finally {
    running.value = false
  }
}

const handleHighRiskClick = async () => {
  if (props.disabled || isBusy.value) return
  await openConfirmModal({
    tone: props.tone,
    title: props.title,
    description: props.description,
    okText: resolvedOkText.value,
    cancelText: resolvedCancelText.value,
    onOk: executeConfirm,
  })
}
</script>

<template>
  <ModalContextHolder v-if="risk === 'high'" />
  <a-popconfirm
    v-if="risk === 'low'"
    :title="title"
    :description="description"
    :ok-text="resolvedOkText"
    :cancel-text="resolvedCancelText"
    :ok-type="isDanger ? 'danger' : 'primary'"
    :disabled="disabled || isBusy"
    @confirm="executeConfirm"
  >
    <a-button
      v-bind="$attrs"
      :type="type"
      :size="size"
      :danger="isDanger"
      :disabled="disabled"
      :loading="isBusy"
    >
      <template v-if="$slots.icon" #icon><slot name="icon" /></template>
      <slot />
    </a-button>
  </a-popconfirm>

  <a-button
    v-else
    v-bind="$attrs"
    :type="type"
    :size="size"
    :danger="isDanger"
    :disabled="disabled"
    :loading="isBusy"
    @click="handleHighRiskClick"
  >
    <template v-if="$slots.icon" #icon><slot name="icon" /></template>
    <slot />
  </a-button>
</template>
