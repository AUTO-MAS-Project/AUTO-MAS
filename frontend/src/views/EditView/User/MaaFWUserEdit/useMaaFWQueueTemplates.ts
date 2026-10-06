import { computed, shallowRef, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { useScriptApi } from '@/composables/useScriptApi'
import type { MaaFWScriptConfig, MaaFWTaskSnapshot } from '@/types/script'
import type { MaaFWQueueTemplateView } from '../../MaaFWFlavor/sectionContracts'
import {
  addMaaFWQueueTemplate,
  buildMaaFWQueueTemplateSnapshot,
  parseMaaFWQueueTemplates,
  removeMaaFWQueueTemplate,
  renameMaaFWQueueTemplate,
  type MaaFWQueueTemplate,
} from '../maafwQueueTemplates'
import type { MaaFWTaskQueue } from './useMaaFWTaskQueue'

interface MaaFWQueueTemplatesOptions {
  scriptId: string
  /** 页面加载时读到的脚本配置：模板列表的初值 */
  scriptConfig: Ref<MaaFWScriptConfig | null>
  taskSnapshot: Ref<MaaFWTaskSnapshot>
  queue: Pick<
    MaaFWTaskQueue,
    | 'showPresetModal'
    | 'passwordFields'
    | 'templateDraftEntries'
    | 'describeQueueSnapshot'
    | 'replaceQueueWith'
  >
}

/**
 * 用户页的自定义模板：脚本级 `Task.Templates`，同一脚本的用户共用。
 *
 * 写之前一律先从后端读最新的列表再改（读最新 → 改 → 写），不拿页面加载时那份旧列表整份覆盖：
 * 另一个用户页同时在存模板时，旧列表会把对方刚存的冲掉。打开模板弹窗时也重读一次。
 */
export function useMaaFWQueueTemplates({
  scriptId,
  scriptConfig,
  taskSnapshot,
  queue,
}: MaaFWQueueTemplatesOptions) {
  const { getScript, updateScript } = useScriptApi()

  const templates = shallowRef<MaaFWQueueTemplate[]>([])

  watch(
    scriptConfig,
    config => {
      templates.value = parseMaaFWQueueTemplates(config?.Task?.Templates)
    },
    { immediate: true }
  )

  /** 每个模板在当前项目下的样子：哪些任务已失效、能套用的有哪些 */
  const queueTemplates = computed<MaaFWQueueTemplateView[]>(() =>
    templates.value.map(template => ({
      name: template.name,
      ...queue.describeQueueSnapshot(template.snapshot),
    }))
  )

  /** 「存为模板」弹窗里列出的任务 */
  const queueTemplateDraft = computed(() =>
    queue.templateDraftEntries.value.map(entry => ({
      id: entry.id,
      label: entry.task.label || entry.task.name,
      invalid: false,
    }))
  )

  const readLatestTemplates = async () => {
    try {
      const script = await getScript(scriptId)
      if (!script) return null
      return parseMaaFWQueueTemplates((script.config as MaaFWScriptConfig).Task?.Templates)
    } catch {
      // getScript 已经提示过错误
      return null
    }
  }

  const refreshQueueTemplates = async () => {
    const latest = await readLatestTemplates()
    if (latest) templates.value = latest
  }

  // 同一页面上连着点（删完马上又存）也按顺序一次一次来，每次都基于上一次写完的结果
  let writing: Promise<unknown> = Promise.resolve()
  const writeTemplates = (
    mutate: (latest: MaaFWQueueTemplate[]) => MaaFWQueueTemplate[] | null
  ): Promise<boolean> => {
    const run = writing.then(async () => {
      const latest = await readLatestTemplates()
      if (!latest) return false
      const next = mutate(latest)
      if (!next) {
        templates.value = latest
        return false
      }
      const success = await updateScript(scriptId, {
        Task: { Templates: JSON.stringify(next) },
      })
      templates.value = success ? next : latest
      return success
    })
    writing = run.catch(() => undefined)
    return run
  }

  const rejectDuplicate = (next: MaaFWQueueTemplate[] | null) => {
    if (!next) message.error(t('edit.queueTemplateNameExists'))
    return next
  }

  /** 把当前队列存成模板（去掉虚影、受管任务与密码值）；同名不覆盖 */
  const saveQueueTemplate = async (name: string) => {
    const snapshot = buildMaaFWQueueTemplateSnapshot(
      queue.templateDraftEntries.value,
      taskSnapshot.value.taskOptions,
      queue.passwordFields.value
    )
    if (snapshot.taskOrder.length === 0) return false
    return await writeTemplates(latest =>
      rejectDuplicate(addMaaFWQueueTemplate(latest, { name, snapshot }))
    )
  }

  const renameQueueTemplate = async (name: string, nextName: string) =>
    await writeTemplates(latest => {
      // 原模板已经被别处删掉：列表换成最新的就行，不再提示重名
      if (!latest.some(item => item.name === name)) return null
      return rejectDuplicate(renameMaaFWQueueTemplate(latest, name, nextName))
    })

  const deleteQueueTemplate = async (name: string) =>
    await writeTemplates(latest => removeMaaFWQueueTemplate(latest, name))

  /** 套用模板：直接替换队列（语义同套用预设），失效任务跳过 */
  const applyQueueTemplate = async (name: string) => {
    const template = queueTemplates.value.find(item => item.name === name)
    if (!template || template.entries.length === 0) return
    await queue.replaceQueueWith(template)
  }

  watch(queue.showPresetModal, open => {
    if (open) void refreshQueueTemplates()
  })

  return {
    queueTemplates,
    queueTemplateDraft,
    saveQueueTemplate,
    renameQueueTemplate,
    deleteQueueTemplate,
    applyQueueTemplate,
  }
}
