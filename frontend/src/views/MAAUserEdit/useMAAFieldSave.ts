import { useSaveQueue, type SaveOutcome } from '@/composables/useSaveQueue'
import { toAppError } from '@/utils/appError'
import type { MaaUserConfig } from '@/api'

/** 后端「拒绝写入」类原因：这些不是写失败，凭据/参数本身没被接受 */
const REJECTED_KINDS = new Set([
  'invalid_input',
  'conflict',
  'permission_denied',
  'protected_discard',
])

/**
 * 写失败的终态：只有拿到后端拒绝原因才算 rejected；断线无法确认落盘算 unknown；
 * 其余按「是否已回读旧值」区分草稿保留 / 已恢复旧值，不猜。
 */
const failureOutcome = (error: unknown, reverted: boolean): SaveOutcome => {
  if (error !== undefined) {
    const { kind } = toAppError(error)
    if (REJECTED_KINDS.has(kind)) return 'rejected'
    if (kind === 'network_unavailable' || kind === 'backend_unavailable') return 'unknown'
  }
  return reverted ? 'failed_reverted' : 'failed_draft_kept'
}

interface FieldSaveOptions {
  formData: object
  defaults: () => object
  canSave: () => boolean
  save: (patch: MaaUserConfig) => Promise<boolean>
  readSaved: () => Promise<object | null>
  hasDraft: (key: string) => boolean
  onFailure: () => void
  onSaved: (key: string, value: unknown) => void
  onError: (error: unknown) => void
}

const FIELD_ALIASES: Record<string, string> = { userName: 'Info.Name', userId: 'Info.Id' }
const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

const readField = (data: object, key: string): unknown =>
  key.split('.').reduce<unknown>((value, part) => (isRecord(value) ? value[part] : undefined), data)

const writeField = (data: object, key: string, value: unknown) => {
  const parts = key.split('.')
  let current = data as Record<string, unknown>
  for (const part of parts.slice(0, -1)) {
    const child = current[part]
    current = isRecord(child) ? child : (current[part] = {})
  }
  current[parts[parts.length - 1]] = value
}

// 复用公共队列，只负责字段回读和草稿保护；排队、合并与串行执行由队列持有。
export function useMAAFieldSave(options: FieldSaveOptions) {
  const { isSaving, state, fieldStates, canLeave, enqueueSave, waitForIdle } = useSaveQueue()
  const fieldVersions = new Map<string, number>()
  const failedFields = new Set<string>()
  const pendingSaves = new Set<Promise<boolean>>()

  /** 回读后端真值并覆盖表单；返回是否真的把输入恢复成后端旧值 */
  const reconcileField = async (
    key: string,
    submittedValue: unknown,
    version: number
  ): Promise<boolean> => {
    try {
      const saved = await options.readSaved()
      if (!saved) return false
      if (
        fieldVersions.get(key) !== version ||
        !Object.is(readField(options.formData, key), submittedValue) ||
        options.hasDraft(key)
      )
        return false
      const value = readField(saved, key)
      writeField(
        options.formData,
        key,
        value === undefined ? readField(options.defaults(), key) : value
      )
      failedFields.delete(key)
      return true
    } catch {
      // 回读失败保留输入与失败标记，下一次显式冲刷时重试。
      return false
    }
  }

  const saveField = (key: string, value: unknown): Promise<boolean> => {
    if (!options.canSave()) return Promise.resolve(false)
    key = FIELD_ALIASES[key] ?? key
    const version = (fieldVersions.get(key) ?? 0) + 1
    fieldVersions.set(key, version)
    failedFields.delete(key)
    writeField(options.formData, key, value)
    // enqueueSave：失败原因直接落成保存终态，队列不再把「写失败」记成已保存
    const pending = enqueueSave(async () => {
      const patch: MaaUserConfig = {}
      writeField(patch, key, value)
      let failure: unknown
      try {
        if (!(await options.save(patch))) failure = new Error(`保存字段失败: ${key}`)
      } catch (error) {
        failure = error
        options.onError(error)
      }
      if (failure === undefined) {
        failedFields.delete(key)
        // 旧请求成功不回写表单，避免盖掉尚未失焦的新输入。
        options.onSaved(key, value)
        return { outcome: 'saved' as SaveOutcome }
      }
      failedFields.add(key)
      options.onFailure()
      const reverted = await reconcileField(key, value, version)
      return { outcome: failureOutcome(failure, reverted), error: failure }
    }, key)
      .then(report => report.outcome === 'saved')
      .finally(() => pendingSaves.delete(pending))
    pendingSaves.add(pending)
    return pending
  }

  const waitForPending = async (): Promise<boolean> => {
    let allSaved = true
    while (pendingSaves.size > 0) {
      if ((await Promise.all([...pendingSaves])).some(saved => !saved)) allSaved = false
    }
    return allSaved && failedFields.size === 0
  }

  const flush = async (): Promise<boolean> => {
    for (const key of [...failedFields]) void saveField(key, readField(options.formData, key))
    return waitForPending()
  }

  const hasPendingEdits = () => pendingSaves.size > 0 || failedFields.size > 0
  return {
    isSaving,
    state,
    fieldStates,
    canLeave,
    waitForIdle,
    saveField,
    flush,
    waitForPending,
    hasPendingEdits,
  }
}
