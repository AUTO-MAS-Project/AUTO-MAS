import { randomUUID } from 'node:crypto'
import * as fs from 'node:fs'
import * as path from 'node:path'
import type {
  BackendService,
  BackendStartResult,
  RuntimeBackendUpdateCheck,
} from './services/backendService'
import { getLogger } from './services/logger'
import type { HotUpdatePhase, HotUpdateRecord, HotUpdateRepair } from './hotUpdateCoordination'

const logger = getLogger('热更协调')
const RENDERER_READY_TIMEOUT_MS = 10000
const CONNECTION_TIMEOUT_MS = 60000

export class HotUpdateOrchestrator {
  private record: HotUpdateRecord | null = null
  private flight: Promise<void> | null = null
  private rendererAck: ((ready: boolean) => void) | null = null
  private connectionTimer: NodeJS.Timeout | null = null
  private cancelled = false

  constructor(
    private readonly options: {
      backend: () => BackendService
      stateFile: string
      onState: (record: HotUpdateRecord) => void
      isClosing: () => boolean
    }
  ) {
    try {
      if (!fs.existsSync(options.stateFile)) return
      const candidate = JSON.parse(
        fs.readFileSync(options.stateFile, 'utf8')
      ) as Partial<HotUpdateRecord>
      if (
        typeof candidate.operationId !== 'string' ||
        typeof candidate.timestamp !== 'string' ||
        !['download', 'stopping', 'installing', 'starting', 'connecting', 'completed'].includes(
          candidate.phase ?? ''
        ) ||
        ![null, 'success', 'failed', 'cancelled'].includes(candidate.result!) ||
        typeof candidate.notified !== 'boolean' ||
        (candidate.baseCommit !== null && !/^[a-f0-9]{40}$/i.test(candidate.baseCommit ?? '')) ||
        (candidate.targetCommit !== null && !/^[a-f0-9]{40}$/i.test(candidate.targetCommit ?? ''))
      )
        return
      if (
        !options.backend().isManagedBackend() ||
        !options.backend().isHotUpdateVersionCurrent(candidate.version)
      )
        return
      this.record = { ...candidate, backendAvailable: undefined } as HotUpdateRecord
    } catch (error) {
      logger.warn(`读取热更通知记录失败: ${String(error)}`)
    }
  }

  getRecord(): HotUpdateRecord | null {
    return this.record ? { ...this.record } : null
  }

  private save(patch: Partial<HotUpdateRecord>): void {
    if (!this.record) return
    const next = { ...this.record, ...patch, timestamp: new Date().toISOString() }
    // 先落盘再发送事件，避免重启窗口内丢失目标身份及未送达通知。
    fs.mkdirSync(path.dirname(this.options.stateFile), { recursive: true })
    const temp = `${this.options.stateFile}.tmp`
    fs.writeFileSync(temp, JSON.stringify(next), 'utf8')
    fs.renameSync(temp, this.options.stateFile)
    this.record = next
    this.options.onState({ ...next })
  }

  private fail(
    failure: BackendStartResult,
    phase: HotUpdatePhase = this.record!.phase,
    backendAvailable?: boolean
  ): void {
    if (!this.record) return
    const key = `${this.record.targetCommit}:${phase}:${failure.code ?? failure.error}`
    this.save({
      error: failure.error,
      code: failure.code,
      logs: failure.logs,
      retryable: failure.retryable,
      remediation: failure.remediation,
      backendAvailable,
      phase,
      result: 'failed',
      notified: this.record.notifiedFailure === key,
    })
  }

  async checkForUpdates(): Promise<RuntimeBackendUpdateCheck> {
    const backend = this.options.backend()
    if (
      this.options.isClosing() ||
      this.flight ||
      !backend.isManagedBackend() ||
      (this.record &&
        this.record.phase !== 'download' &&
        this.record.result !== 'success' &&
        this.record.result !== 'cancelled')
    )
      return { updateAvailable: false }
    const result = await backend.checkRuntimeBackendUpdate(target => {
      if (
        !target.currentCommit ||
        !target.remoteCommit ||
        !target.version ||
        this.options.isClosing()
      )
        return
      if (this.record?.targetCommit !== target.remoteCommit)
        this.record = {
          operationId: randomUUID(),
          baseCommit: target.currentCommit,
          targetCommit: target.remoteCommit,
          version: target.version,
          phase: 'download',
          result: null,
          notified: false,
          timestamp: new Date().toISOString(),
        }
      this.save({})
    })
    if (!result.updateAvailable) return result
    if (!result.currentCommit || !result.remoteCommit || !result.version) return result
    const sameTarget = this.record?.targetCommit === result.remoteCommit
    if (!sameTarget || this.record?.result === 'cancelled') {
      this.record = {
        operationId: randomUUID(),
        baseCommit: result.currentCommit,
        targetCommit: result.remoteCommit,
        version: result.version,
        phase: 'download',
        result: null,
        notified: false,
        timestamp: new Date().toISOString(),
      }
    }
    if (this.options.isClosing()) {
      if (result.staged) this.save({ result: 'cancelled', notified: true })
      return result
    }
    if (result.error) {
      this.fail(
        { success: false, error: result.error, code: result.code, retryable: true },
        'download'
      )
    } else if (
      result.staged &&
      this.record?.result !== 'success' &&
      (this.record?.result !== 'failed' || this.record.phase === 'download')
    ) {
      this.save({ result: null, phase: 'download', error: undefined, code: undefined })
      this.run(() => this.apply())
    }
    return result
  }

  private run(action: () => Promise<void>): void {
    if (this.flight) return
    this.cancelled = false
    const operation = action()
      .catch(error => {
        logger.error(`自动热更失败: ${String(error)}`)
        try {
          this.fail({ success: false, error: String(error), retryable: true })
        } catch (saveError) {
          logger.error(`保存热更结果失败: ${String(saveError)}`)
        }
      })
      .finally(() => {
        if (this.flight === operation) this.flight = null
      })
    this.flight = operation
  }

  private async apply(): Promise<void> {
    if (!this.record) return
    const result = await this.options.backend().applyHotUpdate(this.record, {
      onPhase: phase => this.save({ phase, result: null, backendAvailable: undefined }),
      rendererReady: () => this.waitForRenderer(),
      isClosing: () => this.cancelled || this.options.isClosing(),
    })
    if (result.cancelled || this.cancelled || this.options.isClosing()) {
      this.save({ result: 'cancelled', notified: true })
    } else if (result.deferred) {
      this.save({ phase: 'download', result: null })
    } else if (!result.success) {
      const backendAvailable =
        this.record.phase === 'stopping' &&
        !!this.record.baseCommit &&
        (await this.options.backend().verifyHotUpdateTarget(this.record.baseCommit))
      this.fail(result, this.record.phase, backendAvailable)
    } else {
      this.waitForConnection()
    }
  }

  private waitForRenderer(): Promise<boolean> {
    return new Promise(resolve => {
      const timer = setTimeout(() => finish(false), RENDERER_READY_TIMEOUT_MS)
      const finish = (ready: boolean): void => {
        clearTimeout(timer)
        this.rendererAck = null
        resolve(ready)
      }
      this.rendererAck = finish
      // 订阅页面可能在刚才的停止事件后才就绪，快照及此事件都可确认。
      if (this.record) this.options.onState({ ...this.record })
    })
  }

  rendererReady(operationId: string): void {
    if (this.record?.operationId === operationId && this.record.phase === 'stopping')
      this.rendererAck?.(true)
  }

  private waitForConnection(): void {
    if (this.connectionTimer) clearTimeout(this.connectionTimer)
    this.save({ phase: 'connecting', result: null, error: undefined, code: undefined })
    this.connectionTimer = setTimeout(() => {
      this.connectionTimer = null
      void this.completeConnection(this.record!.operationId, false).catch(error =>
        logger.error(String(error))
      )
    }, CONNECTION_TIMEOUT_MS)
    this.connectionTimer.unref?.()
  }

  async completeConnection(operationId: string, connected: boolean): Promise<boolean> {
    const record = this.record
    if (
      !record ||
      record.operationId !== operationId ||
      record.phase !== 'connecting' ||
      record.result !== null ||
      this.options.isClosing()
    )
      return false
    if (this.connectionTimer) clearTimeout(this.connectionTimer)
    this.connectionTimer = null
    const verified =
      connected &&
      record.targetCommit !== null &&
      (await this.options.backend().verifyHotUpdateTarget(record.targetCommit))
    if (this.record !== record || this.options.isClosing()) return false
    if (verified) {
      this.save({
        phase: 'completed',
        result: 'success',
        notified: false,
        error: undefined,
        code: undefined,
        logs: undefined,
        remediation: undefined,
        retryable: undefined,
      })
    } else {
      this.fail(
        {
          success: false,
          error: '后端更新后连接恢复异常',
          code: 'HOT_UPDATE_CONNECTION_FAILED',
          retryable: true,
        },
        'connecting'
      )
    }
    return verified
  }

  /** 只核对上次暂存的明确目标，普通启动没有记录就绝不生成成功通知。 */
  async afterBackendStart(result: BackendStartResult): Promise<void> {
    const record = this.record
    if (
      !record ||
      !record.targetCommit ||
      !this.options.backend().isManagedBackend() ||
      this.flight ||
      record.result === 'success' ||
      this.options.isClosing()
    )
      return
    if (!result.success) {
      this.fail(
        result,
        ['download', 'stopping'].includes(record.phase) ? 'installing' : record.phase
      )
      return
    }
    if (await this.options.backend().verifyHotUpdateTarget(record.targetCommit))
      this.waitForConnection()
    else if (record.phase !== 'download' && record.result !== 'cancelled') {
      this.fail({
        success: false,
        error: '后端未运行本次更新的目标提交',
        code: 'HOT_UPDATE_TARGET_MISMATCH',
        retryable: true,
      })
    }
  }

  retry(repair?: HotUpdateRepair): boolean {
    if (!this.record || this.flight || this.record.result !== 'failed' || this.options.isClosing())
      return false
    if (this.record.phase === 'download') {
      this.save({ result: null, phase: 'download' })
      void this.checkForUpdates().catch(error =>
        this.fail({ success: false, error: String(error), retryable: true })
      )
    } else {
      this.run(async () => {
        if (
          this.record!.phase === 'stopping' &&
          this.record!.baseCommit &&
          (await this.options.backend().verifyHotUpdateTarget(this.record!.baseCommit!))
        ) {
          this.save({ result: null, phase: 'download' })
          await this.apply()
          return
        }
        this.save({
          result: null,
          backendAvailable: undefined,
          phase:
            this.record!.phase === 'stopping'
              ? 'stopping'
              : this.record!.phase === 'connecting'
                ? 'starting'
                : 'installing',
        })
        const result = await this.options
          .backend()
          .retryHotUpdate(this.record!, repair, phase => this.save({ phase }))
        if (this.cancelled || this.options.isClosing())
          this.save({ result: 'cancelled', notified: true })
        else if (!result.success) this.fail(result)
        else this.waitForConnection()
      })
    }
    return true
  }

  acknowledge(operationId: string, result: unknown): void {
    if (!this.record || this.record.operationId !== operationId || this.record.result !== result)
      return
    this.save({
      notified: true,
      notifiedFailure:
        result === 'failed'
          ? `${this.record.targetCommit}:${this.record.phase}:${this.record.code ?? this.record.error}`
          : this.record.notifiedFailure,
    })
  }

  async cancel(preservePending = false): Promise<void> {
    this.cancelled = true
    this.rendererAck?.(false)
    if (this.connectionTimer) clearTimeout(this.connectionTimer)
    this.connectionTimer = null
    if (!this.record) return
    await this.options
      .backend()
      .cancelHotUpdateAdmission(
        this.record.operationId,
        this.record.baseCommit,
        this.record.targetCommit
      )
      .catch(() => false)
    if (!this.record.result && (!preservePending || this.flight)) {
      try {
        this.save({ result: 'cancelled', notified: true })
      } catch (error) {
        logger.error(`保存热更取消结果失败: ${String(error)}`)
      }
    }
    await this.flight
  }

  dispose(): void {
    this.rendererAck?.(false)
    if (this.connectionTimer) clearTimeout(this.connectionTimer)
    this.connectionTimer = null
  }
}
