import { computed, type Ref } from 'vue'
import { useIsMutating, useMutation } from '@tanstack/vue-query'
import { useScriptApi } from '@/composables/useScriptApi'
import { translate as t } from '@/i18n'

interface ScriptSave {
  run: () => Promise<unknown>
  key?: string
}

interface ScriptSaveMutationOptions {
  scriptId: string
  isInitializing: Ref<boolean>
  logger: Pick<ReturnType<typeof window.electronAPI.getLogger>, 'info' | 'error'>
}

/** Vue Query 按脚本串行保存；仅合并尚未开始的同字段更新。 */
export function useScriptSaveMutation({
  scriptId,
  isInitializing,
  logger,
}: ScriptSaveMutationOptions) {
  const { updateScript, error: apiError } = useScriptApi()
  const mutationKey = ['script-save', scriptId]
  const pending = new Map<string, { job: ScriptSave; promise: Promise<unknown> }>()
  const savingCount = useIsMutating({ mutationKey, exact: true })
  const mutation = useMutation({
    mutationKey,
    scope: { id: `script-save:${scriptId}` },
    networkMode: 'always',
    retry: false,
    mutationFn: async (job: ScriptSave) => {
      // 已开始的请求不能被后续输入替换；后续改动另排一次保存。
      if (job.key !== undefined && pending.get(job.key)?.job === job) pending.delete(job.key)
      return job.run()
    },
  })

  // 专项回读、回滚等步骤留在页面，但必须与普通字段共用这一条队列。
  const enqueue = <T>(run: () => Promise<T>, key?: string): Promise<T> => {
    const existing = key === undefined ? undefined : pending.get(key)
    if (existing) {
      existing.job.run = run
      return existing.promise as Promise<T>
    }

    // 多字段联动是顺序边界，后续字段不能合并到这次联动之前。
    if (key === undefined) pending.clear()
    const job = { run, key }
    const promise = mutation.mutateAsync(job)
    if (key !== undefined) pending.set(key, { job, promise })
    return promise as Promise<T>
  }

  const save = (data: Record<string, unknown>, key?: string): Promise<boolean> => {
    if (isInitializing.value) return Promise.resolve(false)
    return enqueue(async () => {
      try {
        const success = await updateScript(scriptId, data)
        if (!success) throw new Error(apiError.value || t('edit.couldNotSaveConfiguration'))
        logger.info(key ? `配置已保存: ${key}` : '配置已保存')
        return true
      } catch (error) {
        // updateScript 已负责用户提示，这里只记录失败，避免重复弹出提示。
        logger.error(`保存失败: ${error instanceof Error ? error.message : String(error)}`)
        throw error
      }
    }, key).catch(() => false)
  }

  // 字段只提交自己的补丁，多字段联动由页面通过 save 一次提交。
  const saveField = (category: string, key: string, value: unknown) =>
    save({ [category]: { [key]: value } }, `${category}.${key}`)

  return {
    save,
    saveField,
    enqueue,
    isSaving: computed(() => savingCount.value > 0),
    error: mutation.error,
  }
}
