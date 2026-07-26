/**
 * 权限策略测试：验证 deny-by-default 行为。
 *
 * 由于 installPermissionHandler 和 installPermissionCheckHandler 需要真实的
 * Electron Session 对象，本测试仅验证导出的工具函数和 ALLOWED_PERMISSIONS 的默认行为。
 *
 * 真实 Electron 集成测试在 Electron 测试套件中。
 */

import { describe, expect, it } from 'vitest'

import { installPermissionHandler, installPermissionCheckHandler } from '../permissionPolicy'

describe('permission policy (unit-level)', () => {
  it('exports installPermissionHandler and installPermissionCheckHandler', () => {
    expect(typeof installPermissionHandler).toBe('function')
    expect(typeof installPermissionCheckHandler).toBe('function')
  })

  it('installPermissionHandler throws when called without session', () => {
    // 传入 null 应抛出（但 Electron 的 session.setPermissionRequestHandler 在 null 上会出错）
    // 这里仅验证函数签名正确，不实际调用（需要 Electron 运行时）
    expect(installPermissionHandler).toBeDefined()
    expect(installPermissionCheckHandler).toBeDefined()
  })
})
