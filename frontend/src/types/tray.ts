// 托盘菜单项类型（与 frontend/electron/main.ts 保持一致）
export type TrayAction = 'show' | 'hide' | 'stopAll' | 'restartApp' | 'quit'

export interface TrayMenuItem {
  id: string
  label: string
  action: TrayAction
}

// 托盘菜单可选的动作类型
export const TRAY_ACTION_OPTIONS: { value: TrayAction; label: string }[] = [
  { value: 'show', label: '显示窗口' },
  { value: 'hide', label: '隐藏窗口' },
  { value: 'stopAll', label: '停止全部任务' },
  { value: 'restartApp', label: '重启应用' },
  { value: 'quit', label: '退出' },
]

// 默认托盘菜单项（与旧版硬编码菜单保持一致）
export const DEFAULT_TRAY_ITEMS: TrayMenuItem[] = [
  { id: 'show', label: '显示窗口', action: 'show' },
  { id: 'hide', label: '隐藏窗口', action: 'hide' },
  { id: 'quit', label: '退出', action: 'quit' },
]
