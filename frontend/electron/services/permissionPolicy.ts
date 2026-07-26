/**
 * 权限请求处理策略：默认拒绝所有未声明的权限请求。
 *
 * 当前 AUTO-MAS 桌面应用不需要麦克风、摄像头、通知、midi 等浏览器权限，
 * 因此 session.setPermissionRequestHandler 实现 deny-by-default。
 */

import type { Session, PermissionRequest } from 'electron'

/**
 * 显式允许的权限列表（当前为空——任何权限请求都应被拒绝）。
 * 若未来需要允许特定权限（如 clipboard-read），在此数组中添加。
 */
const ALLOWED_PERMISSIONS: readonly string[] = []

/**
 * 安装 deny-by-default 权限请求处理器。
 *
 * 所有权限请求（notification、media、geolocation、midiSysex、pointerLock、
 * fullscreen、openExternal 等）默认拒绝，除非在 ALLOWED_PERMISSIONS 中显式声明。
 */
export function installPermissionHandler(session: Session): void {
  session.setPermissionRequestHandler(
    (
      _webContents: Electron.WebContents,
      permission: string,
      callback: (granted: boolean) => void
    ) => {
      if (ALLOWED_PERMISSIONS.includes(permission)) {
        callback(true)
        return
      }
      callback(false)
    }
  )
}

/**
 * 在 session 级别设置权限检查处理器的默认状态。
 *
 * 生产环境也拒绝所有权限请求，确保即使 setPermissionRequestHandler 未覆盖的情况
 * 也不会被默认允许。
 */
export function installPermissionCheckHandler(session: Session): void {
  session.setPermissionCheckHandler(
    (_webContents: Electron.WebContents | null, permission: string): boolean => {
      return ALLOWED_PERMISSIONS.includes(permission)
    }
  )
}
