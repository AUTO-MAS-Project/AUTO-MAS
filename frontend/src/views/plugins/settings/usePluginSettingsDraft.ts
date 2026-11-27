import { computed, reactive, ref, shallowRef } from 'vue'
import { ApiResponseError } from '@/utils/apiResult'

export type SettingsValues = Record<string, Record<string, unknown>>

export interface SettingsChange {
  group: string
  field: string
}

/** 配置值来自 JSON 接口，按 JSON 深拷贝与比较即可。 */
const clone = <T>(value: T): T =>
  value === undefined ? value : (JSON.parse(JSON.stringify(value)) as T)
const sameValue = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right)

/** 与上次读取的值相比有改动的字段，按分组与字段顺序。 */
export function settingsChanges(
  values: SettingsValues,
  baseline: SettingsValues
): SettingsChange[] {
  const groups = new Set([...Object.keys(baseline), ...Object.keys(values)])
  return [...groups].flatMap(group => {
    const current = values[group] ?? {}
    const original = baseline[group] ?? {}
    const fields = new Set([...Object.keys(original), ...Object.keys(current)])
    return [...fields].flatMap(field =>
      sameValue(current[field], original[field]) ? [] : [{ group, field }]
    )
  })
}

/**
 * 插件设置页的编辑稿：记住上次读取的值，算出未保存的更改，支持放弃与重读时保留改动。
 * 重读（切换语言、按钮类字段执行后）默认保留编辑中的值，只有保存成功或换了插件才整体替换。
 */
export function usePluginSettingsDraft() {
  const values = reactive<SettingsValues>({})
  const errors = ref<Record<string, string>>({})
  const baseline = shallowRef<SettingsValues>({})

  const changes = computed(() => settingsChanges(values, baseline.value))
  const dirtyCount = computed(() => changes.value.length)

  const assign = (next: SettingsValues) => {
    for (const key of Object.keys(values)) delete values[key]
    for (const [group, fields] of Object.entries(next)) values[group] = clone(fields)
  }

  /** 用读取结果替换编辑稿；keepDraft 时把仍存在的分组里的改动放回去。 */
  const reset = (next: SettingsValues, options: { keepDraft: boolean }) => {
    const previousErrors = errors.value
    errors.value = {}
    const kept = options.keepDraft
      ? changes.value.map(change => ({
          ...change,
          value: clone(values[change.group]?.[change.field]),
        }))
      : []
    baseline.value = clone(next)
    assign(next)
    for (const { group, field, value } of kept) {
      const fields = values[group]
      if (!fields) continue
      const key = `${group}.${field}`
      if (previousErrors[key] && !sameValue(fields[field], value))
        errors.value[key] = previousErrors[key]
      fields[field] = value
    }
  }

  const update = (group: string, field: string, value: unknown) => {
    delete errors.value[`${group}.${field}`]
    if (!values[group]) values[group] = {}
    values[group][field] = value
  }

  /** 放弃改动，恢复到上次读取的值。 */
  const discard = () => {
    errors.value = {}
    assign(baseline.value)
  }

  /** 只标出接口确认校验失败的字段。 */
  const saveFailed = (error: unknown) => {
    errors.value = error instanceof ApiResponseError ? { ...error.fieldErrors } : {}
  }

  /** 提交时刻的编辑值快照，保存成功后交给 commit。 */
  const snapshot = (): SettingsValues => clone({ ...values })

  /**
   * 保存成功后把基线设为刚提交的值，编辑稿里此后的改动仍算未保存。
   * 之后的重读失败也不会让已保存的内容继续显示成未保存。
   */
  const commit = (submitted: SettingsValues) => {
    errors.value = {}
    baseline.value = clone(submitted)
  }

  return {
    values,
    errors,
    saveFailed,
    changes,
    dirtyCount,
    reset,
    update,
    discard,
    snapshot,
    commit,
  }
}
