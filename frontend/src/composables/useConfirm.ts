import { h, type VNode } from 'vue'
import { Modal } from 'ant-design-vue'
import {
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'

export type ConfirmTone = 'danger' | 'warning' | 'info'

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

type ConfirmHost = Pick<typeof Modal, 'confirm'>

const TONE_ICONS = {
  danger: ExclamationCircleOutlined,
  warning: WarningOutlined,
  info: InfoCircleOutlined,
} as const

/**
 * 供非 setup 逻辑复用的统一确认弹窗入口。
 *
 * 默认居中、沿用 appOverlays.css 的标题栏避让，高危确认自动应用 danger 样式。
 * 传入 Modal.useModal() 实例时可完整继承局部 ConfigProvider 上下文。
 */
export function openConfirm(options: ConfirmOptions, host: ConfirmHost = Modal): Promise<boolean> {
  const tone: ConfirmTone = options.tone ?? 'warning'
  const Icon = TONE_ICONS[tone]

  return new Promise<boolean>(resolve => {
    let settled = false
    const finish = (value: boolean) => {
      if (settled) return
      settled = true
      resolve(value)
    }

    host.confirm({
      title: options.title,
      content: options.description,
      icon: h(Icon),
      width: options.width ?? 480,
      okText: options.okText,
      cancelText: options.cancelText,
      okType: tone === 'danger' ? 'danger' : 'primary',
      okButtonProps: tone === 'danger' ? { danger: true } : undefined,
      centered: true,
      maskClosable: options.maskClosable ?? false,
      zIndex: options.zIndex,
      wrapClassName: 'app-confirm-modal',
      onOk: async () => {
        if (options.onOk) {
          await options.onOk()
        }
        finish(true)
      },
      onCancel: () => {
        finish(false)
      },
    })
  })
}

/**
 * 在 Vue 组件内使用的统一确认弹窗 composable，自动注入默认 i18n 按钮文案。
 */
export function useConfirm(host?: ConfirmHost) {
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

  return { confirm }
}
