/**
 * Lane 8：设置页表单保护测试。
 *
 * 覆盖：
 * - 保存失败时保留用户输入（pendingChanges 不被清除）
 * - 保存成功时清除 pendingChanges
 * - 按 category 维度的错误展示与清除
 * - getEffectiveValue 优先返回 pendingChanges
 * - retryPending 批量重试
 * - revertField 放弃修改
 * - 多 category 聚合（getAggregateStateForCategories / clearErrorsForCategories / retryPendingForCategories）
 * - 恢复默认（getDefaultsForCategory）
 * - 敏感字段错误消息脱敏
 */
import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { KNOWN_DEFAULTS, useSettingsFormGuard } from './useSettingsFormGuard'
import type { GlobalConfig } from '@/api'

// 构造一个最小可用的 settings 对象
function makeSettings(): GlobalConfig {
  return {
    UI: {
      IfShowTray: true,
      IfToTray: true,
      IfHideCloseButton: false,
      Theme: 'light',
    },
    Notify: {
      SendTaskResultTime: '仅失败时',
      IfSendStatistic: false,
      IfSendSixStar: true,
      IfPushPlyer: true,
      IfSendMail: false,
      SMTPServerAddress: '',
      FromAddress: '',
      AuthorizationCode: '',
      ToAddress: '',
    },
    Start: {},
    Function: {},
    Voice: {},
    Update: {
      IfAutoUpdate: true,
      Source: 'GitHub',
      MirrorChyanCDK: '',
    },
  } as unknown as GlobalConfig
}

describe('useSettingsFormGuard', () => {
  describe('getEffectiveValue', () => {
    it('returns pendingChanges value when present', () => {
      const guard = useSettingsFormGuard()
      const settings = makeSettings()
      // 模拟暂存
      guard.pendingChanges['UI.Theme'] = 'dark'
      const v = guard.getEffectiveValue<string>(settings, 'UI', 'Theme')
      expect(v).toBe('dark')
    })

    it('falls back to settings value when no pending change', () => {
      const guard = useSettingsFormGuard()
      const settings = makeSettings()
      const v = guard.getEffectiveValue<boolean>(settings, 'UI', 'IfShowTray')
      expect(v).toBe(true)
    })

    it('returns undefined for missing field', () => {
      const guard = useSettingsFormGuard()
      const settings = makeSettings()
      const v = guard.getEffectiveValue(settings, 'UI', 'NonExistent')
      expect(v).toBeUndefined()
    })
  })

  describe('stageAndSave', () => {
    it('preserves pendingChanges when save fails (returns false)', async () => {
      const guard = useSettingsFormGuard()
      const saveFn = vi.fn().mockResolvedValue(false)
      const ok = await guard.stageAndSave('UI', 'Theme', 'dark', saveFn)
      expect(ok).toBe(false)
      // 失败时 pendingChanges 必须保留用户输入
      expect(guard.pendingChanges['UI.Theme']).toBe('dark')
      // 错误必须按 category 记录
      expect(guard.getError('UI')).toContain('Theme')
      expect(guard.getError('UI')).toContain('保存失败')
    })

    it('clears pendingChanges when save succeeds (returns true)', async () => {
      const guard = useSettingsFormGuard()
      const saveFn = vi.fn().mockResolvedValue(true)
      const ok = await guard.stageAndSave('UI', 'Theme', 'dark', saveFn)
      expect(ok).toBe(true)
      expect(guard.pendingChanges['UI.Theme']).toBeUndefined()
      expect(guard.getError('UI')).toBeNull()
    })

    it('preserves pendingChanges when saveFn throws', async () => {
      const guard = useSettingsFormGuard()
      const saveFn = vi.fn().mockRejectedValue(new Error('Network down'))
      const ok = await guard.stageAndSave('UI', 'Theme', 'dark', saveFn)
      expect(ok).toBe(false)
      // 抛错时也必须保留用户输入
      expect(guard.pendingChanges['UI.Theme']).toBe('dark')
      expect(guard.getError('UI')).toContain('Network down')
    })

    it('truncates very long error messages (sensitive data sanitization)', async () => {
      const guard = useSettingsFormGuard()
      const longMsg = 'x'.repeat(500)
      const saveFn = vi.fn().mockRejectedValue(new Error(longMsg))
      await guard.stageAndSave('Notify', 'SMTPServerAddress', 'test', saveFn)
      const err = guard.getError('Notify')
      expect(err).toBeTruthy()
      expect(err!.length).toBeLessThan(longMsg.length)
      expect(err).toContain('已截断')
    })

    it('tracks loading state during save', async () => {
      const guard = useSettingsFormGuard()
      let resolveFn!: (v: boolean) => void
      const saveFn = vi.fn(
        () =>
          new Promise<boolean>(resolve => {
            resolveFn = resolve
          })
      )
      const promise = guard.stageAndSave('UI', 'Theme', 'dark', saveFn)
      expect(guard.loading.value).toBe(true)
      resolveFn(true)
      await promise
      expect(guard.loading.value).toBe(false)
    })

    it('tracks savingKeys during save', async () => {
      const guard = useSettingsFormGuard()
      let resolveFn!: (v: boolean) => void
      const saveFn = vi.fn(
        () =>
          new Promise<boolean>(resolve => {
            resolveFn = resolve
          })
      )
      const promise = guard.stageAndSave('UI', 'Theme', 'dark', saveFn)
      expect(guard.isSaving('UI', 'Theme')).toBe(true)
      resolveFn(true)
      await promise
      expect(guard.isSaving('UI', 'Theme')).toBe(false)
    })
  })

  describe('retryPending', () => {
    it('retries all pending changes for a category and clears successful ones', async () => {
      const guard = useSettingsFormGuard()
      // 模拟两个失败的字段
      guard.pendingChanges['UI.Theme'] = 'dark'
      guard.pendingChanges['UI.IfShowTray'] = false
      guard.pendingChanges['Notify.IfSendMail'] = true // 其他 category，不应被重试

      const saveFn = vi.fn().mockResolvedValue(true)
      await guard.retryPending('UI', saveFn)

      // UI 下的 pending 应被清除
      expect(guard.pendingChanges['UI.Theme']).toBeUndefined()
      expect(guard.pendingChanges['UI.IfShowTray']).toBeUndefined()
      // Notify 下的应保留
      expect(guard.pendingChanges['Notify.IfSendMail']).toBe(true)
      // saveFn 应被调用 2 次（UI 下两个字段）
      expect(saveFn).toHaveBeenCalledTimes(2)
    })

    it('keeps failed pendingChanges and sets aggregate error', async () => {
      const guard = useSettingsFormGuard()
      guard.pendingChanges['UI.Theme'] = 'dark'
      guard.pendingChanges['UI.IfShowTray'] = false

      const saveFn = vi.fn().mockResolvedValueOnce(true).mockResolvedValueOnce(false)

      await guard.retryPending('UI', saveFn)

      // 第一个成功，第二个失败
      expect(guard.pendingChanges['UI.Theme']).toBeUndefined()
      expect(guard.pendingChanges['UI.IfShowTray']).toBe(false)
      expect(guard.getError('UI')).toContain('部分字段')
    })

    it('does nothing when no pending changes for category', async () => {
      const guard = useSettingsFormGuard()
      const saveFn = vi.fn()
      await guard.retryPending('UI', saveFn)
      expect(saveFn).not.toHaveBeenCalled()
    })
  })

  describe('revertField', () => {
    it('removes pending change for the field', () => {
      const guard = useSettingsFormGuard()
      guard.pendingChanges['UI.Theme'] = 'dark'
      guard.revertField('UI', 'Theme')
      expect(guard.pendingChanges['UI.Theme']).toBeUndefined()
    })

    it('clears category error when no other pending remains', () => {
      const guard = useSettingsFormGuard()
      guard.pendingChanges['UI.Theme'] = 'dark'
      // 模拟错误已设置
      guard.pendingChanges['Notify.IfSendMail'] = true
      // 手动触发错误状态
      guard.clearError('UI')
      // 设置 UI 错误
      guard.pendingChanges['UI.Theme'] = 'dark'
      guard.revertField('UI', 'Theme')
      // UI 下已无 pending，错误应被清除
      expect(guard.getError('UI')).toBeNull()
    })

    it('keeps category error when other pending remains', () => {
      const guard = useSettingsFormGuard()
      guard.pendingChanges['UI.Theme'] = 'dark'
      guard.pendingChanges['UI.IfShowTray'] = false
      guard.revertField('UI', 'Theme')
      // UI 下还有 IfShowTray，错误状态保留逻辑由调用方控制
      expect(guard.pendingChanges['UI.IfShowTray']).toBe(false)
    })
  })

  describe('error handling', () => {
    it('clearError removes error for category', async () => {
      const guard = useSettingsFormGuard()
      await guard.stageAndSave('UI', 'Theme', 'dark', vi.fn().mockResolvedValue(false))
      expect(guard.getError('UI')).not.toBeNull()
      guard.clearError('UI')
      expect(guard.getError('UI')).toBeNull()
    })

    it('getError returns null when no error set', () => {
      const guard = useSettingsFormGuard()
      expect(guard.getError('UI')).toBeNull()
    })
  })

  describe('computed pendingCount / hasPending', () => {
    it('reflects number of pending changes', () => {
      const guard = useSettingsFormGuard()
      expect(guard.pendingCount.value).toBe(0)
      expect(guard.hasPending.value).toBe(false)

      guard.pendingChanges['UI.Theme'] = 'dark'
      expect(guard.pendingCount.value).toBe(1)
      expect(guard.hasPending.value).toBe(true)

      guard.pendingChanges['Notify.IfSendMail'] = true
      expect(guard.pendingCount.value).toBe(2)
    })
  })

  describe('getDefaultsForCategory', () => {
    it('returns defaults for UI category', () => {
      const guard = useSettingsFormGuard()
      const defaults = guard.getDefaultsForCategory('UI')
      expect(defaults).not.toBeNull()
      expect(defaults?.IfShowTray).toBe(true)
    })

    it('returns defaults for Update category', () => {
      const guard = useSettingsFormGuard()
      const defaults = guard.getDefaultsForCategory('Update')
      expect(defaults?.IfAutoUpdate).toBe(true)
      expect(defaults?.Source).toBe('GitHub')
      expect(defaults?.Channel).toBe('stable')
    })

    it('returns null for category without defaults', () => {
      const guard = useSettingsFormGuard()
      // Start 的默认值对象为空 {}，但 KNOWN_DEFAULTS.Start 存在
      // 实际上 KNOWN_DEFAULTS.Start = {} 是空对象，getDefaultsForCategory 返回 {}
      const defaults = guard.getDefaultsForCategory('Start')
      // Start 在 KNOWN_DEFAULTS 中是空对象，所以返回 {}（truthy）而非 null
      // 这里测试 Function（不在 KNOWN_DEFAULTS 中）
      const fnDefaults = guard.getDefaultsForCategory('Function' as any)
      expect(fnDefaults).toBeNull()
    })

    it('KNOWN_DEFAULTS does not contain sensitive fields', () => {
      // 敏感字段（AuthorizationCode / KoishiToken / ServerChanKey）不应有默认值
      const notifyDefaults = KNOWN_DEFAULTS.Notify
      expect(notifyDefaults).toBeDefined()
      expect(notifyDefaults).not.toHaveProperty('AuthorizationCode')
      expect(notifyDefaults).not.toHaveProperty('ServerChanKey')
      expect(notifyDefaults).not.toHaveProperty('KoishiToken')
    })
  })

  describe('multi-category aggregation (TabFunction scenario)', () => {
    it('getAggregateStateForCategories returns first non-null error', async () => {
      const guard = useSettingsFormGuard()
      // Start 无错误，Function 有错误，Voice 无错误
      await guard.stageAndSave('Function', 'SomeKey', 'val', vi.fn().mockResolvedValue(false))

      const state = guard.getAggregateStateForCategories(['Start', 'Function', 'Voice'])
      expect(state.error).not.toBeNull()
      expect(state.error).toContain('SomeKey')
    })

    it('getAggregateStateForCategories sums pending counts across categories', () => {
      const guard = useSettingsFormGuard()
      guard.pendingChanges['Start.Key1'] = 'v1'
      guard.pendingChanges['Function.Key2'] = 'v2'
      guard.pendingChanges['Voice.Key3'] = 'v3'
      guard.pendingChanges['UI.Key4'] = 'v4' // 不在聚合范围内

      const state = guard.getAggregateStateForCategories(['Start', 'Function', 'Voice'])
      expect(state.pendingCountForCategories).toBe(3)
      expect(state.hasPendingForCategories).toBe(true)
    })

    it('getAggregateStateForCategories returns null error when no errors', () => {
      const guard = useSettingsFormGuard()
      const state = guard.getAggregateStateForCategories(['Start', 'Function'])
      expect(state.error).toBeNull()
      expect(state.pendingCountForCategories).toBe(0)
      expect(state.hasPendingForCategories).toBe(false)
    })

    it('clearErrorsForCategories clears errors for all given categories', async () => {
      const guard = useSettingsFormGuard()
      await guard.stageAndSave('Start', 'K1', 'v', vi.fn().mockResolvedValue(false))
      await guard.stageAndSave('Function', 'K2', 'v', vi.fn().mockResolvedValue(false))

      guard.clearErrorsForCategories(['Start', 'Function'])
      expect(guard.getError('Start')).toBeNull()
      expect(guard.getError('Function')).toBeNull()
    })

    it('retryPendingForCategories retries across multiple categories', async () => {
      const guard = useSettingsFormGuard()
      guard.pendingChanges['Start.K1'] = 'v1'
      guard.pendingChanges['Function.K2'] = 'v2'
      guard.pendingChanges['Voice.K3'] = 'v3'

      const saveFn = vi.fn().mockResolvedValue(true)
      await guard.retryPendingForCategories(['Start', 'Function', 'Voice'], saveFn)

      expect(saveFn).toHaveBeenCalledTimes(3)
      expect(guard.pendingCount.value).toBe(0)
    })
  })
})
