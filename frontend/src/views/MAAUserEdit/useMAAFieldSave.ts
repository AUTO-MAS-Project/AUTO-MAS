import { useSaveQueue } from '@/composables/useSaveQueue'
import type { MaaUserConfig } from '@/api'

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
  const { isSaving, enqueue } = useSaveQueue()
  const fieldVersions = new Map<string, number>()
  const failedFields = new Set<string>()
  const pendingSaves = new Set<Promise<boolean>>()

  const reconcileField = async (key: string, submittedValue: unknown, version: number) => {
    try {
      const saved = await options.readSaved()
      if (!saved) return
      if (
        fieldVersions.get(key) !== version ||
        !Object.is(readField(options.formData, key), submittedValue) ||
        options.hasDraft(key)
      )
        return
      const value = readField(saved, key)
      writeField(
        options.formData,
        key,
        value === undefined ? readField(options.defaults(), key) : value
      )
      failedFields.delete(key)
    } catch {
      // 回读失败保留输入与失败标记，下一次显式冲刷时重试。
    }
  }

  const saveField = (key: string, value: unknown): Promise<boolean> => {
    if (!options.canSave()) return Promise.resolve(false)
    key = FIELD_ALIASES[key] ?? key
    const version = (fieldVersions.get(key) ?? 0) + 1
    fieldVersions.set(key, version)
    failedFields.delete(key)
    writeField(options.formData, key, value)
    const pending = enqueue(async () => {
      const patch: MaaUserConfig = {}
      writeField(patch, key, value)
      let success = false
      try {
        success = await options.save(patch)
      } catch (error) {
        options.onError(error)
      }
      if (!success) {
        failedFields.add(key)
        options.onFailure()
        await reconcileField(key, value, version)
        return false
      }
      failedFields.delete(key)
      // 旧请求成功不回写表单，避免盖掉尚未失焦的新输入。
      options.onSaved(key, value)
      return true
    }, key)
      .catch(error => {
        failedFields.add(key)
        options.onError(error)
        return false
      })
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
  return { isSaving, saveField, flush, waitForPending, hasPendingEdits }
}
