<script setup lang="ts">
import { computed, useSlots, type Component } from 'vue'
import { Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useConfirm } from '@/composables/useConfirm'
import { useModalCloseGuard } from './useModalCloseGuard'

/**
 * 统一弹窗基座。
 *
 * 接管默认尺寸档位、居中、关闭销毁、提交态防误关、未保存关闭保护以及
 * Electron 无边框标题栏避让；其余 Ant Design Vue Modal 原生属性通过 $attrs 透传。
 */
defineOptions({ inheritAttrs: false })

export type AppModalSize = 'sm' | 'md' | 'lg' | 'xl' | 'full'
export type AppModalFooterMode = 'confirm' | 'close' | 'none' | 'custom'
export type AppModalLayer = 'default' | 'nested' | 'blocking'

const SIZE_WIDTH_MAP: Record<AppModalSize, number | string> = {
  sm: 480,
  md: 600,
  lg: 760,
  xl: 960,
  full: '90vw',
}

const LAYER_Z_INDEX: Record<AppModalLayer, number> = {
  default: 1000,
  nested: 1050,
  blocking: 1200,
}

const props = withDefaults(
  defineProps<{
    size?: AppModalSize
    /** 显式传入时覆盖 size 档位 */
    width?: number | string
    title?: string
    subtitle?: string
    icon?: Component
    footer?: AppModalFooterMode
    okText?: string
    cancelText?: string
    okDanger?: boolean
    okDisabled?: boolean
    /** 提交中：同步 confirmLoading 并锁定关闭入口 */
    submitting?: boolean
    /** 有未保存变更：点击取消或遮罩关闭前弹出确认 */
    dirty?: boolean
    dirtyTitle?: string
    dirtyDescription?: string
    /** body: 由弹窗正文单滚动体滚动；none: 交给内部独立面板（如编辑器）管理滚动 */
    scroll?: 'body' | 'none'
    /** default/nested 避让 32px 标题栏；blocking 仅用于启动/关闭安全层 */
    layer?: AppModalLayer
    centered?: boolean
    destroyOnClose?: boolean
    maskClosable?: boolean
    closable?: boolean
    keyboard?: boolean
    wrapClassName?: string
  }>(),
  {
    size: 'md',
    width: undefined,
    title: undefined,
    subtitle: undefined,
    icon: undefined,
    footer: 'confirm',
    okText: undefined,
    cancelText: undefined,
    okDanger: false,
    okDisabled: false,
    submitting: false,
    dirty: false,
    dirtyTitle: undefined,
    dirtyDescription: undefined,
    scroll: 'body',
    layer: 'default',
    centered: true,
    destroyOnClose: true,
    maskClosable: true,
    closable: true,
    keyboard: true,
    wrapClassName: undefined,
  }
)

const emit = defineEmits<{
  ok: []
  cancel: []
}>()

const open = defineModel<boolean>('open', { required: true })

const slots = useSlots()
const { t } = useI18n()
const [modal, ModalContextHolder] = Modal.useModal()
const { confirm } = useConfirm(modal)

const resolvedWidth = computed(() => props.width ?? SIZE_WIDTH_MAP[props.size])
const resolvedOkText = computed(() => props.okText ?? t('core.common.confirm'))
const resolvedCancelText = computed(() => props.cancelText ?? t('core.common.cancel'))
const resolvedCloseText = computed(() => props.cancelText ?? t('core.common.close'))
const resolvedZIndex = computed(() => LAYER_Z_INDEX[props.layer])

const canClose = computed(() => !props.submitting)
const hasCustomHeader = computed(() =>
  Boolean(slots.header || slots['header-extra'] || props.subtitle || props.icon)
)

const resolvedWrapClassName = computed(() =>
  [
    'app-modal-wrap',
    props.scroll === 'none' ? 'app-modal-wrap--none-scroll' : null,
    props.size === 'full' ? 'app-modal-wrap--full' : null,
    props.layer === 'blocking' ? 'app-modal-wrap--blocking' : null,
    props.wrapClassName,
  ]
    .filter(Boolean)
    .join(' ')
)

const { requestClose } = useModalCloseGuard({
  open,
  dirty: () => props.dirty,
  submitting: () => props.submitting,
  confirmDiscard: () =>
    confirm({
      tone: 'warning',
      title: props.dirtyTitle ?? t('core.edit.youHaveUnsavedChanges'),
      description: props.dirtyDescription ?? t('core.edit.leaveWithoutSavingUnsaved'),
      zIndex: resolvedZIndex.value + 50,
    }),
  onClose: () => {
    open.value = false
    emit('cancel')
  },
})

const handleCancel = () => {
  void requestClose()
}

const handleOk = () => {
  if (props.submitting || props.okDisabled) return
  emit('ok')
}
</script>

<template>
  <ModalContextHolder />
  <a-modal
    v-bind="$attrs"
    :open="open"
    :width="resolvedWidth"
    :title="hasCustomHeader ? undefined : title"
    :footer="footer === 'none' ? null : undefined"
    :centered="centered"
    :destroy-on-close="destroyOnClose"
    :closable="closable && canClose"
    :keyboard="keyboard && canClose"
    :mask-closable="maskClosable && canClose"
    :z-index="resolvedZIndex"
    :wrap-class-name="resolvedWrapClassName"
    class="app-modal"
    @cancel="handleCancel"
  >
    <template v-if="hasCustomHeader" #title>
      <slot name="header">
        <div class="app-modal-header">
          <span v-if="icon" class="app-modal-icon" aria-hidden="true">
            <component :is="icon" />
          </span>
          <div class="app-modal-heading">
            <div class="app-modal-title-row">
              <span v-if="title" class="app-modal-title">{{ title }}</span>
              <slot name="header-extra" />
            </div>
            <div v-if="subtitle" class="app-modal-subtitle">{{ subtitle }}</div>
          </div>
        </div>
      </slot>
    </template>

    <slot />

    <template v-if="footer !== 'none'" #footer>
      <slot name="footer">
        <div
          class="app-modal-footer"
          :class="{ 'app-modal-footer--split': Boolean($slots['footer-left']) }"
        >
          <div v-if="$slots['footer-left']" class="app-modal-footer-left">
            <slot name="footer-left" />
          </div>
          <a-space>
            <template v-if="footer === 'close'">
              <a-button :disabled="submitting" @click="handleCancel">
                {{ resolvedCloseText }}
              </a-button>
            </template>
            <template v-else-if="footer === 'confirm'">
              <a-button :disabled="submitting" @click="handleCancel">
                {{ resolvedCancelText }}
              </a-button>
              <a-button
                type="primary"
                :danger="okDanger"
                :loading="submitting"
                :disabled="okDisabled"
                @click="handleOk"
              >
                {{ resolvedOkText }}
              </a-button>
            </template>
          </a-space>
        </div>
      </slot>
    </template>
  </a-modal>
</template>

<style scoped>
.app-modal-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding-right: 24px;
}

.app-modal-icon {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 30px;
  height: 30px;
  margin-top: 1px;
  border-radius: var(--ant-border-radius);
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-size: 15px;
}

.app-modal-heading {
  flex: 1;
  min-width: 0;
}

.app-modal-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.app-modal-title {
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}

.app-modal-subtitle {
  margin-top: 2px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 400;
  line-height: 18px;
}

.app-modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.app-modal-footer--split {
  justify-content: space-between;
}

.app-modal-footer-left {
  min-width: 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
</style>
