import { describe, expect, it } from 'vitest'
import {
  buildSuggestion,
  buildVersionConflictSuggestion,
  createInitialStepState,
  inferFailureStage,
  parseDistributionAndRequested,
  parseInstalledVersionFromMessage,
  parseLockedPluginConflict,
  parsePluginWarnings,
  transitionToFailure,
  transitionToRetry,
  transitionToRunning,
  transitionToSkipped,
  transitionToSuccess,
  useInitializationStateMachine,
} from './useInitializationStateMachine'

describe('useInitializationStateMachine', () => {
  describe('createInitialStepState', () => {
    it('starts in waiting status with zero progress', () => {
      const state = createInitialStepState()
      expect(state.status).toBe('waiting')
      expect(state.progress).toBe(0)
      expect(state.failureDetails).toBeUndefined()
    })
  })

  describe('transitionToRunning', () => {
    it('moves from waiting to running', () => {
      const state = createInitialStepState()
      const next = transitionToRunning(state, '正在下载')
      expect(next.status).toBe('running')
      expect(next.message).toBe('正在下载')
      expect(next.countdown).toBe(0)
    })

    it('preserves existing progress when re-entering running', () => {
      const state = { ...createInitialStepState(), progress: 42 }
      const next = transitionToRunning(state)
      expect(next.progress).toBe(42)
    })
  })

  describe('transitionToSuccess', () => {
    it('moves to success with full progress', () => {
      const state = { ...createInitialStepState(), progress: 50, currentMirror: 'Tsinghua' }
      const next = transitionToSuccess(state, '完成')
      expect(next.status).toBe('success')
      expect(next.progress).toBe(100)
      expect(next.currentMirror).toBe('')
    })

    it('clears failure details when entering success', () => {
      const failed = transitionToFailure(createInitialStepState(), 'timeout', { stepKey: 'python' })
      const next = transitionToSuccess(failed)
      expect(next.failureDetails).toBeUndefined()
    })
  })

  describe('transitionToFailure', () => {
    it('captures specific backend error message in failure details', () => {
      const state = createInitialStepState()
      const next = transitionToFailure(state, 'Connection refused (ECONNREFUSED)', {
        stepKey: 'python',
      })
      expect(next.status).toBe('failure')
      expect(next.failureDetails).toBeDefined()
      // Lane 8 要求：失败不得只给"请选择镜像源"，必须保留具体错误
      expect(next.failureDetails?.reason).toBe('Connection refused (ECONNREFUSED)')
      expect(next.failureDetails?.suggestion).not.toBe('')
      expect(next.failureDetails?.suggestion).not.toContain('请选择镜像源')
    })

    it('preserves retry count across repeated failures', () => {
      let state = createInitialStepState()
      state = transitionToFailure(state, 'first failure', { stepKey: 'python' })
      expect(state.failureDetails?.retryCount).toBe(0)

      state = transitionToRetry(state)
      expect(state.failureDetails?.retryCount).toBe(1)

      state = transitionToFailure(state, 'second failure', { stepKey: 'python' })
      // retryCount should reflect the previous retry attempt
      expect(state.failureDetails?.retryCount).toBe(1)
    })

    it('records the last attempted mirror', () => {
      const state = createInitialStepState()
      const next = transitionToFailure(state, 'download broken', {
        stepKey: 'python',
        mirrorTried: 'Tsinghua',
        mirrorProgress: { current: 2, total: 5 },
      })
      expect(next.failureDetails?.mirrorTried).toBe('Tsinghua')
      expect(next.failureDetails?.mirrorProgress).toEqual({ current: 2, total: 5 })
    })

    it('records ISO timestamp of the failure', () => {
      const state = createInitialStepState()
      const before = new Date().getTime()
      const next = transitionToFailure(state, 'oops', { stepKey: 'python' })
      const after = new Date().getTime()
      const ts = new Date(next.failureDetails!.lastAttemptAt).getTime()
      expect(ts).toBeGreaterThanOrEqual(before - 5)
      expect(ts).toBeLessThanOrEqual(after + 5)
    })
  })

  describe('transitionToSkipped', () => {
    it('moves to skipped with full progress', () => {
      const state = createInitialStepState()
      const next = transitionToSkipped(state)
      expect(next.status).toBe('skipped')
      expect(next.progress).toBe(100)
      expect(next.message).toBe('已跳过')
    })

    it('clears runtime diagnostics but keeps failure details for audit', () => {
      const failed = transitionToFailure(createInitialStepState(), 'err', { stepKey: 'git' })
      const next = transitionToSkipped(failed)
      expect(next.status).toBe('skipped')
      expect(next.currentMirror).toBe('')
      // failureDetails from previous attempt remains accessible
      expect(next.failureDetails).toBeDefined()
    })
  })

  describe('transitionToRetry', () => {
    it('moves to retry and increments retry count', () => {
      const failed = transitionToFailure(createInitialStepState(), 'err', { stepKey: 'python' })
      const next = transitionToRetry(failed)
      expect(next.status).toBe('retry')
      expect(next.failureDetails?.retryCount).toBe(1)
      expect(next.message).toContain('第 1 次')
    })

    it('works without prior failure details', () => {
      const state = createInitialStepState()
      const next = transitionToRetry(state)
      expect(next.status).toBe('retry')
      expect(next.failureDetails).toBeUndefined()
    })
  })

  describe('buildSuggestion', () => {
    it('returns network suggestion for timeout errors', () => {
      const s = buildSuggestion('python', 'ETIMEDOUT connection timeout', undefined)
      expect(s).toContain('网络')
      expect(s).not.toContain('请选择镜像源')
    })

    it('returns permission suggestion for EACCES', () => {
      const s = buildSuggestion('dependency', 'EACCES: permission denied', undefined)
      expect(s).toContain('权限')
    })

    it('returns disk space suggestion for ENOSPC', () => {
      const s = buildSuggestion('git', 'ENOSPC: no space left on device', undefined)
      expect(s).toContain('磁盘')
    })

    it('returns exhausted-mirror suggestion when all mirrors failed', () => {
      const s = buildSuggestion('python', 'failed', { current: 5, total: 5 })
      expect(s).toContain('5 个镜像源')
    })

    it('never returns the generic "请选择镜像源" phrase', () => {
      const cases = [
        { step: 'python', reason: 'unknown', mp: undefined },
        { step: 'pip', reason: '', mp: undefined },
        { step: 'repository', reason: 'authentication failed', mp: undefined },
        { step: 'backend', reason: 'websocket connection failed', mp: undefined },
      ]
      for (const c of cases) {
        const s = buildSuggestion(c.step, c.reason, c.mp)
        expect(s).not.toBe('')
        expect(s).not.toContain('请选择镜像源')
      }
    })

    it('returns backend-specific suggestion for backend step', () => {
      const s = buildSuggestion('backend', 'ImportError', undefined)
      expect(s).toContain('后端启动失败')
    })
  })

  describe('inferFailureStage', () => {
    it('classifies download errors', () => {
      expect(inferFailureStage('download failed')).toBe('download')
      expect(inferFailureStage('下载中断')).toBe('download')
    })

    it('classifies network errors', () => {
      expect(inferFailureStage('ETIMEDOUT')).toBe('network')
      expect(inferFailureStage('connection timeout')).toBe('network')
    })

    it('classifies unknown errors', () => {
      expect(inferFailureStage('something weird')).toBe('unknown')
    })
  })

  describe('useInitializationStateMachine composable', () => {
    it('initializes steps for all provided keys', () => {
      const { steps, failedCount, skippedCount } = useInitializationStateMachine([
        'python',
        'backend',
      ])
      expect(Object.keys(steps.value)).toEqual(['python', 'backend'])
      expect(steps.value.python.status).toBe('waiting')
      expect(failedCount.value).toBe(0)
      expect(skippedCount.value).toBe(0)
    })

    it('failedCount reflects failure states', () => {
      const { steps, setStep, failedCount } = useInitializationStateMachine(['python', 'git'])
      setStep('python', transitionToFailure(steps.value.python, 'err', { stepKey: 'python' }))
      expect(failedCount.value).toBe(1)
      setStep('git', transitionToFailure(steps.value.git, 'err', { stepKey: 'git' }))
      expect(failedCount.value).toBe(2)
    })

    it('skippedCount reflects skipped states', () => {
      const { steps, setStep, skippedCount } = useInitializationStateMachine(['python', 'git'])
      setStep('python', transitionToSkipped(steps.value.python))
      expect(skippedCount.value).toBe(1)
    })

    it('reset returns all steps to waiting', () => {
      const { steps, setStep, reset } = useInitializationStateMachine(['python'])
      setStep('python', transitionToSuccess(steps.value.python))
      reset()
      expect(steps.value.python.status).toBe('waiting')
    })
  })

  // Lane 8：插件版本锁冲突解析测试
  describe('parseDistributionAndRequested', () => {
    it('parses package name with >= specifier', () => {
      const r = parseDistributionAndRequested('auto-mas-core>=6.0.0a1')
      expect(r.distribution).toBe('auto-mas-core')
      expect(r.requested).toBe('>=6.0.0a1')
    })

    it('parses package name with == specifier', () => {
      const r = parseDistributionAndRequested('some-pkg==1.2.3')
      expect(r.distribution).toBe('some-pkg')
      expect(r.requested).toBe('==1.2.3')
    })

    it('parses package name without specifier', () => {
      const r = parseDistributionAndRequested('some-pkg')
      expect(r.distribution).toBe('some-pkg')
      expect(r.requested).toBe('')
    })

    it('handles empty or invalid input safely', () => {
      expect(parseDistributionAndRequested('')).toEqual({ distribution: '', requested: '' })
      // 数字开头的非包名仍返回 trim 结果，不抛错
      const r = parseDistributionAndRequested('123invalid')
      expect(r.distribution).toBe('123invalid')
    })

    it('handles package name with dots and underscores', () => {
      const r = parseDistributionAndRequested('auto_mas.plugin_browser>=0.1.0')
      expect(r.distribution).toBe('auto_mas.plugin_browser')
      expect(r.requested).toBe('>=0.1.0')
    })
  })

  describe('parseInstalledVersionFromMessage', () => {
    it('extracts installed version from standard message', () => {
      const msg = 'Installed version 6.0.0a1 does not satisfy auto-mas-core>=6.0.0a1'
      expect(parseInstalledVersionFromMessage(msg)).toBe('6.0.0a1')
    })

    it('returns null for unknown installed version', () => {
      const msg = 'Installed version unknown does not satisfy auto-mas-core>=6.0.0a1'
      expect(parseInstalledVersionFromMessage(msg)).toBeNull()
    })

    it('returns null when message format does not match', () => {
      expect(parseInstalledVersionFromMessage('some other error')).toBeNull()
    })

    it('returns null for empty or non-string input', () => {
      expect(parseInstalledVersionFromMessage('')).toBeNull()
      expect(parseInstalledVersionFromMessage(null as unknown as string)).toBeNull()
    })

    it('is case-insensitive when matching "Installed version"', () => {
      const msg = 'installed VERSION 1.2.3 does not satisfy foo>=1.0.0'
      expect(parseInstalledVersionFromMessage(msg)).toBe('1.2.3')
    })
  })

  describe('parseLockedPluginConflict', () => {
    it('extracts the locked and requested versions from the Alpha lock error', () => {
      const conflict = parseLockedPluginConflict(
        'Locked plugin automas_plugin_maaend_adapter==0.0.4 violates automas_plugin_maaend_adapter==0.0.3'
      )

      expect(conflict).toMatchObject({
        distribution: 'automas_plugin_maaend_adapter',
        locked: '0.0.4',
        requested: '==0.0.3',
        kind: 'version-mismatch',
      })
      expect(conflict?.suggestion).toContain('切换镜像源或重复安装无法解决')
    })

    it('returns null for unrelated errors', () => {
      expect(parseLockedPluginConflict('download failed')).toBeNull()
    })
  })

  describe('buildVersionConflictSuggestion', () => {
    it('returns install-failed suggestion with raw message', () => {
      const s = buildVersionConflictSuggestion({
        distribution: 'auto-mas-core',
        locked: null,
        requested: '>=6.0.0a1',
        installed: null,
        kind: 'install-failed',
        rawMessage: 'pip install raised ConnectionError',
      })
      expect(s).toContain('auto-mas-core')
      expect(s).toContain('ConnectionError')
      expect(s).not.toBe('')
    })

    it('returns missing-entry-point suggestion mentioning entry_points', () => {
      const s = buildVersionConflictSuggestion({
        distribution: 'automas-plugin-browser',
        locked: null,
        requested: '>=0.1.0',
        installed: '0.1.0',
        kind: 'missing-entry-point',
        rawMessage: 'no entry point found',
      })
      expect(s).toContain('auto_mas.plugins')
      expect(s).toContain('entry_points')
    })

    it('version-mismatch suggestion includes installed and requested when both present', () => {
      const s = buildVersionConflictSuggestion({
        distribution: 'auto-mas-core',
        locked: null,
        requested: '>=6.0.0a1',
        installed: '5.9.0',
        kind: 'version-mismatch',
        rawMessage: 'Installed version 5.9.0 does not satisfy auto-mas-core>=6.0.0a1',
      })
      expect(s).toContain('5.9.0')
      expect(s).toContain('>=6.0.0a1')
      expect(s).toContain('site-packages')
    })

    it('version-mismatch suggestion mentions runtime-lock when locked is provided', () => {
      const s = buildVersionConflictSuggestion({
        distribution: 'auto-mas-core',
        locked: '6.0.0a1',
        requested: '>=6.0.0a1',
        installed: '5.9.0',
        kind: 'version-mismatch',
        rawMessage: 'Installed version 5.9.0 does not satisfy auto-mas-core>=6.0.0a1',
      })
      expect(s).toContain('runtime-lock.json')
      expect(s).toContain('6.0.0a1')
    })

    it('never returns empty string', () => {
      const cases = [
        {
          distribution: '',
          locked: null,
          requested: '',
          installed: null,
          kind: 'version-mismatch' as const,
          rawMessage: '',
        },
        {
          distribution: 'foo',
          locked: null,
          requested: '',
          installed: null,
          kind: 'install-failed' as const,
          rawMessage: '',
        },
      ]
      for (const c of cases) {
        expect(buildVersionConflictSuggestion(c)).not.toBe('')
      }
    })
  })

  describe('parsePluginWarnings', () => {
    it('returns empty array for undefined or null', () => {
      expect(parsePluginWarnings(undefined)).toEqual([])
      expect(parsePluginWarnings(null)).toEqual([])
    })

    it('returns empty array for empty array', () => {
      expect(parsePluginWarnings([])).toEqual([])
    })

    it('parses version-mismatch warning into structured conflict', () => {
      const warnings = [
        {
          packageName: 'auto-mas-core>=6.0.0a1',
          message: 'Installed version 5.9.0 does not satisfy auto-mas-core>=6.0.0a1',
          kind: 'version-mismatch',
        },
      ]
      const conflicts = parsePluginWarnings(warnings)
      expect(conflicts).toHaveLength(1)
      const c = conflicts[0]
      expect(c.distribution).toBe('auto-mas-core')
      expect(c.requested).toBe('>=6.0.0a1')
      expect(c.installed).toBe('5.9.0')
      expect(c.kind).toBe('version-mismatch')
      expect(c.suggestion).not.toBe('')
      expect(c.suggestion).toContain('auto-mas-core')
    })

    it('parses install-failed warning', () => {
      const conflicts = parsePluginWarnings([
        {
          packageName: 'some-pkg>=1.0.0',
          message: 'ConnectionError reaching PyPI',
          kind: 'install-failed',
        },
      ])
      expect(conflicts[0].kind).toBe('install-failed')
      expect(conflicts[0].installed).toBeNull()
      expect(conflicts[0].suggestion).toContain('some-pkg')
    })

    it('parses missing-entry-point warning', () => {
      const conflicts = parsePluginWarnings([
        {
          packageName: 'automas-plugin-browser',
          message: 'package installed but entry point not found',
          kind: 'missing-entry-point',
        },
      ])
      expect(conflicts[0].kind).toBe('missing-entry-point')
      expect(conflicts[0].suggestion).toContain('entry_points')
    })

    it('falls back unknown kind to version-mismatch', () => {
      const conflicts = parsePluginWarnings([
        {
          packageName: 'foo',
          message: 'weird error',
          kind: 'some-unknown-kind',
        },
      ])
      expect(conflicts[0].kind).toBe('version-mismatch')
    })

    it('preserves rawMessage from backend', () => {
      const raw = 'Installed version unknown does not satisfy foo>=1.0.0'
      const conflicts = parsePluginWarnings([
        { packageName: 'foo>=1.0.0', message: raw, kind: 'version-mismatch' },
      ])
      expect(conflicts[0].rawMessage).toBe(raw)
    })

    it('sets locked to null (runtime-lock not exposed to frontend)', () => {
      const conflicts = parsePluginWarnings([
        {
          packageName: 'foo>=1.0.0',
          message: 'Installed version 0.9.0 does not satisfy foo>=1.0.0',
          kind: 'version-mismatch',
        },
      ])
      // 当前 Electron API 未暴露 runtime-lock，前端不应编造 locked 值
      expect(conflicts[0].locked).toBeNull()
    })
  })

  describe('transitionToFailure with plugin warnings', () => {
    it('parses plugin warnings when stepKey is plugin-bootstrap', () => {
      const state = createInitialStepState()
      const warnings = [
        {
          packageName: 'auto-mas-core>=6.0.0a1',
          message: 'Installed version 5.9.0 does not satisfy auto-mas-core>=6.0.0a1',
          kind: 'version-mismatch',
        },
      ]
      const next = transitionToFailure(state, 'plugin bootstrap failed', {
        stepKey: 'plugin-bootstrap',
        pluginWarnings: warnings,
      })
      expect(next.pluginVersionConflicts).toBeDefined()
      expect(next.pluginVersionConflicts).toHaveLength(1)
      expect(next.pluginVersionConflicts?.[0].distribution).toBe('auto-mas-core')
      expect(next.pluginWarnings).toEqual(warnings)
    })

    it('ignores plugin warnings when stepKey is not plugin-bootstrap', () => {
      const state = createInitialStepState()
      const warnings = [{ packageName: 'foo>=1.0.0', message: 'err', kind: 'version-mismatch' }]
      const next = transitionToFailure(state, 'python install failed', {
        stepKey: 'python',
        pluginWarnings: warnings,
      })
      // 非 plugin-bootstrap 步骤不应解析版本冲突
      expect(next.pluginVersionConflicts).toBeUndefined()
    })

    it('structures a locked wheel contract failure even when warnings are absent', () => {
      const next = transitionToFailure(
        createInitialStepState(),
        'Locked plugin automas_plugin_maaend_adapter==0.0.4 violates automas_plugin_maaend_adapter==0.0.3',
        { stepKey: 'plugin-bootstrap' }
      )

      expect(next.pluginVersionConflicts).toHaveLength(1)
      expect(next.pluginVersionConflicts?.[0].locked).toBe('0.0.4')
      expect(next.pluginVersionConflicts?.[0].requested).toBe('==0.0.3')
    })
  })
})
