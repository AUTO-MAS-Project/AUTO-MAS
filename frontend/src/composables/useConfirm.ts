import { h, type VNode } from 'vue'
import { Modal } from 'ant-design-vue'
import {
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

export type ConfirmTone = 'danger' | 'warning' | 'info'
export type AlertTone = 'info' | 'warning' | 'error'

export interface ConfirmOptions {
  /** 语义级别：danger 自动使用红色危险确认按钮 */
  tone?: ConfirmTone
  title: string
  description?: string | VNode
  okText?: string
  cancelText?: string
  width?: number | string
  maskClosable?: boolean
  zIndex?: number
  /** 确认回调；返回 Promise 时按钮自动进入 loading，抛错时弹窗保持打开 */
  onOk?: () => void | Promise<unknown>
}

export interface AlertOptions {
  /** 语义级别：映射到 AntD Modal.info / warning / error */
  tone?: AlertTone
  title: string
  description?: string | VNode
  okText?: string
  width?: number | string
  closable?: boolean
  maskClosable?: boolean
  zIndex?: number
  /** 确认回调；返回 Promise 时按钮自动进入 loading，抛错时弹窗保持打开 */
  onOk?: () => void | Promise<unknown>
}

type ConfirmHost = Pick<typeof Modal, 'confirm'>
type AlertHost = Pick<typeof Modal, 'info' | 'warning' | 'error'>
type DialogHost = ConfirmHost & AlertHost

const TONE_ICONS = {
  danger: ExclamationCircleOutlined,
  warning: WarningOutlined,
  info: InfoCircleOutlined,
} as const

/**
 * 供非 setup 逻辑复用的统一确认弹窗入口。
 *
 * 默认居中、沿用 appOverlays.css 的标题栏避让，高危确认自动应用 danger 样式。
 * 异步确认执行期间锁定取消按钮与 Esc，避免尚未完成的确认被提前算成取消；
 * 传入 Modal.useModal() 实例时可完整继承局部 ConfigProvider 上下文。
 */
export function openConfirm(options: ConfirmOptions, host: ConfirmHost = Modal): Promise<boolean> {
  const tone: ConfirmTone = options.tone ?? 'warning'
  const Icon = TONE_ICONS[tone]
  const initialMaskClosable = options.maskClosable ?? false

  return new Promise<boolean>(resolve => {
    let settled = false
    let running = false
    let modalInstance: ReturnType<ConfirmHost['confirm']> | undefined

    const finish = (value: boolean) => {
      if (settled) return
      settled = true
      resolve(value)
    }

    const setInteractionLocked = (locked: boolean) => {
      modalInstance?.update?.({
        cancelButtonProps: { disabled: locked },
        keyboard: !locked,
        maskClosable: locked ? false : initialMaskClosable,
        closable: false,
      })
    }

    modalInstance = host.confirm({
      title: options.title,
      content: options.description,
      icon: h(Icon),
      width: options.width ?? 480,
      okText: options.okText,
      cancelText: options.cancelText,
      okType: tone === 'danger' ? 'danger' : 'primary',
      okButtonProps: tone === 'danger' ? { danger: true } : undefined,
      cancelButtonProps: { disabled: false },
      centered: true,
      keyboard: true,
      closable: false,
      maskClosable: initialMaskClosable,
      zIndex: options.zIndex,
      wrapClassName: 'app-confirm-modal',
      onOk: async () => {
        if (running) return
        running = true
        setInteractionLocked(true)
        try {
          if (options.onOk) {
            await options.onOk()
          }
          finish(true)
        } catch (error) {
          running = false
          setInteractionLocked(false)
          throw error
        }
      },
      // 带 1 个参数让 AntD ActionButton 把关闭控制权交给本回调：执行中不关闭也不提前算作取消。
      onCancel: (close?: () => void) => {
        if (running) return
        finish(false)
        if (typeof close === 'function') close()
      },
    })
  })
}

/**
 * 供非 setup 逻辑复用的统一单按钮提示弹窗入口（info / warning / error）。
 *
 * 默认居中、沿用 appOverlays.css 的标题栏避让；
 * 异步 onOk 执行期间锁定 Esc、遮罩与关闭按钮，关闭或确认后统一 resolve。
 */
export function openAlert(options: AlertOptions, host: AlertHost = Modal): Promise<void> {
  const tone: AlertTone = options.tone ?? 'info'
  const initialClosable = options.closable ?? false
  const initialMaskClosable = options.maskClosable ?? false

  return new Promise<void>(resolve => {
    let settled = false
    let running = false
    let modalInstance: ReturnType<AlertHost[AlertTone]> | undefined

    const finish = () => {
      if (settled) return
      settled = true
      resolve()
    }

    const setInteractionLocked = (locked: boolean) => {
      modalInstance?.update?.({
        keyboard: !locked,
        maskClosable: locked ? false : initialMaskClosable,
        closable: locked ? false : initialClosable,
      })
    }

    modalInstance = host[tone]({
      title: options.title,
      content: options.description,
      width: options.width ?? 480,
      okText: options.okText,
      centered: true,
      keyboard: true,
      closable: initialClosable,
      maskClosable: initialMaskClosable,
      zIndex: options.zIndex,
      wrapClassName: 'app-confirm-modal',
      onOk: async () => {
        if (running) return
        running = true
        setInteractionLocked(true)
        try {
          if (options.onOk) {
            await options.onOk()
          }
          finish()
        } catch (error) {
          running = false
          setInteractionLocked(false)
          throw error
        }
      },
      onCancel: (close?: () => void) => {
        if (running) return
        finish()
        if (typeof close === 'function') close()
      },
    })
  })
}

/**
 * 在 Vue 组件内使用的统一确认与提示弹窗 composable，自动注入默认 i18n 按钮文案。
 */
export function useConfirm(host?: DialogHost) {
  const { t } = useI18n()

  const confirm = (options: ConfirmOptions): Promise<boolean> =>
    openConfirm(
      {
        okText: t('core.common.confirm'),
        cancelText: t('core.common.cancel'),
        ...options,
      },
      host
    )

  const alert = (options: AlertOptions): Promise<void> =>
    openAlert(
      {
        okText: t('core.common.confirm'),
        ...options,
      },
      host
    )

  return { confirm, alert }
}
